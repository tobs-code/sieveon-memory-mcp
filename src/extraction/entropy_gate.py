"""
sieveon - Entropy Gate
Composite Score aus Text-Entropy und Embedding-Novelty
Nur vor KG-Write, Raw Event Log bekommt immer alles!
"""

import gzip
import hashlib
import logging
import math
import os
import re
import sys
from collections import Counter
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables: project .env by explicit path first (bare
# load_dotenv resolves caller-relative and silently picked up parent .env
# files without GROQ_API_KEY for out-of-tree scripts). No override.
_project_env = Path(__file__).resolve().parents[2] / ".env"
if _project_env.exists():
    load_dotenv(dotenv_path=_project_env)
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.extraction.embedding_service import BaseEmbeddingService, get_embedding_service
from src.extraction.entity_utils import (
    extract_noun_phrases,
    infer_entity_type,
    is_content_phrase,
)


_shared_http_client = None


def _get_http_client() -> httpx.Client:
    global _shared_http_client
    if _shared_http_client is None:
        _shared_http_client = httpx.Client(timeout=httpx.Timeout(30.0))
    return _shared_http_client


def escape_surrealql(value: str) -> str:
    """Escape a string for safe use in a SurrealQL string literal.

    Escapes BOTH quote styles, not just ``'``. Several call sites interpolate
    the result into double-quoted literals (``type::datetime("...")``); while
    ``\\'`` protects a single-quoted context it does nothing for a
    double-quoted one, so a value containing ``"`` broke out of the literal
    there (verified against SurrealDB 3.x: ``type::datetime("a" OR 1=1 --")``
    reached the parser and failed on ``expected this delimiter to close``).

    SurrealQL treats backslash as an active escape character inside
    double-quoted strings too, so ``\\"`` collapses back to ``"`` on store and
    adding it here does not corrupt values written to single-quoted literals
    (verified round-trip: ``he said "hi" and it's fine``).

    Table/record identifiers cannot be escaped this way at all -- those must be
    validated against a strict shape instead (see ``_is_record_id``) or bound as
    parameters.
    """
    import re

    value = value.replace("\\", "\\\\")
    value = value.replace("'", "\\'")
    value = value.replace('"', '\\"')
    value = value.replace("}", "\\}")
    value = value.replace("\n", "\\n")
    value = value.replace("\r", "\\r")
    value = value.replace("\t", "\\t")
    value = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", value)
    return value


def sanitize_fts_query(value: str) -> str:
    """Prepare plain text for SurrealDB FTX matching (@@ operator).

    FTS query syntax treats characters like ? ! : + - " * ( ) as operators;
    a natural question ("When did X?") then silently matches NOTHING.
    Verified 2026-09-30: full question with ? -> 0 rows, same text without
    ? -> rows. The analyzer tokenizes anyway, so replacing everything but
    alphanumerics/whitespace with spaces cannot hurt matching. Use ONLY for
    plain-text search; explicit 'fts'/'exact' modes keep user syntax.
    """
    import re

    cleaned = "".join(ch if (ch.isalnum() or ch == " ") else " " for ch in (value or ""))
    return re.sub(r"[ ]+", " ", cleaned).strip()


_FTS_STOPWORDS = frozenset(
    # Question words + articles/prepositions/conjunctions: they carry no
    # retrieval signal and (with SurrealDB's AND-like @@ matching) actively
    # kill result sets. Content terms do the matching; BM25 ranks them.
    "when did do does is are was were what which where who whom whose how why"
    " can could would should will shall may the a an to of in on and or for with"
    " from by at as is are be been being this that these those it its it’s its"
    " der die das und ist sind war waren wird werden hat haben hatte hatten nicht"
    " ein eine einer einem einen denn oder aber für von zum zur im am an auf aus"
    " bei mit nach seit von vom wer was welche welcher welches wo wohin wie warum"
    " wann wen wem wessen denn doch nur schon sehr".split()
)


def fts_keywords(value: str, min_len: int = 3) -> str:
    """Reduce a natural query to content-bearing keywords for FTX matching.

    SurrealDB's @@ is strict AND over analyzed terms (verified 2026-09-30
    live: `caroline zzzznotaword` -> 0 rows while `caroline` alone -> all).
    Callers therefore match with @OR@ and rank by BM25; this helper just
    drops the terms that would only add noise to that ranking.
    Falls back to the sanitized full text when nothing survives.
    """
    words = [
        w for w in sanitize_fts_query(value).lower().split()
        if w not in _FTS_STOPWORDS and len(w) >= min_len
    ]
    # De-duplicate while preserving order (repeated terms add no signal).
    seen, unique = set(), []
    for w in words:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return " ".join(unique) or sanitize_fts_query(value)


def _debug_print(*args, **kwargs):
    """Print to stderr to avoid breaking MCP JSON-RPC on stdout."""
    print(*args, file=sys.stderr, **kwargs)


def character_diversity(text: str) -> float:
    """Unique chars ratio: len(set(text)) / len(text). < 0.15 = repetitive noise."""
    if not text:
        return 0.0
    unique = len(set(text.lower()))
    return unique / len(text)


# Fact salience v1 (heuristic, 2026-09-30): scores an extracted fact 0..1 from
# signals available at extraction time. Logged in parallel to the (deprecated)
# composite gate score; no behavior change yet -- every fact is still created.
SALIENCE_VERSION = "v1-heuristic"

# Tiering (active since calibration 2026-09-30): co-occurrence facts below
# TIER_DROP_THRESHOLD are not created as KG facts (mentions stay as
# provenance). SVO facts and mentions are never tiered. 0 disables.
DEFAULT_TIER_DROP_THRESHOLD = 0.50


def tier_threshold() -> float:
    """Read TIER_DROP_THRESHOLD from env (default 0.50, 0 = disabled)."""
    try:
        return max(0.0, float(os.getenv("TIER_DROP_THRESHOLD", DEFAULT_TIER_DROP_THRESHOLD)))
    except (TypeError, ValueError):
        return DEFAULT_TIER_DROP_THRESHOLD


def tier_keep(salience: float, threshold: Optional[float] = None) -> bool:
    """Pure tier decision: keep the KG fact iff salience >= threshold."""
    thr = threshold if threshold is not None else tier_threshold()
    if thr <= 0.0:
        return True
    try:
        return float(salience) >= thr
    except (TypeError, ValueError):
        return True


def infer_extractor(entity_labels: List[str]) -> str:
    """Derive which backend produced extraction output from entity labels.

    entity_utils tags entities with their source (RELEX/GLINER/GROQ/spaCy
    NER tags/NOUN_CHUNK/REGEX). Majority vote; ties and unknowns fall back
    to spacy (the weakest-evidence tier). Pure function.
    """
    votes = Counter(
        "relex" if str(lbl).upper() == "RELEX"
        else "gliner" if str(lbl).upper() == "GLINER"
        else "groq" if str(lbl).upper() == "GROQ"
        else "spacy"
        for lbl in (entity_labels or [])
    )
    if not votes:
        return "spacy"
    top = votes.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        return "spacy"
    return top[0][0]

# Predicate specificity: generic co-occurrence predicates carry less signal
# than explicit SVO predicates. Unknown predicates are assumed specific (1.0).
_PREDICATE_SPECIFICITY = {
    "mentions": 0.2,
    "weakly_related": 0.2,
    "co_occurs_with": 0.4,
    "related_to": 0.4,
    "strongly_related": 0.5,
}


class EntropyGateConfig:
    def __init__(
        self,
        alpha: float = 0.25,  # Gewicht Shannon-Entropy
        beta: float = 0.50,  # Gewicht Embedding-Novelty
        gamma: float = 0.25,  # Gewicht Kompressionsrate (Kolmogorov-Approx)
        base_threshold: float = 0.30,  # Minimum threshold (cold start)
        max_threshold: float = 0.55,  # Maximum threshold (mature DB)
        ramp_events: int = 150,  # Events needed to reach max_threshold
        min_length: int = 10,  # Unter X Zeichen immer skippen
        min_diversity: float = 0.15,  # Anteil unique chars; repetitive Texte darunter skippen
        max_length: int = 2000,  # Über X Zeichen immer skippen
        min_novelty: float = 0.20,  # Mindest-Novelty (1 - avg_sim); darunter = near-dup flag
        base_min_novelty: float = 0.05,  # Novelty-Schwelle bei kaltem Start
        max_entities_for_cooccurrence: int = 6,  # Obergrenze gegen kombinatorische Explosion
    ):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.base_threshold = base_threshold
        self.max_threshold = max_threshold
        self.ramp_events = ramp_events
        self.min_length = min_length
        self.max_length = max_length
        self.min_diversity = min_diversity
        self.min_novelty = min_novelty
        self.base_min_novelty = base_min_novelty
        self.max_entities_for_cooccurrence = max_entities_for_cooccurrence


# Predicates asserting that something happened. A copular frame states what
# something IS ("John is a member of a club"), so it cannot license any of
# these. Measured, not assumed: see scripts/eval_structural_gates.py and the
# "Structural gating" section of docs/adr/ADR-004-triple-precision.md.
_EVENT_PREDICATES = frozenset({
    "built", "founded", "created", "developed", "acquired",
    "discovered", "designed", "funded", "integrated", "joined",
})

_COPULAR_RE = None


def _copular_event_rejected(text: str, predicate: str) -> bool:
    """Whether a copular frame rules out this triple.

    "Andrew is a person living in an apartment" licenses part_of, never
    `built`. Returns True when the sentence is copular and the predicate
    asserts an event, hence the triple is rejected. Narrowly scoped: it must
    not reject `part_of` or `located_in`, which a copular sentence can and
    does license.
    """
    global _COPULAR_RE
    if _COPULAR_RE is None:
        import re as _re
        _COPULAR_RE = _re.compile(r"\b(is|are|was|were)\s+(a|an|the)\b", _re.I)
    if predicate not in _EVENT_PREDICATES:
        return False
    return bool(_COPULAR_RE.search(text or ""))


class EntropyGate:
    def __init__(
        self,
        embedding_service: Optional[BaseEmbeddingService] = None,
        config: Optional[EntropyGateConfig] = None,
        ns: Optional[str] = None,
        db: Optional[str] = None,
    ):
        self.config = config or EntropyGateConfig()
        self.min_length = self.config.min_length
        self.max_length = self.config.max_length
        self.surreal_url = os.getenv("SURREALDB_URL", "http://127.0.0.1:8000/sql")
        self.auth = (
            os.getenv("SURREALDB_USER", "root"),
            os.getenv("SURREALDB_PASS", "root"),
        )
        # Explicit ns/db win (namespace isolation for eval harnesses);
        # otherwise env, otherwise the sieveon default. NOTE: this snapshots
        # at construction -- callers that switch namespaces must construct a
        # new gate (see common_logic._get_entropy_gate).
        self.surreal_ns = ns or os.getenv("SURREALDB_NS", "sieveon")
        self.surreal_db = db or os.getenv("SURREALDB_DB", "sieveon")
        self.embedding_service = embedding_service or get_embedding_service()

    def _query_surreal(self, sql: str) -> List[Dict]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "text/plain; charset=utf-8",
        }
        full_sql = f"USE NS {self.surreal_ns} DB {self.surreal_db};\n{sql}"
        client = _get_http_client()
        try:
            response = client.post(
                self.surreal_url,
                content=full_sql.encode("utf-8"),
                headers=headers,
                auth=self.auth,
            )
            data = response.json()
            if isinstance(data, list):
                return data
            else:
                return [data]
        except Exception as e:
            print(f"SurrealDB query failed: {e}")
            return []

    def _escape_surrealql(self, value: str) -> str:
        return escape_surrealql(value)

    @staticmethod
    def _extract_result(data: Any, index: int = 1) -> List[Dict]:
        """Safely extract the result list from a SurrealDB multi-statement response.
        Filters out USE NS/DB connection-info responses and None entries.

        Index-Konvention (P4): Jeder Aufruf in dieser Klasse sendet genau EIN
        Statement (der USE-Prefix wird vorher herausgefiltert, s. Filter unten),
        daher ist candidates[0] immer das eigene Statement. index != 1 nimmt
        candidates[-1] (letztes) -- das ist nur Fallback für mehrteilige Batches
        und wird aktuell nirgends mit index != 1 aufgerufen. Wer hier jemals
        echte Multi-Statement-Batches parsen will: nicht über den Index, sondern
        über explizite Statement-Marker gehen.
        """
        if not isinstance(data, list):
            return []
        candidates = [
            item
            for item in data
            if isinstance(item, dict)
            and item.get("status") == "OK"
            and "result" in item
            and not (
                isinstance(item.get("result"), dict)
                and "database" in item["result"]
                and "namespace" in item["result"]
            )
        ]
        if not candidates:
            return []
        target = candidates[0] if index == 1 and len(candidates) >= 1 else candidates[-1]
        result = target.get("result", [])
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
        return []

    @staticmethod
    def _extract_ok(data: List[Dict], index: int = 1) -> bool:
        """Safely check if a SurrealDB statement returned status OK.
        Scans all entries starting from index to find first OK result."""
        if not isinstance(data, list):
            return False
        for i in range(index, len(data)):
            item = data[i]
            if isinstance(item, dict) and item.get("status") == "OK":
                return True
        return False

    def _hash_content(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def calculate_char_entropy(self, text: str) -> float:
        """
        Shannon-Entropy auf Zeichenebene (Eigenbau, NICHT LightMem --
        siehe Modul-Docstring).
        Returns *unnormalized* entropy (typically 0-4.5)
        """
        if not text:
            return 0.0
        freq = {}
        chars = list(text.lower())
        n = len(chars)
        if n == 0:
            return 0.0
        for c in chars:
            if c.isalnum() or c.isspace():
                freq[c] = freq.get(c, 0) + 1
        total = sum(freq.values())
        if total == 0:
            return 0.0
        entropy = 0.0
        for count in freq.values():
            p = count / total
            entropy -= p * math.log2(p)
        return entropy

    def calculate_compression_ratio(self, text: str) -> float:
        """
        Kolmogorov-Komplexitäts-Approximation via gzip-Kompressionsrate.
        Höhere Werte = schlechter komprimierbar = höherer Informationsgehalt.
        Returns Wert zwischen 0 und 1 (normalisiert auf uncompressed=1.0).
        Bei Kurztexten < 20 Zeichen instabil → Fallback auf 0.5.
        """
        if not text or len(text) < 20:
            return 0.5
        data = text.encode("utf-8")
        compressed = gzip.compress(data, mtime=0)
        ratio = len(compressed) / len(data)
        return min(ratio, 1.0)

    def _get_adaptive_min_novelty(self) -> float:
        """min_novelty steigt linear von base_min_novelty → min_novelty mit der Event-Anzahl."""
        n = self._count_events()
        base = self.config.base_min_novelty
        maximum = self.config.min_novelty
        ramp = self.config.ramp_events
        if ramp <= 0:
            return maximum
        fraction = min(n / ramp, 1.0)
        return base + (maximum - base) * fraction

    def calculate_novelty(
        self,
        text: str,
        exclude_id: Optional[str] = None,
        embedding: Optional[List[float]] = None,
    ) -> float:
        """
        Novelty based on embedding similarity against existing content in SurrealDB.
        Returns value between 0 (no novelty) and 1 (maximum novelty).
        Uses SurrealDB's native vector functions.
        exclude_id: if provided, excludes the event with this id (prevents self-match).
        embedding: precomputed storage embedding for `text` (saves one model call
        when the caller already embedded it, e.g. _ingest_impl for the CREATE).
        """
        if not text.strip():
            return 0.0

        # Generate embedding for the text (or reuse the caller's)
        embedding = (
            embedding
            if embedding is not None
            else self.embedding_service.embed_for_storage(text)
        )
        emb_str = "[" + ", ".join(map(str, embedding)) + "]"

        # Search for top-k similar vectors in SurrealDB
        # We use cosine similarity and calculate 1.0 - avg_similarity for novelty
        # Self-match exclusion MUST use the record literal (id != event:xxx):
        # id != 'event:xxx' (string) never matches a record id in SurrealDB v3,
        # so the quoted form silently kept the self-match (sim 1.0) in top-5 and
        # dragged every novelty down by up to 0.2. Verified empirically.
        exclude_self = ""
        if exclude_id and re.fullmatch(r"[A-Za-z0-9_]+:[A-Za-z0-9_]+", exclude_id):
            exclude_self = f"\n  AND id != {exclude_id}"
        sql = f"""
        SELECT vector::similarity::cosine(embedding, {emb_str}) AS similarity
        FROM event
        WHERE embedding IS NOT NONE
          AND array::len(embedding) = {len(embedding)}
          AND forgotten = false{exclude_self}
        ORDER BY similarity DESC
        LIMIT 5;
        """

        results = self._query_surreal(sql)

        actual_results = self._extract_result(results)

        if not actual_results:
            # No similar content found - maximum novelty
            return 1.0

        # Calculate average similarity (lower = more novel)
        avg_similarity = sum(float(r["similarity"]) for r in actual_results) / len(
            actual_results
        )

        # Return inverse (novelty = 1 - similarity)
        return 1.0 - max(0.0, min(1.0, avg_similarity))

    def _count_events(self) -> int:
        """Count total stored events (for adaptive threshold).

        Cached with a short TTL: the adaptive ramp (0.30 -> 0.55 over 150
        events) is insensitive to slightly stale counts, and uncached this
        costs one HTTP roundtrip per call -- should_extract used to pay it
        three times per store (min_novelty ramp, threshold, log threshold).
        """
        import time as _time

        now = _time.monotonic()
        cached = getattr(self, "_event_count_cache", None)
        if cached is not None:
            value, ts = cached
            if now - ts < 60.0:
                return value
        value = self._count_events_uncached()
        self._event_count_cache = (value, now)
        return value

    def _count_events_uncached(self) -> int:
        try:
            sql = "SELECT count() AS c FROM event WHERE forgotten = false LIMIT 1;"
            result = self._query_surreal(sql)
            rows = self._extract_result(result)
            if rows:
                return rows[0].get("c", 0)
        except Exception:
            # Falling back to 0 lowers the adaptive threshold, i.e. more content
            # gets through the gate -- a safe direction, but not a silent one.
            logging.warning("Event count query failed; assuming an empty store",
                            exc_info=True)
        return 0

    def invalidate_count_cache(self) -> None:
        """Drop the cached event count (e.g. after bulk imports in tests)."""
        self._event_count_cache = None

    def _get_adaptive_threshold(self) -> float:
        """Threshold steigt linear von base_threshold → max_threshold mit der Event-Anzahl."""
        n = self._count_events()
        bt = self.config.base_threshold
        mt = self.config.max_threshold
        ramp = self.config.ramp_events
        if ramp <= 0:
            return mt
        fraction = min(n / ramp, 1.0)
        return bt + (mt - bt) * fraction

    @staticmethod
    def _character_diversity(text: str) -> float:
        return character_diversity(text)

    @staticmethod
    def _word_diversity(text: str) -> float:
        """Word-level diversity: len(set(words)) / len(words). < 0.20 = repetitive."""
        words = text.lower().split()
        if not words:
            return 0.0
        return len(set(words)) / len(words)

    def should_extract(
        self,
        text: str,
        exclude_id: Optional[str] = None,
        embedding: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Entscheidet basierend auf Composite-Score ob Text in KG extrahiert werden soll
        exclude_id: event_id, die von der Novelty-Berechnung ausgeschlossen wird (Self-Match)
        embedding: optional precomputed storage embedding (saves one model call)

        Logging-Konvention (Kalibrierung): Guardrail-Skips loggen die echten
        billigen Scores (entropy, compression), aber novelty=0.0/gate_score=0.0
        weil kein Composite existiert. Filter in Analysen: decision='skip'
        (Guardrail, reason=too_short/too_long/too_repetitive) vs. 'ignore'
        (echter Composite unter Threshold) vs. 'extract'.

        DEPRECATED (2026-09-30): Der Composite-Score trennt auf echten Daten
        nichts (Entropy ~konstant, Threshold bindet nie, Gewichte egal).
        Guardrails bleiben; daneben wird pro Fact fact_salience()
        (v1-heuristic) geloggt. Sobald beide Scores nebeneinander in gate_log
        liegen, wird umgeschaltet. Bis dahin: Verhalten unveraendert.
        """
        # Billige Scores zuerst: rein lokal, kein Embedding, kein DB-Zugriff.
        # Sie werden auch bei Guardrail-Skips geloggt (P2), damit gate_log
        # kalibrierbar bleibt statt 0.0-Zeilen zu enthalten.
        text_entropy = self.calculate_char_entropy(text)
        compression_ratio = self.calculate_compression_ratio(text)
        normalized_entropy = min(text_entropy / 4.5, 1.0)

        if len(text) < self.config.min_length:
            result = {
                "decision": "skip",
                "reason": "text_too_short",
                "text_length": len(text),
                "min_length": self.config.min_length,
            }
            result["gate_log_id"] = self._log_decision(
                text,
                normalized_entropy,
                0.0,
                0.0,
                result["decision"],
                reason_override=result["reason"],
                compression_ratio=compression_ratio,
            )
            return result
        if len(text) > self.config.max_length:
            result = {
                "decision": "skip",
                "reason": "text_too_long",
                "text_length": len(text),
                "max_length": self.config.max_length,
            }
            result["gate_log_id"] = self._log_decision(
                text,
                normalized_entropy,
                0.0,
                0.0,
                result["decision"],
                reason_override=result["reason"],
                compression_ratio=compression_ratio,
            )
            return result

        # Diversity-Check: character-level für Kurztexte, word-level für längere
        # Character diversity skaliert nicht mit Textlänge (Englisch hat nur ~36 unique chars)
        if len(text) <= 150:
            diversity = self._character_diversity(text)
            threshold = self.config.min_diversity
            if diversity < threshold:
                result = {
                    "decision": "skip",
                    "reason": "too_repetitive",
                    "character_diversity": diversity,
                    "threshold": threshold,
                }
                result["gate_log_id"] = self._log_decision(
                    text,
                    normalized_entropy,
                    0.0,
                    0.0,
                    result["decision"],
                    reason_override=result["reason"],
                    compression_ratio=compression_ratio,
                )
                return result
        else:
            diversity = self._word_diversity(text)
            threshold = 0.20
            if diversity < threshold:
                result = {
                    "decision": "skip",
                    "reason": "too_repetitive",
                    "word_diversity": diversity,
                    "threshold": threshold,
                }
                result["gate_log_id"] = self._log_decision(
                    text,
                    normalized_entropy,
                    0.0,
                    0.0,
                    result["decision"],
                    reason_override=result["reason"],
                    compression_ratio=compression_ratio,
                )
                return result

        # Teure Scores: Embedding-Novelty (Model-Call + Vector-Search).
        # Erst hier, nachdem alle billigen Guardrails passiert sind.
        novelty = self.calculate_novelty(
            text, exclude_id=exclude_id, embedding=embedding
        )

        # Near-duplicate guard (soft): falls novelty zu niedrig ist,
        # wird das trotzdem durch den Composite-Score bewertet (kein Hard-Skip mehr).
        # Der adaptive min_novelty-Wert dient als Warning-Flag, blockt aber nicht.
        adaptive_min_novelty = self._get_adaptive_min_novelty()
        near_duplicate_warning = novelty < adaptive_min_novelty

        # Calculate composite score: Shannon + Kompressionsrate + Embedding-Novelty
        # (normalized_entropy wurde oben bereits aus text_entropy berechnet)
        composite_score = (
            self.config.alpha * normalized_entropy
            + self.config.gamma * compression_ratio
            + self.config.beta * novelty
        )

        # Adaptive threshold based on DB maturity
        threshold = self._get_adaptive_threshold()

        # Make decision
        decision = "extract" if composite_score >= threshold else "ignore"

        # Log decision to database
        gate_log_id = self._log_decision(text, normalized_entropy, novelty, composite_score, decision, compression_ratio=compression_ratio, threshold=threshold)

        return {
            "decision": decision,
            "gate_log_id": gate_log_id,
            "text_entropy": text_entropy,
            "normalized_entropy": normalized_entropy,
            "compression_ratio": compression_ratio,
            "novelty": novelty,
            "composite_score": composite_score,
            "threshold": threshold,
            "alpha": self.config.alpha,
            "beta": self.config.beta,
            "gamma": self.config.gamma,
            "near_duplicate_warning": near_duplicate_warning,
            "adaptive_min_novelty": adaptive_min_novelty,
            "reason": f"Composite score {composite_score:.3f} {'meets' if decision == 'extract' else 'does not meet'} threshold {threshold:.3f}",
        }

    def _log_decision(
        self,
        text: str,
        entropy: float,
        novelty: float,
        composite_score: float,
        decision: str,
        reason_override: Optional[str] = None,
        compression_ratio: float = 0.0,
        threshold: Optional[float] = None,
    ) -> Optional[str]:
        """Log the entropy gate decision to database. Returns the gate_log record id."""
        try:
            content_hash = self._hash_content(text)
            decision_escaped = self._escape_surrealql(decision)
            # Reuse the caller's threshold when available: computing it here
            # costs another COUNT query per store and can even disagree with
            # the threshold the decision was made against.
            threshold = (
                threshold if threshold is not None else self._get_adaptive_threshold()
            )
            if reason_override:
                reason = reason_override
            else:
                reason = f"Composite score {composite_score:.3f} {'meets' if decision == 'extract' else 'does not meet'} threshold {threshold:.3f}"
            reason_escaped = self._escape_surrealql(reason)
            sql = f"""
            CREATE gate_log SET
                content_hash = '{content_hash}',
                text_score = {entropy},
                novelty = {novelty},
                compression_ratio = {compression_ratio},
                gate_score = {composite_score},
                decision = '{decision_escaped}',
                reason = '{reason_escaped}',
                threshold = {threshold};
            """
            result = self._query_surreal(sql)
            if not self._extract_ok(result):
                import sys

                sys.stderr.write(f"[Gate] _log_decision failed: {result}\n")
                return None
            rows = self._extract_result(result)
            if rows and isinstance(rows[0], dict):
                return rows[0].get("id")
            return None
        except Exception as e:
            import sys

            sys.stderr.write(f"[Gate] _log_decision exception: {e}\n")
            return None

    def _extract_candidate_entities(self, text: str) -> List[str]:
        """
        Extract candidate entities from text.
        Uses spaCy NER as primary source, with regex fallback.
        """
        import re as _re

        # Try Groq/spaCy-based extraction first
        try:
            from src.extraction.entity_utils import extract_entities

            entities = extract_entities(text)
            candidates = {entity["name"] for entity in entities}
        except ImportError:
            # If neither is available, fall back to original regex approach
            candidates = set()

        # If spaCy is not available or returns no entities, use original approach as fallback
        if not candidates:
            # 1. Noun-Phrase-Extraktion
            noun_phrases = extract_noun_phrases(text)
            for phrase in noun_phrases:
                candidates.add(phrase)

            # 2. Kleingeschriebene mehrteilige Konzepte (z.B. "quantum computing", "social contract")
            concept_patterns = [
                _re.compile(r"\b[a-z]{3,}(?:\s+[a-z]{3,}){1,2}\b"),
            ]
            for pattern in concept_patterns:
                for match in pattern.finditer(text):
                    candidate = match.group(0).strip()
                    words = candidate.split()
                    if len(words) >= 2 and len(candidate) >= 5:
                        if is_content_phrase(words):
                            candidates.add(candidate)

            # 3. CamelCase-Wörter (z.B. "FastMCP", "SurrealDB")
            for match in _re.finditer(r"\b([A-Z][a-z]+[A-Z][a-zA-Z]*)\b", text):
                candidate = match.group(1).strip()
                if len(candidate) >= 3:
                    candidates.add(candidate)

            # 4. Abkürzungen (z.B. "API", "NER", "KG")
            for match in _re.finditer(r"\b([A-Z]{2,})\b", text):
                candidate = match.group(1).strip()
                if len(candidate) >= 2:
                    candidates.add(candidate)

        return list(candidates)

    def _compute_relation_confidence(
        self, text: str, entity_a: str, entity_b: str,
        emb_a: Optional[List[float]] = None,
        emb_b: Optional[List[float]] = None,
    ) -> tuple[str, float]:
        """Berechne dynamische Konfidenz und Relationstyp zwischen zwei Entities basierend auf Embedding.
        Wenn emb_a/emb_b übergeben werden, werden diese genutzt (erspart wiederholte Embedding-Calls)."""
        emb_service = self.embedding_service
        try:
            if emb_a is None:
                emb_a = emb_service.embed_for_storage(entity_a)
            if emb_b is None:
                emb_b = emb_service.embed_for_storage(entity_b)
            dot = sum(a * b for a, b in zip(emb_a, emb_b))
            norm = (sum(a * a for a in emb_a) ** 0.5) * (
                sum(b * b for b in emb_b) ** 0.5
            )
            similarity = dot / norm if norm > 0 else 0.0
            confidence = max(0.0, min(1.0, similarity))
            label = self._infer_relation_type(text, entity_a, entity_b, confidence)
            return label, confidence
        except Exception:
            return "co_occurs_with", 0.5

    def _infer_relation_type(
        self, text: str, entity_a: str, entity_b: str, confidence: float
    ) -> str:
        """Determine the relationship type between two entities.
        Validates against ontology to avoid nonsensical predicates."""
        from src.extraction.entity_utils import infer_entity_type, validate_predicate

        a_type = infer_entity_type(entity_a, self.embedding_service)
        b_type = infer_entity_type(entity_b, self.embedding_service)

        lower_text = text.lower()
        a_lower = entity_a.lower()
        b_lower = entity_b.lower()

        works_verbs = ["works at", "works for", "employed by", "joined", "led by"]
        for verb in works_verbs:
            if verb in lower_text:
                parts = lower_text.split(verb, 1)
                if len(parts) >= 2 and a_lower in parts[0] and b_lower in parts[1]:
                    if validate_predicate(a_type, "works_at", b_type):
                        return "works_at"

        located_verbs = ["located in", "based in", "situated in"]
        for verb in located_verbs:
            if verb in lower_text:
                parts = lower_text.split(verb, 1)
                if len(parts) >= 2 and a_lower in parts[0] and b_lower in parts[1]:
                    if validate_predicate(a_type, "located_in", b_type):
                        return "located_in"

        created_verbs = ["created", "developed", "built", "founded", "implemented"]
        for verb in created_verbs:
            if verb in lower_text:
                parts = lower_text.split(verb, 1)
                if len(parts) >= 2 and a_lower in parts[0] and b_lower in parts[1]:
                    if validate_predicate(a_type, "created", b_type):
                        return "created"

        if confidence > 0.85:
            return "strongly_related"
        elif confidence > 0.7:
            return "related_to"
        elif confidence > 0.55:
            return "co_occurs_with"
        else:
            return "weakly_related"

    def _ensure_entity(
        self, name: str, preferred_type: Optional[str] = None
    ) -> Optional[str]:
        """Create an entity if it does not exist. Returns the entity ID.
        Concurrency-safe: retries SELECT if CREATE races with another writer."""
        name_escaped = self._escape_surrealql(name)
        entity_type = preferred_type or infer_entity_type(name, self.embedding_service)

        # 1. Exact name match (fastest path)
        check_sql = f"SELECT id FROM entity WHERE name = '{name_escaped}' LIMIT 1;"
        check_result = self._query_surreal(check_sql)
        existing = self._extract_result(check_result)
        if existing and len(existing) > 0:
            return existing[0].get("id")

        # 2. Embedding similarity (via SurrealDB Vector Index)
        similar = self._find_similar_entity(name, threshold=0.85)
        if similar:
            return similar

        # 3. Create new entity with embedding
        try:
            embedding = self.embedding_service.embed_for_storage(name)
            embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
            create_sql = f"""
            CREATE entity SET
                name = '{name_escaped}',
                type = '{entity_type}',
                created_at = time::now(),
                updated_at = time::now(),
                embedding = {embedding_str};
            """
        except Exception:
            create_sql = None

        if create_sql:
            result = self._query_surreal(create_sql)
            entity_result = self._extract_result(result)
            if entity_result and len(entity_result) > 0:
                return entity_result[0].get("id")

        # Fallback: create entity without embedding
        fallback_sql = f"""
        CREATE entity SET
            name = '{name_escaped}',
            type = '{entity_type}',
            created_at = time::now(),
            updated_at = time::now();
        """
        result = self._query_surreal(fallback_sql)
        entity_result = self._extract_result(result)
        if entity_result and len(entity_result) > 0:
            return entity_result[0].get("id")

        # Retry SELECT (handles race condition: another writer created it between our SELECT and CREATE)
        retry_result = self._query_surreal(check_sql)
        retry_existing = self._extract_result(retry_result)
        if retry_existing and len(retry_existing) > 0:
            return retry_existing[0].get("id")

        return None

    def _find_similar_entity(self, name: str, threshold: float = 0.85) -> Optional[str]:
        """Find similar entity using SurrealDB vector similarity search."""
        try:
            emb = self.embedding_service.embed_for_storage(name)
            emb_str = "[" + ",".join(str(v) for v in emb) + "]"
            sql = f"""
            SELECT id, name, type,
                vector::similarity::cosine(embedding, {emb_str}) AS sim
            FROM entity
            WHERE embedding IS NOT NULL
              AND vector::similarity::cosine(embedding, {emb_str}) > {threshold}
            ORDER BY sim DESC
            LIMIT 1;
            """
            result = self._query_surreal(sql)
            entities = self._extract_result(result)
            if entities and len(entities) > 0:
                return entities[0].get("id")
        except Exception:
            # If embedding fails, skip similarity search -- the caller then
            # creates a fresh entity. That means a broken embedding service
            # silently duplicates entities, so it must not be invisible.
            logging.warning("Entity similarity lookup failed; treating '%s' as "
                            "new", name, exc_info=True)
        return None

    def _select_salient_entities(
        self, text: str, entity_names: list[str], max_entities: int
    ) -> list[str]:
        """Select the most salient entities when count exceeds max_entities_for_cooccurrence.
        Scores by: frequency in text (weight 2) + specificity/multi-word bonus (weight 1)."""
        if len(entity_names) <= max_entities:
            return entity_names
        text_lower = text.lower()
        scored = []
        for name in entity_names:
            freq = text_lower.count(name.lower())
            specificity = len(name.split())
            scored.append((freq * 2 + specificity, name))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [name for _, name in scored[:max_entities]]

    def _dedup_candidates(self, candidates: List[str]) -> List[str]:
        """Deduplicate: keep the shortest canonical name, remove longer descriptive phrases."""
        result = []
        sorted_c = sorted(candidates, key=lambda x: len(x))
        for c in sorted_c:
            cl = c.lower().strip()
            is_superstr = False
            for other in result:
                ol = other.lower().strip()
                if cl != ol and len(cl) > len(ol) and ol in cl:
                    is_superstr = True
                    break
            if not is_superstr:
                result.append(c)
        return result

    _NOISE_WORDS = {
        "access",
        "assistance",
        "author",
        "bureaucracy",
        "changes",
        "deadlines",
        "effort",
        "efforts",
        "factors",
        "first",
        "gap",
        "governance",
        "injection",
        "june",
        "may",
        "march",
        "april",
        "performance",
        "planning",
        "poisoning",
        "progress",
        "security",
        "solutions",
        "testing",
        "vectors",
        "pricing",
        "focus",
        "nano",
        "cli",
        "os",
        "flash",
        "code",
        "agents",
        "agent",
        "models",
        "model",
        "framework",
        "platform",
        "service",
        "services",
        "system",
        "systems",
        "data",
        "time",
        "way",
        "part",
        "parts",
        "result",
        "results",
        "value",
        "values",
        "level",
        "levels",
        "rate",
        "rates",
        "cost",
        "costs",
        "price",
        "prices",
        "market",
        "provider",
        "providers",
        "standard",
        "network",
        "application",
        "applications",
        "user",
        "users",
        "tool",
        "tools",
        "process",
        "team",
        "teams",
        "work",
        "support",
        "report",
        "reports",
        "risk",
        "risks",
        "threat",
        "threats",
        "skill",
        "skills",
        "task",
        "tasks",
        "project",
        "projects",
        "guardrails",
        "compliance",
        "bottleneck",
        "hindrance",
        "four",
        "they",
        "codebases",
        "coding",
        "environments",
        "orchestrator",
        "validation",
        "tests",
        "test",
    }

    def _filter_noisy_candidates(self, candidates: List[str]) -> List[str]:
        """Filter out noisy/unwanted entity candidates before KG insertion."""
        result = []
        for c in candidates:
            clean = c.strip(" \t\n\r.,;:!?()[]{}'")
            if len(clean) < 3:
                continue

            # Pure numbers
            if re.match(r"^\d+(?:\.\d+)?%?$", clean):
                continue

            # Currency amounts
            if re.match(r"^[\$€£¥]\s*\d+[\.\d,]*\s*[A-Za-z/]*", clean):
                continue

            # Measurements (digits + unit)
            if re.match(
                r"^[\d,.]+\s*(?:miles?|km|kg|gb|mb|tb|ghz|mhz|years?|days?|hours?|b|m)\b",
                clean.lower(),
            ):
                continue

            # Numeric prefixes (e.g. "3 Nano", "309B", "30B", "40 cities")
            if re.match(r"^[\d,.%]+\s+", clean):
                continue

            # Digits-only or mostly numeric
            digit_count = sum(1 for ch in clean if ch.isdigit())
            if digit_count > 0 and digit_count / max(len(clean), 1) > 0.4:
                continue

            # Parenthesis fragments
            if clean.startswith("("):
                continue

            # Single generic words
            words = clean.split()
            if (
                len(words) == 1
                and clean.lower().strip(".,;:!?()[]{}'") in self._NOISE_WORDS
            ):
                continue

            # Sentence fragments: multi-word starting with determiner/number/possessive, no proper nouns
            if len(words) >= 2:
                first = words[0].lower().strip(".,;:!?()[]{}'")
                if first in (
                    "the",
                    "a",
                    "an",
                    "this",
                    "that",
                    "these",
                    "those",
                    "any",
                    "no",
                    "its",
                    "one",
                    "two",
                    "three",
                    "four",
                    "five",
                    "six",
                    "seven",
                    "eight",
                    "nine",
                    "ten",
                ):
                    remaining = words[1:]
                    if not any(w[0].isupper() for w in remaining if w):
                        continue

            # Reject if entity ends with a measurement word (e.g. "78.0 percent", "2 cents", "3 dollars")
            if len(words) >= 2:
                last_word = words[-1].lower().strip('.,;:!?()[]{}""\'')
                if last_word in (
                    "percent",
                    "dollars",
                    "cents",
                    "euros",
                    "pounds",
                    "billion",
                    "million",
                    "miles",
                    "years",
                    "days",
                    "hours",
                    "tokens",
                    "parameters",
                ):
                    continue

            # 4+ word phrases with no proper nouns at all
            if len(words) >= 4:
                if not any(w[0].isupper() for w in words if w):
                    continue

            # Overlong candidates (>6 words) with lowercase verbs/internal stops → sentence fragment
            if len(words) > 6:
                continue

            # 5-6 word phrases starting with capitalized word but containing a lowercase verb → sentence fragment
            if len(words) >= 5 and words[0][0].isupper():
                lowercase_words = [w for w in words[1:] if w and w[0].islower()]
                if len(lowercase_words) >= 2:
                    continue

            result.append(c)
        return result

    @staticmethod
    def fact_salience(
        confidence: float, predicate: str, event_novelty: Optional[float] = None
    ) -> float:
        """Score one extracted fact 0..1 (v1 heuristic).

        Inputs: the fact's extraction confidence, its predicate, and the
        parent event's embedding novelty (None = neutral 0.5, e.g. dedup
        retry where novelty was never computed). Specific SVO predicates
        outrank generic co-occurrence predicates. Pure function, no I/O --
        safe to unit-test without DB or model.
        """
        try:
            conf = max(0.0, min(1.0, float(confidence or 0.0)))
        except (TypeError, ValueError):
            conf = 0.0
        if event_novelty is None:
            nov = 0.5
        else:
            try:
                nov = max(0.0, min(1.0, float(event_novelty)))
            except (TypeError, ValueError):
                nov = 0.5
        spec = _PREDICATE_SPECIFICITY.get((predicate or "").lower(), 1.0)
        return round(min(1.0, 0.6 * conf + 0.25 * nov + 0.15 * spec), 4)

    def _active_fact_exists(self, subject_id: str, predicate: str, object_id: str) -> bool:
        """Check if an active fact already exists for (subject, predicate, object).
        Prevents duplicate fact creation in the KG."""
        pred_escaped = self._escape_surrealql(predicate)
        sql = f"""
        SELECT id FROM fact
        WHERE in = {subject_id}
          AND predicate = '{pred_escaped}'
          AND out = {object_id}
          AND (valid_until IS NONE OR valid_until > time::now())
        LIMIT 1;
        """
        result = self._query_surreal(sql)
        existing = self._extract_result(result)
        return bool(existing)

    def _event_has_kg_facts(self, event_id: str) -> bool:
        """Check if an event already has extracted KG facts (mentions)."""
        sql = f"""
        SELECT id FROM fact
        WHERE in = {event_id}
          AND predicate = 'mentions'
          AND (valid_until IS NONE OR valid_until > time::now())
        LIMIT 1;
        """
        result = self._query_surreal(sql)
        existing = self._extract_result(result)
        return bool(existing)

    def _extract_to_kg(
        self,
        text: str,
        event_id: str,
        debug: bool = False,
        event_novelty: Optional[float] = None,
    ):
        """
        Extract entities and semantic relationships to the Knowledge Graph.
        Uses SVO extraction as primary method, with co-occurrence as fallback.

        Salience (v1, parallel logging only): every created fact gets
        fact_salience() stored on the fact row; the return dict carries the
        average. NOTHING is filtered yet -- every fact is still created.
        """
        # First, try SVO extraction if spaCy is available
        entity_type_map = {}
        entity_label_map = {}
        svo_triples = None
        try:
            from src.extraction.entity_utils import extract_entities, extract_triples

            svo_triples = extract_triples(text)
            entities = extract_entities(text)

            # Extract entities from SVO triples if any
            svo_entities = set()
            for triple in svo_triples:
                svo_entities.add(triple["subject"])
                svo_entities.add(triple["object"])

            # Combine entities from SVO and spaCy NER, preserving types
            all_candidates = set()
            for entity in entities:
                name = entity["name"]
                all_candidates.add(name)
                if name not in entity_type_map:
                    entity_type_map[name] = entity["type"]
                if name not in entity_label_map:
                    entity_label_map[name] = entity.get("label", "?")
            all_candidates.update(svo_entities)

            candidates = self._dedup_candidates(list(all_candidates))
            candidates = self._filter_noisy_candidates(candidates)
        except ImportError:
            # Fall back to original method if spaCy is not available
            candidates = self._extract_candidate_entities(text)

        if not candidates:
            if debug:
                print("  [KG] No candidate entities found in text")
            return {"entities_created": 0, "facts_created": 0, "tier_skipped": 0}

        if debug:
            print(f"  [KG] Found candidate entities: {candidates}")

        entities_created = 0
        facts_created = 0
        tier_skipped = 0
        structurally_dropped = 0
        verifier_dropped = 0
        tier_thr = tier_threshold()
        saliences: List[float] = []
        entity_ids = []
        entity_names = []

        for name in candidates:
            # Safety: skip if name doesn't appear in source text (hallucination guard)
            if name.lower() not in text.lower():
                if debug:
                    print(f"  [KG] Skipping hallucinated entity: {name}")
                continue
            eid = self._ensure_entity(name, entity_type_map.get(name))
            if eid:
                entity_ids.append(eid)
                entity_names.append(name)
                entities_created += 1
                if debug:
                    print(
                        f"  [KG] Entity: {name} ({entity_type_map.get(name, '?')}) -> {eid}"
                    )

        # Process SVO triples if spaCy is available (using cached svo_triples from above)
        # Provenance for all facts below: majority vote over entity labels.
        extractor = infer_extractor([entity_label_map.get(n, "?") for n in entity_names])
        if svo_triples is None:
            try:
                from src.extraction.entity_utils import extract_triples
                svo_triples = extract_triples(text)
            except ImportError:
                svo_triples = []

        # Create facts from SVO triples
        if svo_triples:
            # Structural pre-filter. A copular frame states what something
            # IS, so it cannot license a predicate asserting something
            # happened. Measured on 118 hand-annotated production triples:
            # alone the copular test has no discriminative power (it also
            # rejects "John is a member of a hiking club", which really does
            # license part_of), but conjoined with event predicates it
            # rejects 22 triples of which 16 are wrong and 6 are good, moving
            # precision 0.441 -> 0.479. Cheap and falsifiable: see
            # scripts/eval_structural_gates.py.
            #
            # Deliberately narrow. The remaining wrong triples are mostly
            # argument-role errors (recipient read as location, purpose read
            # as object), which need the surface verb and its direct object
            # to judge -- a dependency parse, not a regex.
            before_filter = len(svo_triples)
            svo_triples = [
                t for t in svo_triples
                if not _copular_event_rejected(text, t.get("predicate", ""))
            ]
            structurally_dropped = before_filter - len(svo_triples)

            # NLI verifier. The extractor answers "which label fits this pair",
            # never "does this sentence entail the relation", so high
            # confidence survives on the wrong verb. The verifier asks exactly
            # that question, but only for the band where the confidence cannot
            # decide. Above the band auto-accepts, below it drops; the model
            # never sees either. Fails closed: a verifier error drops the
            # triple rather than risking a wrong fact in the graph.
            from src.extraction.verifier import BAND_HI as _BAND_HI
            from src.extraction.verifier import BAND_LO as _BAND_LO
            from src.extraction.verifier import verify_triples as _verify

            def _in_band(t):
                try:
                    c = float(t.get("confidence") or 0.0)
                except (TypeError, ValueError):
                    return False
                return _BAND_LO <= c <= _BAND_HI

            band = [t for t in svo_triples if _in_band(t)]
            svo_triples = [t for t in svo_triples if not _in_band(t)]
            verifier_dropped = 0
            if band:
                try:
                    accepted_band, verifier_dropped = _verify(text, band)
                    svo_triples.extend(accepted_band)
                except Exception as e:
                    sys.stderr.write(f"[Verifier] failed, dropping band: {e}\n")
                    verifier_dropped = len(band)

            for triple in svo_triples:
                subject = triple["subject"]
                predicate = triple["predicate"]
                obj = triple["object"]
                confidence = triple["confidence"]

                # Find corresponding entity IDs
                subject_idx = None
                obj_idx = None

                subj_lower = subject.lower()
                obj_lower = obj.lower()

                for i, name in enumerate(entity_names):
                    name_lower = name.lower()
                    if name_lower == subj_lower:
                        subject_idx = i
                    elif len(name_lower) > 3 and len(subj_lower) > 3 and (name_lower in subj_lower or subj_lower in name_lower):
                        if subject_idx is None:
                            subject_idx = i
                    if name_lower == obj_lower:
                        obj_idx = i
                    elif len(name_lower) > 3 and len(obj_lower) > 3 and (name_lower in obj_lower or obj_lower in name_lower):
                        if obj_idx is None:
                            obj_idx = i

                if (
                    subject_idx is not None
                    and obj_idx is not None
                    and subject_idx != obj_idx
                    and confidence >= 0.4
                ):
                    try:
                        predicate_escaped = self._escape_surrealql(predicate)
                        # UPSERT: skip if fact already exists
                        if self._active_fact_exists(entity_ids[subject_idx], predicate, entity_ids[obj_idx]):
                            if debug:
                                print(f"  [KG] SVO Fact already exists, skipping: {subject} -[{predicate}]-> {obj}")
                        else:
                            sal = self.fact_salience(confidence, predicate, event_novelty)
                            # The verifier margin travels on the fact so the
                            # accept threshold can move without re-ingesting.
                            margin = triple.get("verifier_margin")
                            margin_sql = (
                                f"verifier_margin = {margin:.4f},"
                                if isinstance(margin, (int, float)) else ""
                            )
                            relate_sql = f"""
                            RELATE {entity_ids[subject_idx]}->fact->{entity_ids[obj_idx]}
                            SET predicate = '{predicate_escaped}',
                                source_event = {event_id},
                                confidence = {confidence:.4f},
                                salience = {sal:.4f},
                                {margin_sql}
                                extractor = '{extractor}';
                            """
                            relate_result = self._query_surreal(relate_sql)
                            if self._extract_ok(relate_result):
                                facts_created += 1
                                saliences.append(sal)
                                if debug:
                                    print(
                                        f"  [KG] SVO Fact: {subject} -[{predicate} ({confidence:.2f}, sal {sal:.2f})]-> {obj}"
                                    )
                    except Exception as e:
                        if debug:
                            print(f"  [KG] Error creating SVO fact: {e}")

        # Fall back to co-occurrence method for any remaining entity pairs
        # Uses sentence-level proximity (nicht global O(n²)) + hard cap + Distanz-Confidence
        if len(entity_ids) >= 2:
            # Hard cap: max_entities_for_cooccurrence wählen
            if len(entity_names) > self.config.max_entities_for_cooccurrence:
                selected = self._select_salient_entities(
                    text, entity_names, self.config.max_entities_for_cooccurrence
                )
                name_to_idx = {name: idx for idx, name in enumerate(entity_names)}
                selected_indices = [name_to_idx[name] for name in selected]
                subset_ids = [entity_ids[i] for i in selected_indices]
                subset_names = [entity_names[i] for i in selected_indices]
            else:
                subset_ids = list(entity_ids)
                subset_names = list(entity_names)

            # Satzweise Paarbildung statt globaler Kombinatorik
            sentences = re.split(r"(?<=[.!?])\s+", text)
            paired = set()

            # Embeddings für alle Entities vorberechnen (einmal statt pro Paar)
            entity_embeddings = {}
            for name in subset_names:
                try:
                    entity_embeddings[name] = self.embedding_service.embed_for_storage(name)
                except Exception:
                    # No embedding means this entity cannot take part in
                    # cosine pair scoring, so its co-occurrence facts are
                    # silently weaker. Say so.
                    logging.warning("Skipping embedding for entity %r during "
                                    "co-occurrence pairing", name, exc_info=True)

            # SVO-Triples einmal vor der Schleife cachen
            svo_triples = None
            try:
                from src.extraction.entity_utils import extract_triples
                svo_triples = extract_triples(text)
            except ImportError:
                pass

            for sentence in sentences:
                sentence_lower = sentence.lower()
                indices_in_sentence = [
                    i
                    for i, name in enumerate(subset_names)
                    if name.lower() in sentence_lower
                ]
                if len(indices_in_sentence) < 2:
                    continue

                for idx_a in indices_in_sentence:
                    for idx_b in indices_in_sentence:
                        if idx_a >= idx_b:
                            continue
                        pair_key = (idx_a, idx_b)
                        if pair_key in paired:
                            continue
                        paired.add(pair_key)

                        # Prüfen ob dieses Paar bereits SVO-Fact hat (nutzt gecachte Triples)
                        has_svo_fact = False
                        if svo_triples:
                            for triple in svo_triples:
                                subj = triple["subject"]
                                obj = triple["object"]
                                if (
                                    subset_names[idx_a].lower() == subj.lower()
                                    and subset_names[idx_b].lower() == obj.lower()
                                ) or (
                                    subset_names[idx_b].lower() == subj.lower()
                                    and subset_names[idx_a].lower() == obj.lower()
                                ):
                                    has_svo_fact = True
                                    break

                        if not has_svo_fact:
                            try:
                                predicate, base_conf = (
                                    self._compute_relation_confidence(
                                        text, subset_names[idx_a], subset_names[idx_b],
                                        emb_a=entity_embeddings.get(subset_names[idx_a]),
                                        emb_b=entity_embeddings.get(subset_names[idx_b]),
                                    )
                                )

                                # Confidence via Embedding-Similarity + textualer Distanz
                                pos_a = sentence_lower.index(
                                    subset_names[idx_a].lower()
                                )
                                pos_b = sentence_lower.index(
                                    subset_names[idx_b].lower()
                                )
                                proximity = 1.0 - min(
                                    abs(pos_a - pos_b) / max(len(sentence), 1), 1.0
                                )
                                confidence = max(
                                    0.1, min(1.0, base_conf * 0.6 + proximity * 0.4)
                                )

                                if confidence >= 0.50:
                                    # UPSERT: skip if fact already exists
                                    if self._active_fact_exists(subset_ids[idx_a], predicate, subset_ids[idx_b]):
                                        if debug:
                                            print(f"  [KG] Co-occurrence Fact already exists, skipping: {subset_names[idx_a]} -[{predicate}]-> {subset_names[idx_b]}")
                                    else:
                                        sal = self.fact_salience(confidence, predicate, event_novelty)
                                        # Tiering: low-salience co-occurrence facts are
                                        # not created (mentions below preserve
                                        # provenance). SVO facts never tiered.
                                        if not tier_keep(sal, tier_thr):
                                            tier_skipped += 1
                                            if debug:
                                                print(
                                                    f"  [KG] Tier-skipped: {subset_names[idx_a]} -[{predicate} ({confidence:.2f}, sal {sal:.2f})]-> {subset_names[idx_b]}"
                                                )
                                            continue
                                        relate_sql = f"""
                                        RELATE {subset_ids[idx_a]}->fact->{subset_ids[idx_b]}
                                        SET predicate = '{predicate}',
                                            source_event = {event_id},
                                            confidence = {confidence:.4f},
                                            salience = {sal:.4f},
                                            extractor = '{extractor}';
                                        """
                                        relate_result = self._query_surreal(relate_sql)
                                        if self._extract_ok(relate_result):
                                            facts_created += 1
                                            saliences.append(sal)
                                            if debug:
                                                print(
                                                    f"  [KG] Co-occurrence Fact: {subset_names[idx_a]} -[{predicate} ({confidence:.2f}, sal {sal:.2f})]-> {subset_names[idx_b]}"
                                                )
                            except Exception as e:
                                if debug:
                                    print(
                                        f"  [KG] Error creating co-occurrence fact: {e}"
                                    )

        for eid in entity_ids:
            try:
                # UPSERT: skip if mention fact already exists
                if not self._active_fact_exists(event_id, "mentions", eid):
                    sal = self.fact_salience(0.8, "mentions", event_novelty)
                    relate_sql = f"""
                    RELATE {event_id}->fact->{eid}
                    SET predicate = 'mentions',
                        source_event = {event_id},
                        confidence = 0.8,
                        salience = {sal:.4f},
                        extractor = '{extractor}';
                    """
                    relate_result = self._query_surreal(relate_sql)
                    if self._extract_ok(relate_result):
                        facts_created += 1
                        saliences.append(sal)
                else:
                    if debug:
                        print(f"  [KG] Mention fact already exists, skipping: {event_id} -> {eid}")
            except Exception as e:
                sys.stderr.write(f"[EntropyGate] Error creating mention fact for {event_id} -> {eid}: {e}\n")

        avg_sal = round(sum(saliences) / len(saliences), 4) if saliences else None
        return {
            "entities_created": entities_created,
            "facts_created": facts_created,
            "tier_skipped": tier_skipped,
            # Narrow structural pre-filter (copular + event predicate).
            # Reported so a change in stored-fact volume is attributable.
            "structurally_dropped": structurally_dropped,
            # NLI verifier on the ambiguous band, same reasoning.
            "verifier_dropped": verifier_dropped,
            "avg_fact_salience": avg_sal,
            "salience_version": SALIENCE_VERSION if saliences else None,
        }

    def _dict_to_surrealdb_object(self, d: dict) -> str:
        """Convert a Python dict to a SurrealDB object literal."""
        items = []
        for k, v in d.items():
            key = k
            if v is None:
                val = "NULL"
            elif isinstance(v, bool):
                val = "true" if v else "false"
            elif isinstance(v, (int, float)):
                val = str(v)
            elif isinstance(v, str):
                val = "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"
            elif isinstance(v, dict):
                val = self._dict_to_surrealdb_object(v)
            elif isinstance(v, list):
                list_items = []
                for item in v:
                    if isinstance(item, dict):
                        list_items.append(self._dict_to_surrealdb_object(item))
                    elif isinstance(item, str):
                        list_items.append(
                            "'" + item.replace("\\", "\\\\").replace("'", "\\'") + "'"
                        )
                    elif isinstance(item, bool):
                        list_items.append("true" if item else "false")
                    elif item is None:
                        list_items.append("NULL")
                    else:
                        list_items.append(str(item))
                val = "[" + ", ".join(list_items) + "]"
            else:
                val = "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"
            items.append(f"{key}: {val}")
        return "{" + ", ".join(items) + "}"

    def ingest(
        self,
        text: str,
        source: str = "unknown",
        debug: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        trust: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Hauptfunktion: Ingest eines Textes in das Memory System
        1. IMMER in Raw Event Log speichern (mit trust-Markierung)
        2. Entropy Gate entscheiden lassen ob KG-Extraction
        3. Bei 'extract': Entities und Facts in den Knowledge Graph extrahieren
        """
        try:
            return self._ingest_impl(text, source, debug, metadata, trust)
        except Exception as e:
            sys.stderr.write(f"[EntropyGate] ingest fatal error: {e}\n")
            return None, None, {"decision": "ignore", "reason": f"ingest_error: {e}"}

    def _ingest_impl(
        self,
        text: str,
        source: str = "unknown",
        debug: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        trust: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Hauptfunktion: Ingest eines Textes in das Memory System
        1. IMMER in Raw Event Log speichern
        2. Entropy Gate entscheiden lassen ob KG-Extraction
        3. Bei 'extract': Entities und Facts in den Knowledge Graph extrahieren
        """

        if not text or not text.strip():
            sys.stderr.write(f"[EntropyGate] Error: Empty or whitespace-only content rejected (source={source})\n")
            return None, None, None
        if len(text) > 100_000:
            sys.stderr.write(f"[EntropyGate] Error: Content exceeds maximum storage length ({len(text)} > 100000) (source={source})\n")
            return None, None, None
        if "\x00" in text:
            sys.stderr.write(f"[EntropyGate] Error: Content contains null bytes, rejecting (source={source})\n")
            return None, None, None

        # 0. Dedup: Prüfen ob exakt gleicher Content mit gleicher Source bereits existiert
        content_hash = self._hash_content(text)
        source_escaped_dedup = self._escape_surrealql(source)
        dedup_sql = f"""
        SELECT id FROM event
        WHERE content_hash = '{content_hash}'
          AND source = '{source_escaped_dedup}'
          AND forgotten = false
        LIMIT 1;
        """
        dedup_result = self._query_surreal(dedup_sql)
        existing = self._extract_result(dedup_result)
        if existing and len(existing) > 0:
            first = existing[0]
            event_id = first.get("id") if isinstance(first, dict) else None
            if debug:
                print(
                    f"  [Dedup] Found existing event {event_id} for identical content and source"
                )
            # P3: Exakte Content-Dupes laufen NICHT durchs Gate (kein Embedding,
            # kein Vector-Search): Der identische Text wurde bereits bewertet.
            # Falls das Original noch keine KG-Facts hat (z.B. damals ignoriert),
            # wird die Extraction hier nachgeholt; sonst ehrlich skip/dedup.
            if event_id and not self._event_has_kg_facts(event_id):
                kg_result = self._extract_to_kg(text, event_id, debug)
                gate_result = {
                    "decision": "extract",
                    "reason": "dedup_retry_kg_missing",
                    "deduplicated_to": event_id,
                }
            else:
                kg_result = {"entities_created": 0, "facts_created": 0}
                gate_result = {
                    "decision": "skip",
                    "reason": "dedup_content_exists" if event_id else "dedup_no_event_id",
                    "deduplicated_to": event_id,
                }
                self._log_decision(
                    text,
                    self.calculate_char_entropy(text) / 4.5,
                    0.0,
                    0.0,
                    gate_result["decision"],
                    reason_override=gate_result["reason"],
                    compression_ratio=self.calculate_compression_ratio(text),
                )
            return event_id, kg_result, gate_result

        # 1. IMMER in Raw Event Log speichern (ohne Gate!)
        embedding = self.embedding_service.embed_for_storage(text)
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        text_escaped = self._escape_surrealql(text)
        source_escaped = self._escape_surrealql(source)
        # Trust: explicit wins, else direct only for user_input. Stored on the
        # event; _clean_output derives it for old rows without the field.
        base_source = (source or "").split("#")[0]
        trust_value = trust if isinstance(trust, str) and trust else (
            "direct" if base_source == "user_input" else "untrusted"
        )
        trust_escaped = self._escape_surrealql(trust_value)
        metadata_str = ""
        if metadata:
            metadata_str = (
                f",\n            metadata = {self._dict_to_surrealdb_object(metadata)}"
            )
        sql = f"""
        CREATE event SET
            content = '{text_escaped}',
            content_hash = '{content_hash}',
            source = '{source_escaped}',
            trust = '{trust_escaped}',
            embedding = {embedding_str}{metadata_str};
        """
        event_id = None
        result = None
        try:
            result = self._query_surreal(sql)
            event_result = self._extract_result(result)
            if event_result and len(event_result) > 0:
                first = event_result[0]
                event_id = first.get("id") if isinstance(first, dict) else None
        except Exception as e:
            import sys

            sys.stderr.write(f"[EntropyGate] Error saving to event log: {e}\n")
            if result:
                sys.stderr.write(f"[EntropyGate]   SurrealDB response: {result}\n")

        if event_id is None:
            import sys

            sys.stderr.write("[EntropyGate] WARNING: ingest returned no event_id\n")
            sys.stderr.write(
                f"[EntropyGate]   source={source}, content_length={len(text)}, hash={content_hash[:16]}...\n"
            )

        # 2. Entropy Gate prüfen (mit event_id als exclude_id, um Self-Match zu vermeiden)
        # Das Embedding aus Schritt 1 wird wiederverwendet (spart einen Model-Call).
        try:
            gate_result = self.should_extract(
                text, exclude_id=event_id, embedding=embedding
            )
        except Exception as e:
            sys.stderr.write(f"[EntropyGate] Gate decision error: {e}\n")
            gate_result = {"decision": "ignore", "reason": f"gate_error: {e}"}

        if debug:
            print(f"Entropy Gate Decision: {gate_result}")

        # 3. Falls extract: starte KG-Extraction
        kg_result = None
        gate_decision = gate_result.get("decision", "ignore") if isinstance(gate_result, dict) else "ignore"
        if gate_decision == "extract" and event_id:
            try:
                kg_result = self._extract_to_kg(
                    text,
                    event_id,
                    debug,
                    event_novelty=gate_result.get("novelty"),
                )
            except Exception as e:
                import sys
                sys.stderr.write(f"[EntropyGate] KG extraction error: {e}\n")
                kg_result = {"entities_created": 0, "facts_created": 0, "error": str(e)}
            if debug:
                print(f"  [KG] Extraction complete: {kg_result}")
            # 4. Salience parallel loggen (kein Verhaltenseffekt): avg fact
            # salience auf die gate_log-Zeile dieser Entscheidung schreiben.
            self._attach_salience(gate_result.get("gate_log_id"), kg_result)

        return event_id, kg_result, gate_result

    def _attach_salience(
        self, gate_log_id: Optional[str], kg_result: Optional[Dict[str, Any]]
    ) -> None:
        """Write avg fact salience onto the gate_log row (best effort, no throw)."""
        try:
            if not gate_log_id or not isinstance(kg_result, dict):
                return
            avg_sal = kg_result.get("avg_fact_salience")
            version = kg_result.get("salience_version")
            if avg_sal is None or not re.fullmatch(
                r"[A-Za-z0-9_]+:[A-Za-z0-9_]+", gate_log_id
            ):
                return
            version_escaped = self._escape_surrealql(version or SALIENCE_VERSION)
            self._query_surreal(
                f"UPDATE {gate_log_id} SET salience = {float(avg_sal):.4f}, "
                f"salience_version = '{version_escaped}';"
            )
        except Exception as e:
            sys.stderr.write(f"[Gate] _attach_salience failed: {e}\n")
