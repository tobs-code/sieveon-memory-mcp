# -*- coding: utf-8 -*-
"""
Common logic functions shared between HTTP endpoints and MCP tools
"""

import asyncio
import sys
import os
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.extraction.classifier import QueryClassifier
from src.extraction.entropy_gate import escape_surrealql
from src.extraction.entity_utils import infer_entity_type
from src.planner.executor import RetrievalExecutor
from src.router.budget import BudgetLevel, BudgetTracker
from src.router.policy import get_policy, resolve_query_type
from .core import (
    _query_surreal,
    _extract_result,
    _clean_output,
)

MAX_CONTENT_LENGTH = 100_000

_entropy_gate_instance = None


def _get_entropy_gate():
    global _entropy_gate_instance
    # The gate snapshots its namespace at construction: rebuild whenever the
    # core namespace changed (eval harnesses switch NS/DB per run). Without
    # this, stores silently land in the default namespace (found via an empty
    # LoCoMo spike namespace in 2026-09-30).
    from .core import SURREAL_DB, SURREAL_NS

    if (
        _entropy_gate_instance is None
        or getattr(_entropy_gate_instance, "surreal_ns", None) != SURREAL_NS
        or getattr(_entropy_gate_instance, "surreal_db", None) != SURREAL_DB
    ):
        from src.extraction.entropy_gate import EntropyGate
        _entropy_gate_instance = EntropyGate(ns=SURREAL_NS, db=SURREAL_DB)
    return _entropy_gate_instance


async def _store_content(content: str, source: str = "user_input", debug: bool = False, metadata: Optional[Dict[str, Any]] = None, trust: Optional[str] = None) -> dict:
    """Einzige Store-Implementierung: validiert → EntropyGate → Event + ggf. KG."""
    if not content or not content.strip():
        return {"event_id": None, "status": "error", "source": source,
                "message": "content must not be empty or whitespace-only"}
    if '\x00' in content:
        return {"event_id": None, "status": "error", "source": source,
                "message": "content contains null bytes, rejecting"}
    if len(content) > MAX_CONTENT_LENGTH:
        return {"event_id": None, "status": "error", "source": source,
                "message": f"content exceeds maximum length of {MAX_CONTENT_LENGTH} (got {len(content)})"}

    gate = _get_entropy_gate()
    try:
        event_id, kg_result, gate_result = await asyncio.to_thread(gate.ingest, content, source, debug=debug, metadata=metadata, trust=trust)
    except Exception as e:
        return {"event_id": None, "status": "error", "source": source,
                "message": f"storage failed – unexpected error: {e}"}

    if event_id is None:
        return {"event_id": None, "status": "error", "source": source,
                "message": "storage failed – event could not be persisted"}

    gate_info: dict = {"decision": "active"}
    if isinstance(gate_result, dict):
        gate_info["decision"] = gate_result.get("decision", "active")
    if gate_result.get("decision") != "extract":
        gate_info["reason"] = gate_result.get("reason", "unknown")
        gate_info["composite_score"] = gate_result.get("composite_score")
        gate_info["threshold"] = gate_result.get("threshold")

    # KG-Resultate aus ingest() verwenden (kein zweiter _extract_to_kg-Aufruf!)
    if kg_result:
        gate_info["kg"] = {"entities_created": kg_result.get("entities_created", 0),
                            "facts_created": kg_result.get("facts_created", 0),
                            "tier_skipped": kg_result.get("tier_skipped", 0),
                            # Which pre-write filters fired, and how often. Without
                            # these a drop in stored-fact volume is silent.
                            "structurally_dropped": kg_result.get("structurally_dropped", 0),
                            "verifier_dropped": kg_result.get("verifier_dropped", 0)}

    base_source = (source or "").split("#")[0]
    return {"event_id": event_id, "status": "stored", "source": source,
            "trust": trust if isinstance(trust, str) and trust else ("direct" if base_source == "user_input" else "untrusted"),
            "gate": gate_info}


async def _execute_query(
    query: str,
    cost_budget: str = "auto",
    limit: int = 10,
    since: Optional[str] = None,
    until: Optional[str] = None,
    at_time: Optional[str] = None,
) -> dict:
    """Einzige Query-Implementierung: classify → route → execute → parse → track.

    since/until bound event timestamps (fn::events_at semantics),
    at_time pins KG validity (fn::facts_at_time semantics, B1).
    """
    classifier = QueryClassifier()
    q_type_str, confidence = classifier.classify(query)

    # Classifier emits "multi-hop" while the enum uses "multi_hop"; unknown
    # types normalize to FACTUAL instead of failing the whole query.
    q_type = resolve_query_type(q_type_str)

    policy = get_policy()
    strategy_info = policy.get_strategy(q_type, confidence)
    
    # Unpack the tuple returned by get_strategy
    strategy, budget_level, policy_applied = strategy_info
    
    # Create strategy dict with required fields
    strategy_dict = {
        "strategy": strategy,
        "cost_budget": cost_budget if cost_budget != "auto" else budget_level.value,
        "policy_applied": policy_applied
    }

    executor = RetrievalExecutor()
    
    # Create a BudgetTracker instance with the appropriate budget level
    # Convert string budget level to BudgetLevel enum
    try:
        budget_enum = BudgetLevel(strategy_dict["cost_budget"])
    except ValueError:
        # If the budget level is not valid, default to MEDIUM
        budget_enum = BudgetLevel.MEDIUM
    
    budget_tracker = BudgetTracker(budget_enum)
    execution_error = None
    results_raw: Dict[str, Any] = {}
    
    try:
        # Convert strategy string to RetrievalStrategy enum
        from src.planner.executor import RetrievalStrategy
        try:
            strategy_enum = RetrievalStrategy(strategy_dict["strategy"])
        except ValueError:
            # Unknown strategy: hybrid_fallback is the safe default here too,
            # it degrades gracefully instead of dropping the graph/vector paths
            strategy_enum = RetrievalStrategy.HYBRID_FALLBACK
        
        results_raw = await executor.execute_strategy(
            strategy_enum,
            query,
            budget_tracker,
            since=since,
            until=until,
            at_time=at_time,
            query_type=q_type.value,
        )
        if isinstance(results_raw, dict) and results_raw.get("error"):
            execution_error = {
                "message": results_raw["error"],
                "type": results_raw.get("error_type", "Exception"),
            }
        results = _flatten_query_results(results_raw)
    except Exception as e:
        execution_error = {"message": str(e), "type": type(e).__name__}
        print(f"Error executing strategy: {e}")
        # Fallback: return empty results
        results = []

    entities, facts, events = _categorize_results(results)
    summary = _synthesize_answer(
        query, entities, facts, events,
        retrieval_relevance=results_raw.get("relevance_score"),
    )

    # Enrich events with matched terms and ranking info
    import re
    query_words_list = [w for w in re.findall(r'\b\w+\b', query.lower()) if len(w) > 2]
    enriched_events = []
    for ev in events:
        content = ev.get("content", "")
        if content and query_words_list:
            matched = set()
            relevance_hits = 0
            for word in query_words_list:
                if word.lower() in content.lower():
                    relevance_hits += 1
                    matched.add(word)
            ev["matched_terms"] = sorted(matched)
            ev["relevance_hits"] = relevance_hits
        enriched_events.append(ev)

    ranking = {
        "strategy_used": strategy_dict["strategy"],
        "query_type": q_type.value,
        "classification_confidence": confidence,
        "total_candidates": len(entities) + len(facts) + len(events),
        "relevance_score": results_raw.get("relevance_score"),
        "diversity_note": "Results from multiple retrieval paths (FTX + vector + KG) fused via RRF.",
        "temporal_window": {"since": since, "until": until, "at_time": at_time},
    }
    if any(ev.get("relevance_score") is not None for ev in events):
        scores = [ev.get("relevance_score", 0) or 0 for ev in events]
        ranking["score_range"] = {"min": round(min(scores), 4), "max": round(max(scores), 4)} if scores else None

    events = events[:limit]
    entities = entities[:limit]
    facts = facts[:limit]

    return {
        "query": query,
        "classified_as": q_type.value,
        "confidence": confidence,
        "strategy": strategy_dict["strategy"],
        "cost_budget": strategy_dict["cost_budget"],
        "results": {"entities": entities, "facts": facts, "events": events},
        "total": len(entities) + len(facts) + len(events),
        "ranking": ranking,
        "error": execution_error,
        "summary": {
            "found": summary["found"],
            # verdict is one of found / weak_match / nothing_found. An agent
            # needs this to tell "no answer in the store" apart from "here is
            # something loosely related", which a populated result list alone
            # does not convey.
            "verdict": summary["verdict"],
            "confidence": summary["confidence"],
            "answer": summary["answer"],
            "total_facts": summary["total_facts"],
            "total_entities": summary["total_entities"],
            "total_events": summary["total_events"],
            "near_misses": summary["near_misses"],
        },
        "budget": {
            "level": budget_enum.value,
            "db_calls": budget_tracker.db_calls,
            "estimated_tokens": budget_tracker.estimated_tokens,
            "over_budget": budget_tracker.is_over_budget(),
        },
    }


def _flatten_query_results(results_raw: Any) -> List[Any]:
    """Flatten the various result shapes from different strategies into one list."""
    if isinstance(results_raw, dict) and "combined_results" in results_raw:
        combined = results_raw["combined_results"]
        return combined if isinstance(combined, list) else [combined]

    if isinstance(results_raw, dict):
        flat = []
        for key in ("events", "entities", "facts", "keyword_results", "vector_results", "temporal_results", "result"):
            val = results_raw.get(key)
            if isinstance(val, list):
                flat.extend(val)
        if not flat and "result" in results_raw:
            val = results_raw["result"]
            flat = val if isinstance(val, list) else [val]
        return flat

    if isinstance(results_raw, list):
        return results_raw
    return []


def _categorize_results(results: List[Any]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Sort results into entities, facts, events buckets and enrich fact names."""
    entities, facts, events = [], [], []
    for r in results:
        if isinstance(r, dict):
            clean = _clean_output(r)
            rid = clean.get("id", "")
            if isinstance(rid, str):
                if rid.startswith("entity:"):
                    entities.append(clean)
                elif rid.startswith("fact:"):
                    facts.append(clean)
                elif rid.startswith("event:"):
                    events.append(clean)
                else:
                    events.append(clean)
            else:
                events.append(clean)
        elif isinstance(r, list):
            for item in r:
                if isinstance(item, dict):
                    clean = _clean_output(item)
                    rid = clean.get("id", "")
                    if isinstance(rid, str) and rid.startswith("entity:"):
                        entities.append(clean)
                    elif isinstance(rid, str) and rid.startswith("fact:"):
                        facts.append(clean)
                    else:
                        events.append(clean)

    NOISY_PREDICATES = {"weakly_related", "mentions"}
    FACTS_MIN_CONFIDENCE = 0.5
    filtered_facts = []
    for f in facts:
        pred = f.get("predicate", "")
        conf = f.get("confidence", 0) or 0
        if pred in NOISY_PREDICATES:
            continue
        if pred in ("co_occurs_with", "strongly_related", "related_to") and conf < FACTS_MIN_CONFIDENCE:
            continue
        # Ontologie-Validierung: Prädikat muss zu Entity-Typen passen
        in_data = f.get("in", {})
        out_data = f.get("out", {})
        in_type = in_data.get("type", "") if isinstance(in_data, dict) else ""
        out_type = out_data.get("type", "") if isinstance(out_data, dict) else ""
        if pred not in ("related_to", "co_occurs_with", "strongly_related", "weakly_related", "mentions"):
            in_name = in_data.get("name", "") if isinstance(in_data, dict) else ""
            out_name = out_data.get("name", "") if isinstance(out_data, dict) else ""
            # Nur types via infer_entity_type ergänzen wenn der Name keine SurrealDB-ID ist
            if not in_type and in_name and not in_name.startswith("entity:") and not in_name.startswith("fact:"):
                in_type = infer_entity_type(in_name)
            if not out_type and out_name and not out_name.startswith("entity:") and not out_name.startswith("fact:"):
                out_type = infer_entity_type(out_name)
            # Validierung wenn beide types bekannt sind und keiner "concept" (Fallback) ist
            if in_type and out_type and in_type != "concept" and out_type != "concept":
                from src.extraction.entity_utils import validate_predicate
                if not validate_predicate(in_type, pred, out_type):
                    continue
            # Fallback: wenn Typen nicht bestimmbar (entity-ID als name), require high confidence
            elif conf < 0.8:
                continue
        filtered_facts.append(f)
    facts = filtered_facts

    name_to_entity = {}
    for e in entities:
        eid = e.get("id")
        ename = e.get("name")
        if eid and ename:
            name_to_entity[eid] = ename

    for f in facts:
        # Normalize executor format (in_name/in_id) to in/out dicts
        for key, name_key, type_key, id_key in [
            ('in', 'in_name', 'in_type', 'in_id'),
            ('out', 'out_name', 'out_type', 'out_id'),
        ]:
            val = f.get(key)
            if not isinstance(val, (dict, str)):
                name_val = f.pop(name_key, None) if name_key in f else None
                type_val = f.pop(type_key, None) if type_key in f else None
                id_val = f.pop(id_key, None) if id_key in f else None
                if id_val:
                    f[key] = {"id": id_val, "name": name_val, "type": type_val}
                    val = f[key]

            if isinstance(val, dict):
                val_id = val.get("id")
                if val_id and val_id not in name_to_entity:
                    for e in entities:
                        if e.get("id") == val_id:
                            name_to_entity[val_id] = e.get("name", val_id)
                            break

        for key in ('in', 'out'):
            val = f.get(key)
            if isinstance(val, str):
                f[key] = {"id": val, "name": name_to_entity.get(val, val), "type": ""}
            elif isinstance(val, dict):
                val_id = val.get("id", "")
                val_name = val.get("name")
                if not val_name and val_id in name_to_entity:
                    val_name = name_to_entity[val_id]
                f[key] = {
                    "id": val_id,
                    "name": val_name if val_name else val_id,
                    "type": val.get("type", ""),
                }

    return entities, facts, events


# Words that must never count as evidence that an event answers the question.
# They appear in almost any sentence, so matching them produces confident
# nonsense: "What is the capital of France?" matched "is"/"the" and returned
# a note about Charles Babbage.
_SUMMARY_STOPWORDS = frozenset({
    "who", "what", "which", "where", "when", "why", "how",
    "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for",
    "with", "by", "from", "at", "as", "it", "its", "this", "that",
    "first", "made", "make", "makes", "get", "get", "any", "all",
    "can", "could", "should", "would", "will", "shall", "may", "might",
    "there", "here", "about", "into", "than", "then", "some", "such",
    "not", "no", "yes", "if", "but", "so", "because", "when", "while",
})


# A query is accepted as answered when the retriever's top vector similarity
# clears this. Measured on docs/eval_retrieval_gold.jsonl: answerable queries
# score 0.524-0.818 and no-answer probes 0.224-0.335, so this sits in the gap
# rather than on a measured optimum -- four no-answer queries is too few to
# place it precisely.
#
# This is an empirically calibrated value for one embedding model on one
# corpus, not a universal constant: cosine scores from a ranking-trained
# embedding are only comparable within a query, and this constant encodes
# what they happen to mean here. Re-measure after changing the model or the
# corpus, otherwise the verdict silently misbehaves.
_SUMMARY_FOUND_THRESHOLD = 0.43

# Minimum retrieval confidence before any evidence is trusted at all. Below
# this the query is reported as having nothing, regardless of how many rows
# came back -- the store always returns its nearest neighbours, so row count
# says nothing about whether they are relevant.
_SUMMARY_MIN_RETRIEVAL = 0.40


# Above this, retrieval results may be trusted for facts and entities that
# have no lexical overlap with the query -- the paraphrase case, where
# "The streaming service's cloud provider?" shares no content word with
# "Netflix uses Amazon Web Services". Set equal to the accept threshold
# because both are read off the same measurement: a query whose top vector
# similarity reaches the accept band is one whose results may be trusted.
_SUMMARY_TRUST_RETRIEVAL_ABOVE = 0.43


def _is_confident_retrieval(relevance: Optional[float]) -> bool:
    """Whether the retriever looked confident enough to trust a paraphrase."""
    return (
        relevance is not None
        and relevance >= _SUMMARY_TRUST_RETRIEVAL_ABOVE
    )


def _synthesize_answer(
    query: str,
    entities: List[Dict],
    facts: List[Dict],
    events: List[Dict],
    retrieval_relevance: Optional[float] = None,
) -> Dict[str, Any]:
    """Synthesize a structured answer from entities, facts, and events."""
    answer_parts = []
    key_facts = []
    key_entities = []
    event_snippets = []

    import re
    query_lower = query.lower()
    query_words = {
        w
        for w in re.findall(r"\b\w+\b", query_lower)
        if len(w) > 2 and w not in _SUMMARY_STOPWORDS
    }

    fact_entity_names = set()
    for f in facts:
        in_data = f.get("in")
        out_data = f.get("out")
        subj = ""
        obj = ""
        if isinstance(in_data, dict):
            subj = in_data.get("name", in_data.get("id", ""))
        elif isinstance(in_data, str):
            subj = in_data
        if isinstance(out_data, dict):
            obj = out_data.get("name", out_data.get("id", ""))
        elif isinstance(out_data, str):
            obj = out_data
        pred = f.get("predicate", "")
        if subj and obj and pred and pred not in ("mentions", "weakly_related"):
            subj_words = {w for w in re.findall(r'\b\w+\b', subj.lower()) if len(w) > 2}
            obj_words = {w for w in re.findall(r'\b\w+\b', obj.lower()) if len(w) > 2}
            if not (subj_words & query_words or obj_words & query_words):
                # No lexical overlap. The retriever may have matched this
                # semantically ("The streaming service's cloud provider?" shares
                # no content word with "Netflix uses Amazon Web Services"), so
                # do not drop it outright -- but only when the retriever
                # actually looks confident. Without that gate every fact came
                # back for every query, because the strategies return their
                # top-k regardless of the query.
                if not _is_confident_retrieval(retrieval_relevance):
                    continue
                key_facts.append(f"{subj} {pred} {obj}")
                fact_entity_names.update([subj.lower(), obj.lower()])
                continue
            key_facts.append(f"{subj} {pred} {obj}")
            fact_entity_names.update([subj.lower(), obj.lower()])

    key_facts = key_facts[:5]

    for e in entities:
        name = e.get("name", "")
        if not name:
            continue
        name_lower = name.lower()
        name_words = {w for w in re.findall(r'\b\w+\b', name_lower) if len(w) > 2}
        if not (name_words & query_words or name_lower in fact_entity_names):
            # Same reasoning as facts above: keep the entity when the
            # retriever is confident, drop it otherwise.
            if not _is_confident_retrieval(retrieval_relevance):
                continue
            etype = e.get("type", "")
            key_entities.append(f"{name} ({etype})" if etype else name)
            if len(key_entities) >= 5:
                break
            continue
        etype = e.get("type", "")
        key_entities.append(f"{name} ({etype})" if etype else name)
        if len(key_entities) >= 5:
            break

    query_words_list = [
        w for w in re.findall(r"\b\w+\b", query_lower) if len(w) > 2 and w not in _SUMMARY_STOPWORDS
    ]
    for ev in events[:5]:
        content = ev.get("content", "")
        if content:
            content_words = {w.lower() for w in re.findall(r"\b\w+\b", content.lower())}
            # Whole-word matching on content terms. Substring matching scored
            # "design" inside "designed" and counted question words like "is"
            # and "was" as hits, so a query with nothing to do with the store
            # ("What is the capital of France?") still reported a best match
            # and found=True. That is worse than returning nothing: the
            # agent reads a populated answer as a real one.
            matched = [w for w in query_words_list if w in content_words]
            score = len(matched)
            # Score by share of the query covered, not by raw count. A longer
            # query has more words to miss, so a raw count punished it:
            # "Where is Munich's Acme Corp based?" matched acme/corp/munich --
            # three real content words including the entity and the place --
            # yet scored no better than a two-word overlap, and fell below the
            # bar. Coverage keeps paraphrases honest without letting an
            # unrelated long sentence in.
            coverage = score / len(query_words_list) if query_words_list else 0.0
            # Require more than a single incidental overlap, and enough of the
            # query to be more than coincidence.
            if score >= 2 and coverage >= 0.5:
                event_snippets.append({
                    "content": content[:400],
                    "relevance_hits": score,
                    "query_coverage": round(coverage, 4),
                    "matched_terms": sorted(matched),
                    "source": ev.get("source", ""),
                    "timestamp": ev.get("timestamp", ""),
                })

    event_snippets.sort(key=lambda x: x["relevance_hits"], reverse=True)

    if key_facts:
        answer_parts.append({"type": "facts_found", "detail": key_facts})
    if key_entities:
        answer_parts.append({"type": "entities_found", "detail": key_entities})
    if event_snippets:
        answer_parts.append({"type": "relevant_events", "detail": event_snippets[:3]})

    has_content = bool(key_facts or key_entities or event_snippets)

    # An agent needs to tell "the store has nothing on this" apart from
    # "here are some loosely related rows". A populated result list with no
    # statement of confidence invites the agent to answer from noise, and a
    # bare empty list is ambiguous -- it looks like a broken query. So report
    # a verdict plus the evidence behind it.
    #
    # Confidence is deliberately conservative: a structured fact is strong
    # evidence, an entity name match is weak on its own, and an event needs
    # two content-word overlaps. Anything below `found_threshold` is reported
    # as "nothing_found" while still returning the near misses, so the caller
    # can see what was considered without treating it as an answer.
    evidence = 0.0
    if key_facts:
        evidence += 0.6
    if event_snippets:
        # Scale by how much of the query the best event actually covers, so a
        # thin overlap cannot reach the bar on strength of raw word count.
        best_coverage = event_snippets[0].get("query_coverage", 0.0)
        evidence += min(0.4, 0.4 * best_coverage)
    if key_entities:
        evidence += 0.2

    confidence = min(1.0, round(evidence, 4))
    if not has_content:
        verdict = "nothing_found"
    elif confidence >= _SUMMARY_FOUND_THRESHOLD:
        verdict = "found"
    else:
        verdict = "weak_match"

    # Retrieval confidence gates the verdict. Evidence built from rows the
    # retriever already doubts is not evidence, and this is the layer that
    # keeps an unrelated query from reading as answered: the store always
    # returns its nearest neighbours, so "some facts matched a word" is not a
    # reason to claim an answer.
    if (
        retrieval_relevance is not None
        and retrieval_relevance < _SUMMARY_MIN_RETRIEVAL
    ):
        verdict = "nothing_found"

    # Build a concise natural-language summary
    text_parts = []
    if key_facts:
        text_parts.append(". ".join(key_facts[:3]))
    if key_entities:
        text_parts.append("Related entities: " + ", ".join(key_entities[:5]))
    if event_snippets:
        best = event_snippets[0]
        text_parts.append(f"Best match: \"{best['content'][:150]}...\" (source: {best['source']}, hits: {best['relevance_hits']})")

    answer_text = ". ".join(text_parts) if text_parts else ""

    if verdict == "nothing_found":
        answer_text = (
            "Nothing in the store matches this query. No facts, entities or "
            "events were found that relate to it."
        )
    elif verdict == "weak_match":
        answer_text = (
            "No direct match found. These are the closest related items and may "
            "not answer the question: " + answer_text
        )

    return {
        # Backwards compatible: a caller checking `found` still behaves the
        # same, but `found` is now false unless the evidence cleared the bar.
        "found": verdict == "found",
        "verdict": verdict,
        "confidence": confidence,
        "answer": answer_text,
        "parts": answer_parts,
        "total_facts": len(facts),
        "total_entities": len(entities),
        "total_events": len(events),
        # What was considered and why it was not enough. Lets an agent decide
        # whether to widen the search itself instead of guessing.
        "near_misses": {
            "facts": key_facts[:3],
            "entities": key_entities[:5],
            "events": [
                {"content": e["content"][:120], "matched_terms": e["matched_terms"]}
                for e in event_snippets[:2]
            ],
        },
    }


async def _get_or_create_entity(name: str) -> Optional[str]:
    """Find an entity by name or create it with inferred type. Returns entity ID or None."""
    name_escaped = escape_surrealql(name)
    sql = f"SELECT id FROM entity WHERE name = '{name_escaped}' LIMIT 1;"
    result = await _query_surreal(sql)
    entities = _extract_result(result, 1)
    if entities:
        return entities[0]["id"]

    entity_type = infer_entity_type(name)
    create_sql = f"CREATE entity SET name = '{name_escaped}', type = '{entity_type}', created_at = time::now(), updated_at = time::now();"
    create_result = await _query_surreal(create_sql)
    created = _extract_result(create_result, 1)
    if created:
        return created[0]["id"]
    return None