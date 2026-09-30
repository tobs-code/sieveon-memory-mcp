"""
Query Classifier (Python Implementation) for sieveon
Klassifiziert Queries in die Typen: temporal, factual, multi-hop, conversational, update

Hybrid approach:
  1. ML: sklearn LogisticRegression on Qwen3-Embedding-0.6B embeddings + TF-IDF features (if training data available)
  2. Regex: rule-based fallback if ML confidence is low or no model trained
"""

import json
import pickle
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from src.extraction.embedding_service import BaseEmbeddingService


_ML_MODEL_PATH = Path(__file__).parents[2] / "docs" / "data" / "classifier_model.pkl"

# Read-requests worded with "update" that are never updates (asking for
# information, changing nothing). Used by the regex fallback AND as an ML
# veto in QueryClassifier (an ML "update" verdict never survives these).
_UPDATE_READ_REQUEST_RE = re.compile(
    r"\bupdate\s+me\s+on\b|\blatest\s+updates?\b"
    r"|\bbring\s+me\s+up\s+to\s+date\b"
)

# Distinct question words: 2+ in one query usually means multiple facts
# ("Who ... and where ...") -> multi-hop, even if each word alone is factual.
_WH_WORD_RE = re.compile(
    r"\b(who|what|which|where|when|why|how|wer|was|welche|wo|wann|warum|wie)\b"
)

# Definitional why ("why is/are ..."): asks for an explanation of a stable
# fact (lookup), not multi-hop synthesis. Past-tense/causal why
# ("why did/was ...") stays multi-hop territory.
_WHY_DEFINITIONAL_RE = re.compile(r"\bwhy\s+(is|are)\b")

# German factual question frames. Conversational DE training data uses
# worüber/gesprochen/erinnerst-frames exclusively, so these frames never
# legitimately route to conversational -- an ML "conversational" verdict on
# them is always template gravity from EN CoQA "What ..." questions.
_DE_FACTUAL_RE = re.compile(
    r"\bwas\s+(ist|sind|hat|haben|war|waren|wurde|wurden|bedeutet|kostet|steht)\b"
    r"|\bwer\s+(ist|war|hat)\b|\bwo\s+ist\b|\bwie\s+funktioni"
)
_TRAINING_PATHS = [
    Path(__file__).parents[2] / "docs" / "data" / "trec_queries.jsonl",
    Path(__file__).parents[2] / "docs" / "data" / "coqa_conversational.jsonl",
    Path(__file__).parents[2] / "docs" / "data" / "training_queries.jsonl",
    Path(__file__).parents[2] / "docs" / "data" / "training_queries_extra.jsonl",
    Path(__file__).parents[2] / "docs" / "data" / "manual_labels.jsonl",
    # Public sources (scripts/fetch_classifier_data.py). CoQA overlap with
    # coqa_conversational.jsonl was removed (9 rows); classes noted per file.
    Path(__file__).parents[2] / "docs" / "data" / "hotpot_multihop.jsonl",
    Path(__file__).parents[2] / "docs" / "data" / "squad_factual.jsonl",
    Path(__file__).parents[2] / "docs" / "data" / "coqa_conv.jsonl",
    Path(__file__).parents[2] / "docs" / "data" / "clinc_mapped.jsonl",
    Path(__file__).parents[2] / "docs" / "data" / "timeqa_temporal.jsonl",
]
_ML_CONFIDENCE_THRESHOLD = 0.60


class _RegexClassifier:
    """Pure regex-based classifier (used as fallback)."""

    def __init__(self):
        self.temporal_patterns = [
            # Deutsch
            r"\bwann\b",
            r"\bgestern\b",
            r"\bheute\b",
            r"\bmorgen\b",
            r"\bletzt\b",
            r"\bnächste\b",
            r"\btimestamp\b",
            r"\bzeit\b",
            r"\bdatum\b",
            r"\bseit\b",
            r"\bbis\b",
            r"\bänderung\b",
            r"\bgeändert\b",
            # Englisch
            r"\bwhen\b",
            r"\byesterday\b",
            r"\btoday\b",
            r"\btomorrow\b",
            r"\blast\b",
            r"\bnext\b",
            r"\btime\b",
            r"\bdate\b",
            r"\bsince\b",
            r"\buntil\b",
            # NOTE: no bare change/changed here (removed 2026-09-30): "what
            # changed" asks for facts (factual + optional time window), the
            # time aspect comes from when/since/until words. Bare "change"
            # routed too many lookups to temporal.
        ]
        self.factual_patterns = [
            # Deutsch
            r"\bwer\b",
            r"\bwas\b",
            r"\bwelche\b",
            r"\bwo\b",
            r"\bhat\b",
            r"\bhaben\b",
            r"\bist\b",
            r"\bworan\b",
            r"\bwomit\b",
            r"\bwodurch\b",
            r"\bwerdegang\b",
            r"\bfakten\b",
            r"\binfos\b",
            r"\bnenne\b",
            r"\bliste\b",
            r"\bzeig\b",
            r"\bfinde\b",
            # Englisch
            r"\bwho\b",
            r"\bwhat\b",
            r"\bwhich\b",
            r"\bwhere\b",
            r"\bhas\b",
            r"\bhave\b",
            r"\bis\b",
            r"\blist\b",
            r"\bshow\b",
            r"\bfind\b",
            r"\btell\b",
            # Englisch + Deutsch: how-questions are lookups, not multi-hop
            r"\bhow\b",
            r"\bwie\b",
            # Deutsch: reflexive change-questions ask what changed (factual).
            # Umlaute in beiden Schreibweisen (ä/ae), da User beides tippen.
            r"\bwas hat sich\b",
            r"\bwas haben sich\b",
            r"\bhat sich ge(ä|ae)ndert\b",
            r"\bhaben sich ge(ä|ae)ndert\b",
        ]
        self.multi_hop_patterns = [
            # Deutsch
            r"\bwarum\b",
            r"\bweshalb\b",
            r"\bwieso\b",
            r"\bwegen\b",
            r"\bdaher\b",
            r"\bdeshalb\b",
            r"\bbeziehung\b",
            r"\bverbunden\b",
            r"\bzusammenhang\b",
            r"\bund wo\b",
            r"\bund was\b",
            r"\bund welche\b",
            # Englisch
            r"\bwhy\b",
            r"\bbecause\b",
            r"\breason\b",
            r"\brelation\b",
            r"\bconnected\b",
            r"\brelationship\b",
            r"\band where\b",
            r"\band what\b",
            r"\band which\b",
        ]
        self.conversational_patterns = [
            # Deutsch
            r"\bworüber\b",
            r"\büber was\b",
            r"\bgesprochen\b",
            r"\bredeten\b",
            r"\bunterhielt\b",
            r"\berinnerst du dich\b",
            r"\bweißt du noch\b",
            # Englisch
            r"\bwhat about\b",
            r"\btalked about\b",
            r"\bspoke about\b",
            r"\btalking about\b",
            # Recall-questions stay conversational; bare "remember that/note"
            # (memory writes) must NOT match here -- ML learned update for those.
            r"\bremember what\b",
            r"\bremember when\b",
            r"\bremember who\b",
            r"\bdo you recall\b",
            r"\bdo you remember\b",
            # Greetings / acknowledgements (CLINC greeting/goodbye/thank_you)
            r"^\s*hi\b",
            r"^\s*hello\b",
            r"^\s*hey\b",
            r"^\s*hallo\b",
            r"\bgood morning\b",
            r"\bgood evening\b",
            r"\bthank you\b",
            r"\bthanks\b",
            r"\bdanke\b",
            r"\bsee you\b",
        ]
        self.update_patterns = [
            # Deutsch
            r"\baktualisiere\b",
            r"\bupdate\b",
            r"\bändere\b",
            r"\bkorrigiere\b",
            r"\bsetze\b",
            r"\büberschreibe\b",
            # Deutsch: memory-write verbs (erinnern/vergessen/merken)
            r"\bvergiss\b",
            r"\bvergisst\b",
            r"\bvergesse\b",
            r"\berinnere\b",
            r"\bmerke\b",
            r"\bmerk dir\b",
            # Englisch
            r"\bupdate\b",
            r"\bchange\b",
            r"\bmodify\b",
            r"\bcorrect\b",
            r"\bset\b",
            r"\boverwrite\b",
            # Englisch: memory-write verbs
            r"\bforget\b",
            r"\bremind\b",
            r"\bremember to\b",
            r"\bmake a note\b",
            r"\btake note\b",
        ]

    def classify(self, query: Optional[str]) -> Tuple[str, float]:
        if not query or not query.strip():
            return "factual", 0.5
        query_lower = query.lower()
        scores: Dict[str, int] = {
            "temporal": 0,
            "factual": 0,
            "multi-hop": 0,
            "conversational": 0,
            "update": 0,
        }

        for pattern in self.temporal_patterns:
            if re.search(pattern, query_lower):
                scores["temporal"] += 1
        for pattern in self.factual_patterns:
            if re.search(pattern, query_lower):
                scores["factual"] += 1
        for pattern in self.multi_hop_patterns:
            # Definitional why ("why is/are ...") is a lookup, not synthesis.
            # Skip only the bare "why" hit; coordination still counts via _WH_WORD_RE.
            if pattern == r"\bwhy\b" and _WHY_DEFINITIONAL_RE.search(query_lower):
                continue
            if re.search(pattern, query_lower):
                scores["multi-hop"] += 1
        for pattern in self.conversational_patterns:
            if re.search(pattern, query_lower):
                scores["conversational"] += 2
        for pattern in self.update_patterns:
            if re.search(pattern, query_lower):
                scores["update"] += 2

        # Read-requests worded with "update" are NOT updates: "update me on
        # X", "latest update(s) ...", "bring me up to date" ask for information
        # (factual/conversational), they change nothing. Bare "update(s) on"
        # stays ambiguous on purpose -- the ML model decides those.
        if scores["update"] > 0 and _UPDATE_READ_REQUEST_RE.search(query_lower):
            scores["update"] = 0

        # Coordination: two distinct question words in one query ("Who ...
        # and where ...") combine multiple facts -> multi-hop. Counts distinct
        # wh-words so "where ... where" repetition does not trigger it.
        if len(set(_WH_WORD_RE.findall(query_lower))) >= 2:
            scores["multi-hop"] += 2

        priority_order = [
            "update",
            "multi-hop",
            "conversational",
            "temporal",
            "factual",
        ]

        sorted_types = sorted(
            scores.keys(), key=lambda t: (-scores[t], priority_order.index(t))
        )
        best_type = sorted_types[0]
        best_score = scores[best_type]

        if best_score == 0:
            return "factual", 0.5

        sorted_scores = sorted(scores.values(), reverse=True)
        second_best_score = sorted_scores[1] if len(sorted_scores) > 1 else 0

        margin = (best_score - second_best_score) / best_score
        confidence = 0.5 + (margin * 0.5)

        return best_type, round(confidence, 2)


# ── ML Classifier ─────────────────────────────────────────────────────

class _MLClassifier:
    """LogisticRegression trained on Qwen3 embeddings + TF-IDF features."""

    def __init__(self):
        self.model = None
        self.label_encoder = None
        self.vectorizer = None
        self._embedding_service = None

    def _get_emb(self) -> "BaseEmbeddingService":
        if self._embedding_service is None:
            from src.extraction.embedding_service import get_embedding_service
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    def _embed(self, text: str) -> List[float]:
        return self._get_emb().embed_for_storage(text)

    def _load_training_data(self) -> Tuple[List[str], List[str]]:
        texts, labels = [], []
        for p in _TRAINING_PATHS:
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ex = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        t = ex.get("type")
                        txt = ex.get("text")
                        if t and txt and t != "skip":
                            texts.append(txt)
                            labels.append(t)
        return texts, labels

    def is_trained(self) -> bool:
        return self.model is not None

    def _suppress_tqdm(self):
        import os
        os.environ.setdefault("TQDM_DISABLE", "1")

    def _build_features(self, texts: List[str]):
        import numpy as np
        svc = self._get_emb()
        embeddings = np.array(svc.embed_batch(texts, for_storage=True))
        if self.vectorizer is not None:
            tfidf = self.vectorizer.transform(texts).toarray()
            return np.concatenate([embeddings, tfidf], axis=1)
        return embeddings

    def train(self, texts: Optional[List[str]] = None, labels: Optional[List[str]] = None,
              cap_per_class: int = 600):
        self._suppress_tqdm()

        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import LabelEncoder

        if texts is None or labels is None:
            texts, labels = self._load_training_data()

        if len(texts) < 10:
            return

        # Per-class cap (deterministic): keeps dominant sources (e.g. 5.4k TREC
        # factual templates) from drowning minority classes. Seed fixed for
        # reproducible retrains.
        if cap_per_class and cap_per_class > 0:
            import random as _random
            rng = _random.Random(42)
            by_class: Dict[str, List[str]] = {}
            for t, lbl in zip(texts, labels):
                by_class.setdefault(lbl, []).append(t)
            texts, labels = [], []
            for lbl in sorted(by_class):
                items = by_class[lbl][:]
                rng.shuffle(items)
                for t in items[:cap_per_class]:
                    texts.append(t)
                    labels.append(lbl)

        import numpy as np

        self.vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            max_features=500,
            sublinear_tf=True,
        )
        tfidf = self.vectorizer.fit_transform(texts).toarray()

        svc = self._get_emb()
        embeddings = np.array(svc.embed_batch(texts, for_storage=True))
        X = np.concatenate([embeddings, tfidf], axis=1)

        self.label_encoder = LabelEncoder()
        y = self.label_encoder.fit_transform(labels)

        self.model = LogisticRegression(
            C=1.0,
            max_iter=1000,
            multi_class="ovr",
            class_weight="balanced",
            random_state=42,
        )
        self.model.fit(X, y)

        try:
            data_dir = _ML_MODEL_PATH.parent
            data_dir.mkdir(parents=True, exist_ok=True)
            with open(_ML_MODEL_PATH, "wb") as f:
                pickle.dump({
                    "model": self.model,
                    "label_encoder": self.label_encoder,
                    "vectorizer": self.vectorizer,
                }, f)
        except OSError:
            pass

    def load(self) -> bool:
        if not _ML_MODEL_PATH.exists():
            return False
        try:
            with open(_ML_MODEL_PATH, "rb") as f:
                data = pickle.load(f)
            self.model = data["model"]
            self.label_encoder = data["label_encoder"]
            self.vectorizer = data.get("vectorizer")
            return True
        except Exception:
            return False

    def classify(self, query: str) -> Tuple[Optional[str], float]:
        if self.model is None:
            return None, 0.0

        import numpy as np
        emb = np.array([self._embed(query)])
        if self.vectorizer is not None:
            tfidf = self.vectorizer.transform([query]).toarray()
            features = np.concatenate([emb, tfidf], axis=1)
        else:
            features = emb
        probs = self.model.predict_proba(features)[0]
        best_idx = int(probs.argmax())
        confidence = float(probs[best_idx])
        label = self.label_encoder.inverse_transform([best_idx])[0]
        return label, round(confidence, 3)


class QueryClassifier:
    """Hybrid classifier: tries ML first, falls back to regex."""

    def __init__(self):
        self._ml = _MLClassifier()
        self._regex = _RegexClassifier()
        self._ml_loaded = False

    def _ensure_ml(self):
        if not self._ml_loaded:
            self._ml_loaded = True
            if not self._ml.load():
                texts, labels = self._ml._load_training_data()
                if texts:
                    self._ml.train(texts, labels)

    def classify(self, query: Optional[str]) -> Tuple[str, float]:
        if not query or not query.strip():
            return "factual", 0.5

        self._ensure_ml()

        if self._ml.is_trained():
            label, confidence = self._ml.classify(query)
            if confidence >= _ML_CONFIDENCE_THRESHOLD:
                # Deterministic vetoes: known phrasings must never route to
                # update (triggers writes) or conversational (EN-template
                # gravity on DE factual frames), no matter the ML confidence.
                if label == "update" and _UPDATE_READ_REQUEST_RE.search(query.lower()):
                    return self._regex.classify(query)
                if label == "conversational" and _DE_FACTUAL_RE.search(query.lower()):
                    return self._regex.classify(query)
                return label, confidence

        return self._regex.classify(query)

    def train(self, texts: List[str], labels: List[str]):
        self._ml.train(texts, labels)
        self._ml_loaded = True


if __name__ == "__main__":
    classifier = QueryClassifier()

    test_queries = [
        "Wann habe ich Alice getroffen?",
        "Wer ist mein Kunde?",
        "Warum haben wir das Projekt gestoppt?",
        "Worüber haben wir gestern gesprochen?",
        "Aktualisiere meinen Namen auf Max.",
    ]

    print("Query Classification Test:")
    for q in test_queries:
        q_type, conf = classifier.classify(q)
        src = "ml" if classifier._ml.is_trained() and classifier._ml.classify(q)[1] >= _ML_CONFIDENCE_THRESHOLD else "regex"
        print(f"  '{q}'")
        print(f"    → {q_type:14s} (confidence: {conf:.2f}) [{src}]")
