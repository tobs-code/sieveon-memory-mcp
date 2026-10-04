"""Shared entity utilities for sieveon - single source of truth."""

import os
import re
import sys
from typing import Optional

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.extraction.embedding_service import BaseEmbeddingService, get_embedding_service

# Global variable for spaCy model (lazy-loaded)
_nlp = None

# Cache for embedding calculations
_EMBEDDING_CACHE = {}

# Cache for infer_entity_type embedding-path results (name.lower() -> type).
# Types are stable; each miss costs a full model.encode (~110ms CPU).
_INFER_TYPE_CACHE: dict[str, str] = {}


def _get_nlp():
    """Lazy-load spaCy model with fallback to regex if not available."""
    global _nlp
    if _nlp is None:
        try:
            import spacy

            _nlp = spacy.load("en_core_web_sm")
        except (ImportError, OSError):
            # spaCy not installed or model not available
            _nlp = None
    return _nlp


_STOPWORDS = {
    "the",
    "a",
    "an",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "in",
    "on",
    "at",
    "by",
    "for",
    "with",
    "from",
    "to",
    "of",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "can",
    "could",
    "must",
    "not",
    "no",
    "nor",
    "but",
    "if",
    "as",
    "so",
    "this",
    "that",
    "there",
    "their",
    "them",
    "they",
    "then",
    "than",
    "also",
    "very",
    "just",
    "like",
    "into",
    "about",
    "over",
    "such",
    "each",
    "which",
    "what",
    "who",
    "whom",
    "when",
    "where",
    "why",
    "how",
    "all",
    "both",
    "every",
    "some",
    "any",
    "few",
    "more",
    "most",
    "other",
    "another",
}

_PREPOSITION_STARTS = {
    "in",
    "on",
    "at",
    "by",
    "for",
    "with",
    "from",
    "to",
    "of",
    "about",
    "over",
    "under",
    "through",
    "between",
    "among",
    "against",
    "without",
    "during",
    "before",
    "after",
    "above",
    "below",
    "out",
    "off",
    "up",
    "down",
    "into",
    "onto",
    "upon",
    "within",
    "across",
    "along",
    "around",
    "behind",
    "beneath",
    "beside",
    "beyond",
    "inside",
    "outside",
    "toward",
    "towards",
    "via",
    "per",
}

_VERB_STARTS = {
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "can",
    "could",
    "must",
    "works",
    "worked",
    "working",
    "relies",
    "relied",
    "relying",
    "based",
    "lives",
    "lived",
    "living",
    "says",
    "said",
    "made",
    "makes",
    "making",
    "uses",
    "used",
    "using",
    "takes",
    "took",
    "taking",
    "gives",
    "gave",
}

_ENTITY_PROTOTYPES = {
    "organization": [
        "Acme Corp",
        "Microsoft Inc",
        "Google LLC",
        "OpenAI Ltd",
        "Red Cross",
        "United Nations",
        "Stanford University",
    ],
    "technology": [
        "SQL Database",
        "Web Framework",
        "API Gateway",
        "MCP Server",
        "Entropy Gate",
        "Protocol",
        "Engine",
        "Platform",
        "Toolkit",
        "Runtime",
    ],
    "person": [
        "John Smith",
        "Alice Johnson",
        "Jane Doe",
        "Mr Bond",
        "Dr Watson",
        "Prof Higgins",
    ],
    "concept": [
        "The Theory of Everything",
        "Quantum Mechanics",
        "Social Contract",
        "Cognitive Bias",
        "Paradigm Shift",
        "Heuristics",
        "Algorithm",
    ],
}

# Ontology definition for Phase 4
ONTOLOGY = {
    "entity_types": [
        "person",
        "organization",
        "location",
        "technology",
        "concept",
        "event",
        "project",
        "product",
    ],
    "predicate_types": {
        "works_at": {"source": "person", "target": "organization"},
        "located_in": {"source": ["person", "organization"], "target": "location"},
        "developed": {"source": ["person", "organization"], "target": ["technology", "concept", "product"]},
        "discovered": {"source": ["person", "organization"], "target": ["technology", "concept"]},
        "founded": {"source": "person", "target": "organization"},
        "uses": {
            "source": ["person", "organization"],
            "target": ["technology", "concept"],
        },
        "part_of": {"source": "*", "target": "*"},
        "leads": {"source": "person", "target": ["organization", "project"]},
        "wrote": {"source": "person", "target": "concept"},
        "published": {"source": ["person", "organization"], "target": "concept"},
        "created": {"source": ["person", "organization"], "target": ["technology", "concept", "product"]},
        "built": {"source": ["person", "organization"], "target": ["technology", "concept", "product"]},
        "designed": {"source": ["person", "organization"], "target": ["technology", "concept", "product"]},
        "implemented": {"source": ["person", "organization"], "target": ["technology", "concept"]},
        "manages": {"source": "person", "target": ["organization", "project", "technology"]},
        "joined": {"source": "person", "target": "organization"},
        "acquired": {"source": "organization", "target": ["organization", "product"]},
        "invested_in": {"source": ["person", "organization"], "target": "organization"},
        "held": {"source": ["person", "organization"], "target": "event"},
        "met_with": {"source": "person", "target": "person"},
        "strongly_related": {"source": "*", "target": "*"},
        "related_to": {"source": "*", "target": "*"},
        "co_occurs_with": {"source": "*", "target": "*"},
    },
}


def validate_predicate(subject_type: str, predicate: str, object_type: str) -> bool:
    """Checks if the relation is allowed according to the ontology.
    On violation: fallback to 'related_to' (no exception thrown)."""
    spec = ONTOLOGY["predicate_types"].get(predicate)
    if spec is None:
        return False
    if spec["source"] != "*" and subject_type not in (
        spec["source"] if isinstance(spec["source"], list) else [spec["source"]]
    ):
        return False
    if spec["target"] != "*" and object_type not in (
        spec["target"] if isinstance(spec["target"], list) else [spec["target"]]
    ):
        return False
    return True


def _get_prototype_embedding(
    emb_service: BaseEmbeddingService, texts: list[str]
) -> list[float]:
    key = "||".join(sorted(texts))
    if key in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[key]
    if not texts:
        result = [0.0] * 1024
        _EMBEDDING_CACHE[key] = result
        return result
    all_embs = [emb_service.embed_for_storage(t) for t in texts]
    avg = [sum(vals) / len(vals) for vals in zip(*all_embs)]
    _EMBEDDING_CACHE[key] = avg
    return avg


def is_content_phrase(words: list[str]) -> bool:
    """Check if a phrase contains at least one content word (not all stopwords/prepositions/verbs)."""
    if not words:
        return False
    content_count = 0
    for w in words:
        wl = w.lower().strip('.,;:!?()[]{}""')
        if not wl:
            continue
        if wl not in _STOPWORDS:
            content_count += 1
        if w[0].isupper() and wl not in _STOPWORDS:
            content_count += 2
    if content_count == 0:
        return False
    first_word = words[0].lower().strip('.,;:!?()[]{}""')
    if first_word in _PREPOSITION_STARTS or first_word in _VERB_STARTS:
        if content_count <= 1:
            return False
    return True


def extract_entities_with_spacy(text: str) -> list[dict]:
    """Extract entities using spaCy NER as primary source, with regex fallback."""
    nlp = _get_nlp()

    if nlp is not None:
        # Use spaCy as primary source
        doc = nlp(text)
        entities = []

        # Get named entities from spaCy
        for ent in doc.ents:
            entity_type = map_spacy_label_to_sieveon(ent.label_)
            entities.append(
                {
                    "name": ent.text,
                    "type": entity_type,
                    "label": ent.label_,
                    "confidence": 0.99,  # High confidence for spaCy entities
                }
            )

        # Also get noun chunks as additional candidates
        for chunk in doc.noun_chunks:
            # Skip if already captured as entity
            if any(chunk.text.lower() == ent["name"].lower() for ent in entities):
                continue

            words = chunk.text.split()
            # Skip sentence-length noun chunks (likely fragments, not entities)
            if len(words) > 5:
                continue
            # Skip chunks with a determiner in non-first position (sentence fragment)
            if len(words) >= 3 and any(
                w.lower() in ("the", "a", "an", "this", "that") for w in words[1:]
            ):
                continue

            entity_type = infer_entity_type(chunk.text)
            entities.append(
                {
                    "name": chunk.text,
                    "type": entity_type,
                    "label": "NOUN_CHUNK",
                    "confidence": 0.7,  # Medium confidence for noun chunks
                }
            )

        return entities
    else:
        # Fallback to regex-based extraction
        regex_entities = []
        noun_phrases = extract_noun_phrases(text)
        for phrase in noun_phrases:
            entity_type = infer_entity_type(phrase)
            regex_entities.append(
                {
                    "name": phrase,
                    "type": entity_type,
                    "label": "REGEX",
                    "confidence": 0.5,  # Lower confidence for regex
                }
            )

        return regex_entities


_GROQ_API_KEY = None

_DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"

# --- Local joint extraction backends (relex primary, gliner fallback) ---

_RELEX_MODEL = None
_GLINER_MODEL = None

_SIEVEON_ENTITY_LABELS = ["person", "organization", "location", "technology", "concept", "event"]

# Relation labels offered to the relex model at inference.
#
# This list is the label space: a predicate absent from it cannot be emitted
# at any confidence, so a gold set containing such predicates measures this
# configuration rather than the model. Six verbs were missing here
# (wrote, designed, built, funded, integrated, provides), which capped recall
# at 0.714 on docs/eval_triples_gold.jsonl and made `developed` look like a
# catch-all when it was mostly the nearest available broad label.
#
# Run scripts/audit_relation_labels.py after changing this. It is pure set
# arithmetic and takes a second.
#
# Kept as natural-language phrases because that is the format the model card
# documents; _normalize_relation_label slugs them for storage.
_SIEVEON_RELATION_LABELS = [
    # existing
    "works at", "located in", "created", "developed", "discovered",
    "uses", "leads", "acquired", "founded", "part of",
    # added 2026-10-02: were unreachable, see scripts/audit_relation_labels.py
    "wrote", "designed", "built", "funded", "integrated", "provides",
]


def _get_relex():
    """Lazy-load knowledgator/gliner-relex-multi-v1.0 (CUDA if available)."""
    global _RELEX_MODEL
    if _RELEX_MODEL is None:
        from gliner import GLiNER

        model = GLiNER.from_pretrained("knowledgator/gliner-relex-multi-v1.0")
        try:
            import torch

            if torch.cuda.is_available():
                model = model.to("cuda")
        except ImportError:
            pass
        model.eval()
        _RELEX_MODEL = model
    return _RELEX_MODEL


def _get_gliner():
    """Lazy-load fastino/gliner2.5-multi-v1 (multilingual, CUDA if available)."""
    global _GLINER_MODEL
    if _GLINER_MODEL is None:
        from gliner2 import AutoExtractor

        model = AutoExtractor.from_pretrained("fastino/gliner2.5-multi-v1")
        try:
            import torch

            if torch.cuda.is_available():
                model.cuda()
        except ImportError:
            pass
        model.eval()
        _GLINER_MODEL = model
    return _GLINER_MODEL


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _normalize_relation_label(label: str) -> str:
    """Map a zero-shot relation label to a Sieveon predicate slug."""
    slug = re.sub(r"[\s\-]+", "_", (label or "").strip().lower())
    return re.sub(r"[^a-z0-9_]", "", slug) or "related_to"


def extract_entities_with_relex(text: str) -> list[dict]:
    """Entities via local relex model. Returns [] on any failure (chain falls through)."""
    if not text or not text.strip():
        return []
    try:
        model = _get_relex()
        threshold = _env_float("RELEX_ENT_THRESHOLD", 0.5)
        raw = model.predict_entities(text, _SIEVEON_ENTITY_LABELS, threshold=threshold)
    except Exception as e:
        sys.stderr.write(f"[Relex] entity extraction failed: {e}\n")
        return []
    out = []
    for ent in raw or []:
        name = ent.get("text", "").strip() if isinstance(ent, dict) else str(ent).strip()
        if len(name) < 2:
            continue
        etype = (ent.get("label", "concept") if isinstance(ent, dict) else "concept").lower()
        conf = ent.get("score", 0.7) if isinstance(ent, dict) else 0.7
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.7
        out.append({"name": name, "type": etype, "label": "RELEX", "confidence": conf})
    return out


def extract_triples_with_relex(text: str) -> list[dict]:
    """Triples via local relex model (joint NER+RE, one forward pass)."""
    if not text or not text.strip():
        return []
    try:
        model = _get_relex()
        ent_thr = _env_float("RELEX_ENT_THRESHOLD", 0.5)
        rel_thr = _env_float("RELEX_REL_THRESHOLD", 0.7)
        _ents, rels = model.predict_relations(
            text, _SIEVEON_ENTITY_LABELS, _SIEVEON_RELATION_LABELS,
            threshold=ent_thr, relation_threshold=rel_thr,
        )
    except Exception as e:
        sys.stderr.write(f"[Relex] triple extraction failed: {e}\n")
        return []
    triples, seen = [], set()
    for rel in rels or []:
        try:
            head = rel["head"]["text"].strip()
            tail = rel["tail"]["text"].strip()
            pred = _normalize_relation_label(rel.get("relation", ""))
            conf = float(rel.get("score", 0.7))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if len(head) < 2 or len(tail) < 2 or head.lower() == tail.lower():
            continue
        key = f"{head.lower()}|{pred}|{tail.lower()}"
        if key in seen:
            continue
        seen.add(key)
        triples.append({"subject": head, "predicate": pred, "object": tail, "confidence": conf})
    return triples


def extract_entities_with_gliner(text: str) -> list[dict]:
    """Entities via local gliner2.5-multi (zero-shot, multilingual)."""
    if not text or not text.strip():
        return []
    try:
        model = _get_gliner()
        threshold = _env_float("GLINER_ENT_THRESHOLD", 0.5)
        import torch

        with torch.no_grad():
            raw = model.extract_entities(text, _SIEVEON_ENTITY_LABELS, threshold=threshold)
    except Exception as e:
        sys.stderr.write(f"[GLiNER] entity extraction failed: {e}\n")
        return []
    groups = raw.get("entities", {}) if isinstance(raw, dict) else {}
    out = []
    for label, items in (groups.items() if isinstance(groups, dict) else []):
        for it in items or []:
            name = (it if isinstance(it, str) else it.get("text", "")).strip()
            if len(name) < 2:
                continue
            out.append({"name": name, "type": label.lower(), "label": "GLINER", "confidence": 0.8})
    return out


def extract_triples_with_gliner(text: str) -> list[dict]:
    """Triples via local gliner2.5-multi relation head."""
    if not text or not text.strip():
        return []
    try:
        model = _get_gliner()
        rel_thr = _env_float("GLINER_REL_THRESHOLD", 0.7)
        import torch

        with torch.no_grad():
            raw = model.extract_relations(text, _SIEVEON_RELATION_LABELS, threshold=rel_thr)
    except Exception as e:
        sys.stderr.write(f"[GLiNER] triple extraction failed: {e}\n")
        return []
    groups = raw.get("relation_extraction", {}) if isinstance(raw, dict) else {}
    triples, seen = [], set()
    if isinstance(groups, dict):
        for label, pairs in groups.items():
            pred = _normalize_relation_label(label)
            for pair in pairs or []:
                try:
                    head, tail = pair[0].strip(), pair[1].strip()
                except (IndexError, TypeError, AttributeError):
                    continue
                if len(head) < 2 or len(tail) < 2 or head.lower() == tail.lower():
                    continue
                key = f"{head.lower()}|{pred}|{tail.lower()}"
                if key in seen:
                    continue
                seen.add(key)
                triples.append({"subject": head, "predicate": pred, "object": tail, "confidence": 0.7})
    return triples


def _get_groq_key() -> str | None:
    global _GROQ_API_KEY
    if _GROQ_API_KEY is None:
        _GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    return _GROQ_API_KEY if _GROQ_API_KEY else None


def _get_groq_model() -> str:
    """Groq chat model, override via GROQ_MODEL in .env."""
    return os.getenv("GROQ_MODEL", _DEFAULT_GROQ_MODEL)


_GROQ_SYSTEM_PROMPT = (
    "You are a precise entity extraction system. Identify every specific named entity in the text.\n\n"
    "OUTPUT FORMAT (one per line): name | type | confidence\n\n"
    "Valid types: person, organization, location, technology, concept, event\n\n"
    "RULES:\n"
    "1. Extract specific named entities: people, companies, products, places, benchmarks, laws/acts, dates\n"
    "2. Skip generic terms: job roles, common nouns, measurements, prices, standalone years, single generic words\n"
    "3. Universities, institutes, and colleges are organizations, not locations\n"
    "4. Generic event descriptions like 'conference' or 'meeting' without a proper name should be skipped\n"
    "5. Entity names MUST be short canonical forms (e.g. 'sieveon', not 'sieveon is a framework'). Never output full sentences, clauses, or phrases containing verbs as entity names.\n"
    "6. Confidence: 0.90-0.99 for clear proper names, 0.70-0.89 when ambiguous or partial\n"
    "7. Output ONLY the pipe lines — no greetings, no explanations, no markdown"
)

_GROQ_FEW_SHOT_EXAMPLES = """\
Text: Google released Gemini 2.0 and Microsoft launched Copilot.
Output:
Google | organization | 0.99
Gemini 2.0 | technology | 0.95
Microsoft | organization | 0.99
Copilot | technology | 0.90

Text: Anthropic's Claude 3.5 Sonnet scored 88% on SWE-bench.
Output:
Anthropic | organization | 0.99
Claude 3.5 Sonnet | technology | 0.99
SWE-bench | technology | 0.95"""


def extract_entities_with_groq(text: str) -> list[dict]:
    key = _get_groq_key()
    if not key:
        return []
    payload = {
        "model": _get_groq_model(),
        "messages": [
            {"role": "system", "content": _GROQ_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Examples:\n{_GROQ_FEW_SHOT_EXAMPLES}\n\nText: {text}\nOutput:",
            },
        ],
        "temperature": 0.0,
        "max_tokens": 512,
        # NOTE: kein "stop" hier -- gpt-oss-Modelle beenden sonst sofort
        # mit leerer Antwort (fuehrender Umbruch triggert "\n\n").
    }
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        sys.stderr.write(f"[Groq] entity extraction failed ({_get_groq_model()}): {e}\n")
        return []

    entities = []
    seen = set()
    for line in content.split("\n"):
        line = line.strip()
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2 or len(parts[0]) < 2:
            continue
        name = parts[0]
        etype = parts[1].lower()
        if etype not in {
            "person",
            "organization",
            "location",
            "technology",
            "concept",
            "event",
        }:
            etype = "concept"
        # Universities/institutes are organizations, not locations
        if etype == "location":
            lower = name.lower()
            if any(
                kw in lower
                for kw in (
                    "university",
                    "institute of technology",
                    "college",
                    "school of",
                    "institut",
                )
            ):
                etype = "organization"
        conf = 0.7
        if len(parts) >= 3:
            try:
                conf = min(1.0, max(0.0, float(parts[2])))
            except ValueError:
                pass
        key = f"{name.lower()}|{etype}"
        if key in seen:
            continue
        seen.add(key)
        entities.append(
            {"name": name, "type": etype, "label": "GROQ", "confidence": conf}
        )
    return entities


def extract_entities(text: str) -> list[dict]:
    """Dispatch entity extraction.

    Chain (default "auto"): relex (local, joint NER+RE model) -> gliner
    (local zero-shot NER) -> spacy (regex fallback inside). Groq is NOT in
    the default chain (API latency, retired-model risk); opt in explicitly
    with EXTRACTION_METHOD=groq.
    """
    method = os.getenv("EXTRACTION_METHOD", "auto")
    if method in ("relex", "auto"):
        entities = extract_entities_with_relex(text)
        if entities:
            return entities
    if method in ("gliner", "auto"):
        entities = extract_entities_with_gliner(text)
        if entities:
            return entities
    if method == "groq":
        entities = extract_entities_with_groq(text)
        if entities:
            return entities
    if method in ("trackb", "auto") and os.getenv("TRACKB_IN_AUTO", "1") == "1":
        entities = extract_entities_with_trackb(text)
        if entities:
            return entities
    return extract_entities_with_spacy(text)


def map_spacy_label_to_sieveon(spacy_label: str) -> str:
    """Map spaCy labels to sieveon entity types."""
    label_mapping = {
        "PERSON": "person",
        "ORG": "organization",
        "GPE": "location",  # Geopolitical entity (countries, cities, states)
        "LOC": "location",
        "PRODUCT": "technology",
        "EVENT": "event",
        "WORK_OF_ART": "concept",
        "NORP": "concept",  # Nationalities or religious or political groups
        "FAC": "location",  # Facilities
    }
    return label_mapping.get(spacy_label, "concept")


def infer_entity_type(
    name: str, embedding_service: Optional[BaseEmbeddingService] = None
) -> str:
    """Infer entity type using suffix heuristics (fast path) + embedding similarity (slow path)."""
    lower = name.lower().strip()

    if not lower:
        return "concept"

    if any(
        suffix in lower
        for suffix in [
            "corp",
            "inc",
            "ltd",
            "ltd",
            "company",
            "org",
            "ag",
            "llc",
            "corp.",
            "inc.",
            "ltd.",
            "& co",
            "e.l.l.c.",
        ]
    ):
        return "organization"
    if any(
        suffix in lower
        for suffix in [
            "gate",
            "system",
            "framework",
            "engine",
            "server",
            "protocol",
            "database",
            "platform",
            "service",
            "tool",
            "api",
            "sdk",
            "runtime",
            "client",
            "agent",
            "model",
            "code",
            "cli",
            "studio",
            "os",
            "suite",
            "app",
            "bot",
            "flash",
            "nano",
            "codex",
            "inference",
            "benchmark",
            "infer",
            "train",
            "dataset",
            "embedding",
            "vector",
            "reasoning",
            "token",
            "layer",
            "params",
            "neural",
            "transformer",
            "attention",
            "encoder",
            "decoder",
            "quantum",
            "blockchain",
        ]
    ):
        return "technology"
    if any(
        suffix in lower
        for suffix in [
            "theory",
            "effect",
            "mechanics",
            "technology",
            "principle",
            "rule",
            "law",
            "theorem",
            "axiom",
            "paradigm",
            "method",
            "algorithm",
            "concept",
        ]
    ):
        return "concept"
    if any(
        suffix in lower
        for suffix in ["street", "place", "avenue", "lane", "road", "way", "boulevard"]
    ):
        return "location"
    if any(
        prefix in lower
        for prefix in [
            "dr ",
            "mr ",
            "ms ",
            "mrs ",
            "prof ",
            "miss ",
            "sir ",
            "lord ",
            "lady ",
        ]
    ):
        return "person"

    if embedding_service is None:
        return "concept"

    # Result cache: entity types are stable, and each miss costs a full
    # model.encode (~110ms CPU). Heuristic hits above never reach this path.
    cache_key = lower
    cached = _INFER_TYPE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        name_emb = embedding_service.embed_for_storage(name)
        best_type = "concept"
        best_sim = -1.0

        for etype, prototypes in _ENTITY_PROTOTYPES.items():
            proto_emb = _get_prototype_embedding(embedding_service, prototypes)
            sim = sum(a * b for a, b in zip(name_emb, proto_emb))
            norm = (sum(a * a for a in name_emb) ** 0.5) * (
                sum(b * b for b in proto_emb) ** 0.5
            )
            if norm > 0:
                sim = sim / norm
            if sim > best_sim:
                best_sim = sim
                best_type = etype

        if len(_INFER_TYPE_CACHE) >= 2048:
            _INFER_TYPE_CACHE.clear()
        _INFER_TYPE_CACHE[cache_key] = best_type
        return best_type
    except Exception:
        return "concept"


def extract_noun_phrases(text: str) -> list[str]:
    """Extract noun phrases using simple pattern matching. Filters stopword-only phrases."""
    phrases = set()

    patterns = [
        r"\b(?:the|a|an|this|that|these|those)\s+"
        r"(?:[A-Z][a-z]+\s+)*[A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+))*\b",
        r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b",
        r"\b[A-Z][a-z]+[A-Z][a-zA-Z]*\b",
        r"\b[A-Z]{2,}\b",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidate = match.group(0).strip()
            words = candidate.split()
            if len(words) > 4:
                continue
            if len(candidate) < 3:
                continue
            if candidate.lower() in {"the", "and", "or"}:
                continue
            if not is_content_phrase(words):
                continue
            phrases.add(candidate)

    return list(phrases)


# SVO Extraction functions for Phase 2
PREDICATE_MAP = {
    "work": "works_at",
    "develop": "developed",
    "found": "founded",
    "create": "created",
    "use": "uses",
    "build": "built",
    "lead": "leads",
    "write": "wrote",
    "publish": "published",
    "implement": "implemented",
    "design": "designed",
    "manage": "manages",
    "join": "joined",
    "acquire": "acquired",
    "invest": "invested_in",
    "locate": "located_in",
    "hold": "held",
    "meet": "met_with",
}

_GROQ_TRIPLE_PROMPT = """You are a precise relationship extraction system. Extract every explicit subject-verb-object relationship from the text.

OUTPUT FORMAT (one per line): subject | predicate | object | confidence

Valid predicates: works_at, founded, developed, created, uses, built, leads, wrote, published, implemented, designed, manages, joined, acquired, invested_in, met_with, held, located_in, related_to, discovered, plans_to_open, investigates

RULES:
1. Subject and object MUST be specific named entities (people, organizations, products, places, events)
2. Never use generic nouns: paper, study, company, report, system, product, research, analysis
3. Map the text verb to the closest predicate; if none matches use related_to
4. Extract every explicit relationship — do not skip any
5. Output ONLY the pipe-delimited lines — no introductions, no explanations, no markdown
6. For passive voice (e.g. "X was created by Y"): output "Y | created | X | 0.99"""

_GROQ_TRIPLE_EXAMPLES = [
    ("Sam Altman founded OpenAI.", "Sam Altman | founded | OpenAI | 0.99"),
    (
        "Microsoft acquired Activision Blizzard.",
        "Microsoft | acquired | Activision Blizzard | 0.99",
    ),
    (
        "Elon Musk leads Tesla and SpaceX.",
        "Elon Musk | leads | Tesla | 0.99\nElon Musk | leads | SpaceX | 0.99",
    ),
    (
        "Satya Nadella is CEO of Microsoft. He met with Sundar Pichai at Davos.",
        "Satya Nadella | works_at | Microsoft | 0.99\nSatya Nadella | met_with | Sundar Pichai | 0.99",
    ),
    (
        "Apple held WWDC 2026 at Apple Park.",
        "Apple | held | WWDC 2026 | 0.99\nWWDC 2026 | located_in | Apple Park | 0.8",
    ),
    (
        "Marie Curie discovered radium and polonium.",
        "Marie Curie | discovered | radium | 0.99\nMarie Curie | discovered | polonium | 0.99",
    ),
    (
        "Rust was created by Graydon Hoare at Mozilla Research.",
        "Graydon Hoare | created | Rust | 0.99\nGraydon Hoare | works_at | Mozilla Research | 0.9",
    ),
    (
        "Acme Corp is planning to open an office in Barcelona next year.",
        "Acme Corp | plans_to_open | Barcelona | 0.8",
    ),
    (
        "Meta is planning to build a data center in Spain.",
        "Meta | plans_to_open | Spain | 0.8",
    ),
]


def findSVOs(doc):
    """Extract Subject-Verb-Object triples from spaCy doc using dependency parsing."""
    svos = []

    # Find root verbs and their dependents
    for token in doc:
        if token.dep_ in ["ROOT", "conj"] and token.pos_ == "VERB":
            subject = None
            direct_object = None

            # Find subject
            for child in token.children:
                if child.dep_ in ("nsubj", "nsubjpass"):
                    subject = child
                elif child.dep_ == "dobj":
                    direct_object = child

            # Handle passive voice
            if not subject:
                for child in token.children:
                    if child.dep_ == "nsubjpass":
                        subject = child

            # If we have both subject and object, create SVO
            if subject and direct_object:
                svos.append((subject.text, token.lemma_, direct_object.text))

                # Handle conjunctions in subjects or objects
                for child in subject.children:
                    if child.dep_ == "conj":
                        svos.append((child.text, token.lemma_, direct_object.text))

                for child in direct_object.children:
                    if child.dep_ == "conj":
                        svos.append((subject.text, token.lemma_, child.text))

    return svos


def extract_triples_with_spacy(text: str) -> list[dict]:
    """Extract SVO triples from text using spaCy dependency parsing."""
    nlp = _get_nlp()

    if nlp is None:
        return []

    doc = nlp(text)
    svos = findSVOs(doc)
    triples = []

    for subj, verb, obj in svos:
        if subj.lower() == obj.lower():
            continue
        predicate = PREDICATE_MAP.get(verb, "related_to")

        try:
            emb_service = get_embedding_service()
            subj_emb = emb_service.embed_for_storage(subj)
            obj_emb = emb_service.embed_for_storage(obj)

            dot_product = sum(a * b for a, b in zip(subj_emb, obj_emb))
            norm_a = sum(a * a for a in subj_emb) ** 0.5
            norm_b = sum(b * b for b in obj_emb) ** 0.5
            confidence = 0.0
            if norm_a > 0 and norm_b > 0:
                confidence = dot_product / (norm_a * norm_b)

            confidence = max(0.0, min(1.0, confidence))

            subj_type = infer_entity_type(subj)
            obj_type = infer_entity_type(obj)

            if not validate_predicate(subj_type, predicate, obj_type):
                predicate = "related_to"

            triples.append(
                {
                    "subject": subj,
                    "predicate": predicate,
                    "object": obj,
                    "confidence": confidence,
                }
            )
        except Exception:
            triples.append(
                {
                    "subject": subj,
                    "predicate": predicate,
                    "object": obj,
                    "confidence": 0.5,
                }
            )

    return triples


_GROQ_GENERIC_OBJECTS = {
    "paper",
    "study",
    "company",
    "report",
    "system",
    "product",
    "research",
    "analysis",
    "article",
    "document",
    "book",
    "chapter",
    "section",
    "page",
    "data",
    "information",
    "work",
    "project",
    "service",
    "platform",
    "tool",
    "application",
    "software",
    "hardware",
    "model",
    "algorithm",
    "method",
    "approach",
    "technique",
    "framework",
    "version",
    "release",
    "update",
    "patch",
    "build",
    "code",
    "website",
    "site",
    "page",
    "file",
    "document",
    "image",
    "video",
    "audio",
    "office",
    "branch",
    "department",
    "team",
    "division",
    "subsidiary",
    "headquarters",
    "solution",
}


def extract_triples_with_groq(text: str) -> list[dict]:
    key = _get_groq_key()
    if not key:
        return []

    messages = [{"role": "system", "content": _GROQ_TRIPLE_PROMPT}]
    for user_text, assistant_text in _GROQ_TRIPLE_EXAMPLES:
        messages.append({"role": "user", "content": user_text})
        messages.append({"role": "assistant", "content": assistant_text})
    messages.append({"role": "user", "content": text})

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json={
                "model": _get_groq_model(),
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": 2048,
            },
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        sys.stderr.write(f"[Groq] triple extraction failed ({_get_groq_model()}): {e}\n")
        return []

    triples = []
    seen = set()
    for line in content.split("\n"):
        line = line.strip()
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        subj, predicate, obj = parts[0], parts[1].lower(), parts[2]
        if len(subj) < 2 or len(obj) < 2:
            continue
        if subj.lower() == obj.lower():
            continue
        conf = 0.7
        if len(parts) >= 4:
            try:
                conf = min(1.0, max(0.0, float(parts[3])))
            except ValueError:
                pass
        key = f"{subj.lower()}|{predicate}|{obj.lower()}"
        if key in seen:
            continue
        seen.add(key)
        triples.append(
            {
                "subject": subj,
                "predicate": predicate,
                "object": obj,
                "confidence": conf,
            }
        )

    # Remove generic objects AND chain through intermediaries:
    # If X -> predicate -> generic_Y AND generic_Y -> located_in -> Z,
    # rewrite as X -> predicate -> Z (drop generic_Y)
    # First pass: collect triples involving generic entities
    generic_entities = {}
    for t in list(triples):
        subj_lower = t["subject"].lower()
        obj_lower = t["object"].lower()
        if obj_lower in _GROQ_GENERIC_OBJECTS:
            generic_entities.setdefault(obj_lower, []).append(t)
            triples.remove(t)
        elif subj_lower in _GROQ_GENERIC_OBJECTS:
            generic_entities.setdefault(subj_lower, []).append(t)
            triples.remove(t)

    # Build outgoing map: generic_name -> [target_entity, ...]
    generic_outgoing = {}
    for gen_name, gen_triples in generic_entities.items():
        for gt in gen_triples:
            if gt["predicate"] == "located_in" and gt["object"].lower() != gen_name:
                generic_outgoing.setdefault(gen_name, []).append(gt["object"])
            elif gt["predicate"] == "located_in" and gt["subject"].lower() != gen_name:
                generic_outgoing.setdefault(gen_name, []).append(gt["subject"])

    # Rewire: find triples pointing TO a generic, replace target with actual location
    rewired = []
    for gen_name, gen_triples in generic_entities.items():
        targets = generic_outgoing.get(gen_name, [])
        if not targets:
            continue
        for gt in gen_triples:
            is_incoming = gt["object"].lower() == gen_name
            if is_incoming:
                for target_obj in targets:
                    chain_key = f"{gt['subject'].lower()}|{gt['predicate']}|{target_obj.lower()}"
                    if chain_key not in seen:
                        seen.add(chain_key)
                        rewired.append({
                            "subject": gt["subject"],
                            "predicate": gt["predicate"],
                            "object": target_obj,
                            "confidence": round(gt["confidence"] * 0.9, 4),
                        })

    triples.extend(rewired)

    # Final filter: drop any remaining triples with generic entities
    final = []
    for t in triples:
        if t["object"].lower() in _GROQ_GENERIC_OBJECTS:
            continue
        if t["subject"].lower() in _GROQ_GENERIC_OBJECTS:
            continue
        final.append(t)

    return final


# --- Track B backend (NuExtract3 candidates + stepfun assertion) ---
# Frozen from trackb_two_stage_v1. Opt-in only via EXTRACTION_METHOD=trackb,
# mirroring the groq precedent: never in the "auto" chain, strict method
# semantics (explicit request returns this backend's output or nothing).
# Only relation covered: provides.

_TRACKB_NU_MODEL = "numind/nuextract3:q4_k_m"
_TRACKB_KILO_MODEL = "stepfun/step-3.7-flash:free"
_TRACKB_TEMPLATE = {"support_relations": [{"provider": "verbatim-string",
                                           "receiver": "verbatim-string"}]}
_TRACKB_VALIDATOR_PROMPT = (
    "Decide one binary question about the sentence below.\n"
    "Sentence: %s\n"
    "Question: Does this sentence assert that %s provides support, help, "
    "funding or encouragement to %s?\n"
    "Consider assertions only: offers, plans, intentions, wishes, questions, "
    "rumored/reported/alleged support, or encouragement directed at someone "
    "else do NOT count.\n"
    'Reply with ONLY this JSON: {"supported": true} or {"supported": false}'
)


def _get_kilo_key() -> str | None:
    return os.getenv("KILO_API_KEY") or None


def _trackb_normalize(mention: str) -> str:
    s = mention.strip()
    s = re.sub(r"^(the|a|an)\s+", "", s, flags=re.IGNORECASE)
    return s.strip()


def extract_triples_with_trackb(text: str) -> list[dict]:
    """Two-stage provides extraction: local candidates + API assertion check."""
    if not text or not text.strip():
        return []
    key = _get_kilo_key()
    if not key:
        sys.stderr.write("[trackb] KILO_API_KEY not set\n")
        return []
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    try:
        import json as _json
        payload = {
            "model": os.getenv("TRACKB_NU_MODEL", _TRACKB_NU_MODEL),
            "stream": False, "think": False,
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 256},
            "messages": [
                {"role": "template", "content": _json.dumps(_TRACKB_TEMPLATE)},
                {"role": "user", "content": text},
            ],
        }
        resp = requests.post(f"{ollama_url}/api/chat", json=payload, timeout=300)
        resp.raise_for_status()
        raw = resp.json()["message"]["content"]
        start, end = raw.index("{"), raw.rindex("}") + 1
        obj = _json.loads(raw[start:end])
        candidates = [(r.get("provider", ""), r.get("receiver", ""))
                      for r in obj.get("support_relations", []) or []
                      if isinstance(r, dict) and r.get("provider") and r.get("receiver")]
    except Exception as e:
        sys.stderr.write(f"[trackb] candidate extraction failed: {e}\n")
        return []
    triples, seen = [], set()
    for x, y in candidates:
        xs, ys = _trackb_normalize(x), _trackb_normalize(y)
        if len(xs) < 2 or len(ys) < 2 or xs.lower() == ys.lower():
            continue
        try:
            body = {
                "model": _TRACKB_KILO_MODEL, "stream": False, "temperature": 0,
                "messages": [{"role": "user", "content": _TRACKB_VALIDATOR_PROMPT % (text, x, y)}],
            }
            vresp = requests.post(
                "https://api.kilo.ai/api/gateway/chat/completions", json=body,
                headers={"Authorization": f"Bearer {key}"}, timeout=180)
            vresp.raise_for_status()
            vraw = vresp.json()["choices"][0]["message"]["content"]
            vs, ve = vraw.index("{"), vraw.rindex("}") + 1
            supported = bool(_json.loads(vraw[vs:ve]).get("supported"))
        except Exception as e:
            sys.stderr.write(f"[trackb] assertion check failed for {x!r}->{y!r}: {e}\n")
            continue
        if not supported:
            continue
        dedup = f"{xs.lower()}|provides|{ys.lower()}"
        if dedup in seen:
            continue
        seen.add(dedup)
        triples.append({"subject": xs, "predicate": "provides", "object": ys,
                        "confidence": 0.85,
                        "extractor": "trackb",
                        "provenance": {"candidate_source": "nuextract3",
                                       "validator": "stepfun"}})
    return triples


def extract_entities_with_trackb(text: str) -> list[dict]:
    """Entities from validated trackb triples (typed via infer_entity_type)."""
    out, seen = [], set()
    for t in extract_triples_with_trackb(text):
        for name in (t["subject"], t["object"]):
            key = name.lower()
            if key in seen or len(name) < 2:
                continue
            seen.add(key)
            out.append({"name": name, "type": infer_entity_type(name),
                        "label": "TRACKB", "confidence": t["confidence"]})
    return out


def extract_triples(text: str) -> list[dict]:
    """Dispatch triple extraction. Same chain as extract_entities (no Groq/trackb in auto).

    spaCy is deliberately NOT a fallback here (ADR-002). On the gold set it
    asserted 0 correct triples out of 15 (tripR 0.000): its dependency labels do
    not correspond to KG predicates, so every fact it contributes is wrong.
    Returning no triple is strictly better than returning a false one --
    retrieval can fail to find a fact that does not exist, but it will happily
    surface a fact that is false. spaCy still backs entity extraction
    (entR 0.981); only the triple chain is gated.

    An explicit EXTRACTION_METHOD is also honoured strictly: requesting "relex"
    returns relex's output or nothing, rather than silently downgrading to a
    weaker backend.
    """
    if not text or not text.strip():
        return []

    method = os.getenv("EXTRACTION_METHOD", "auto")

    if method == "auto" and os.getenv("TRACKB_IN_AUTO", "1") == "1":
        # Standard pipe: union of the classic chain with trackb provides.
        # Track B covers only provides; all other predicates still come
        # from relex/gliner. Failures degrade to the classic result.
        triples = extract_triples_with_relex(text) or []
        if not triples:
            triples = extract_triples_with_gliner(text) or []
        seen = {f"{t['subject'].lower()}|{t['predicate']}|{t['object'].lower()}"
                for t in triples}
        for t in extract_triples_with_trackb(text):
            key = f"{t['subject'].lower()}|{t['predicate']}|{t['object'].lower()}"
            if key not in seen:
                seen.add(key)
                triples.append(t)
        return triples
    if method in ("relex", "auto"):
        triples = extract_triples_with_relex(text)
        if triples:
            return triples
    if method in ("gliner", "auto"):
        triples = extract_triples_with_gliner(text)
        if triples:
            return triples
    if method == "groq":
        triples = extract_triples_with_groq(text)
        if triples:
            return triples
    if method == "trackb":
        triples = extract_triples_with_trackb(text)
        if triples:
            return triples
    return []


