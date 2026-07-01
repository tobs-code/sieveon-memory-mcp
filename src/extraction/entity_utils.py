"""Shared entity utilities for STRATA - single source of truth."""
from typing import Optional
import re
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.extraction.embedding_service import get_embedding_service, BaseEmbeddingService

_STOPWORDS = {
    'the', 'a', 'an', 'this', 'that', 'these', 'those', 'it', 'its',
    'in', 'on', 'at', 'by', 'for', 'with', 'from', 'to', 'of', 'and', 'or',
    'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'shall', 'should', 'may', 'might',
    'can', 'could', 'must', 'not', 'no', 'nor', 'but', 'if', 'as', 'so',
    'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einen',
    'einem', 'eines', 'einer', 'ist', 'sind', 'war', 'waren', 'wird',
    'werden', 'wurde', 'wurden', 'hat', 'haben', 'hätte', 'hatten',
    'sein', 'seine', 'seiner', 'seinem', 'seinen', 'ihr', 'ihre',
    'ihrer', 'ihrem', 'ihren', 'mein', 'meine', 'meiner', 'meinem',
    'meinen', 'und', 'oder', 'aber', 'denn', 'doch', 'nicht', 'kein',
    'keine', 'keinen', 'keinem', 'keines', 'im', 'am', 'um', 'zur',
    'zum', 'vom', 'beim', 'ins', 'durch', 'für', 'gegen', 'ohne',
    'mit', 'nach', 'bei', 'aus', 'von', 'zu', 'an', 'auf', 'über',
    'unter', 'vor', 'zwischen', 'außer', 'gegenüber',
    'this', 'that', 'there', 'their', 'them', 'they', 'then', 'than',
    'also', 'very', 'just', 'like', 'into', 'about', 'over', 'such',
    'each', 'which', 'what', 'who', 'whom', 'when', 'where', 'why',
    'how', 'all', 'both', 'every', 'some', 'any', 'few', 'more', 'most',
    'other', 'another',
}

_PREPOSITION_STARTS = {
    'in', 'on', 'at', 'by', 'for', 'with', 'from', 'to', 'of', 'about',
    'over', 'under', 'through', 'between', 'among', 'against', 'without',
    'during', 'before', 'after', 'above', 'below', 'out', 'off', 'up',
    'down', 'into', 'onto', 'upon', 'within', 'across', 'along', 'around',
    'behind', 'beneath', 'beside', 'beyond', 'inside', 'outside', 'toward',
    'towards', 'via', 'per',
    'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einen',
    'einem', 'eines', 'einer', 'im', 'am', 'um', 'zur', 'zum', 'vom',
    'beim', 'ins', 'durch', 'für', 'gegen', 'ohne', 'mit', 'nach', 'bei',
    'aus', 'von', 'zu', 'an', 'auf', 'über', 'unter', 'vor', 'zwischen',
    'außer',
}

_VERB_STARTS = {
    'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'shall', 'should', 'may', 'might',
    'can', 'could', 'must', 'ist', 'sind', 'war', 'waren', 'wird', 'werden',
    'wurde', 'wurden', 'hat', 'haben', 'hätte', 'hatten', 'sein',
    'works', 'worked', 'working', 'relies', 'relied', 'relying', 'based',
    'lives', 'lived', 'living', 'says', 'said', 'made', 'makes', 'making',
    'uses', 'used', 'using', 'takes', 'took', 'taking', 'gives', 'gave',
    'arbeitet', 'arbeitete', 'gearbeitet', 'lebt', 'lebte', 'gelebt',
}

_ENTITY_PROTOTYPES = {
    "organization": [
        "Acme Corp", "Microsoft Inc", "Google LLC", "OpenAI GmbH", "Tech AG",
        "Stiftung", "Universität", "Institut", "Behörde", "Verein"
    ],
    "technology": [
        "SQL Database", "Web Framework", "API Gateway", "MCP Server", "Entropy Gate",
        "Protocol", "Engine", "Platform", "Toolkit", "Runtime"
    ],
    "person": [
        "John Smith", "Dr Müller", "Prof Schmidt", "Alice Johnson", "Max Mustermann",
        "Jane Doe", "Herr Fischer", "Frau Weber", "Mr Bond"
    ],
    "concept": [
        "The Theory of Everything", "Quantum Mechanics", "Social Contract",
        "Cognitive Bias", "Paradigm Shift", "Heuristics", "Algorithm"
    ],
}

_EMBEDDING_CACHE = {}


def _get_prototype_embedding(emb_service: BaseEmbeddingService, texts: list[str]) -> list[float]:
    key = "||".join(sorted(texts))
    if key in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[key]
    if not texts:
        result = [0.0] * 768
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
        wl = w.lower().strip('.,;:!?()[]{}""''')
        if not wl:
            continue
        if wl not in _STOPWORDS:
            content_count += 1
        if w[0].isupper() and wl not in _STOPWORDS:
            content_count += 2
    if content_count == 0:
        return False
    first_word = words[0].lower().strip('.,;:!?()[]{}""''')
    if first_word in _PREPOSITION_STARTS or first_word in _VERB_STARTS:
        if content_count <= 1:
            return False
    return True


def infer_entity_type(name: str, embedding_service: Optional[BaseEmbeddingService] = None) -> str:
    """Infer entity type using suffix heuristics (fast path) + embedding similarity (slow path)."""
    lower = name.lower().strip()

    if not lower:
        return "concept"

    if any(suffix in lower for suffix in ['corp', 'inc', 'ltd', 'gmbh', 'company', 'org', 'ag', 'llc', 'corp.', 'inc.', 'ltd.', 'kg', '& co', 'e.k']):
        return 'organization'
    if any(suffix in lower for suffix in ['gate', 'system', 'framework', 'engine', 'server', 'protocol', 'database', 'platform', 'service', 'tool', 'api', 'sdk', 'runtime', 'client', 'agent', 'model']):
        return 'technology'
    if any(suffix in lower for suffix in ['theorie', 'effekt', 'mechanik', 'technologie', 'princip', 'rule', 'law', 'theorem', 'axiom', 'paradigm', 'verfahren']):
        return 'concept'
    if any(suffix in lower for suffix in ['strasse', 'straße', 'platz', 'allee', 'gasse', 'weg']):
        return 'location'
    if any(prefix in lower for prefix in ['dr ', 'mr ', 'ms ', 'mrs ', 'prof ', 'herr ', 'frau ', 'hr ', 'fr ']):
        return 'person'

    if embedding_service is None:
        return 'concept'

    try:
        name_emb = embedding_service.embed_for_storage(name)
        best_type = "concept"
        best_sim = -1.0

        for etype, prototypes in _ENTITY_PROTOTYPES.items():
            proto_emb = _get_prototype_embedding(embedding_service, prototypes)
            sim = sum(a * b for a, b in zip(name_emb, proto_emb))
            norm = (sum(a * a for a in name_emb) ** 0.5) * (sum(b * b for b in proto_emb) ** 0.5)
            if norm > 0:
                sim = sim / norm
            if sim > best_sim:
                best_sim = sim
                best_type = etype

        return best_type
    except Exception:
        return 'concept'


def extract_noun_phrases(text: str) -> list[str]:
    """Extract noun phrases using simple pattern matching (German + English). Filters stopword-only phrases."""
    phrases = set()

    patterns = [
        r'\b(?:der|die|das|den|dem|des|ein|eine|einen|einem|eines|the|a|an|this|that|these|those)\s+'
        r'(?:[A-ZÄÖÜ][a-zäöüß]+\s+)*[A-ZÄÖÜ][a-zäöüß]+(?:\s+(?:[A-ZÄÖÜ][a-zäöüß]+))*\b',
        r'\b[A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*\b',
        r'\b[A-Z][a-z]+[A-Z][a-zA-Z]*\b',
        r'\b[A-ZÄÖÜ]{2,}\b',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.UNICODE):
            candidate = match.group(0).strip()
            words = candidate.split()
            if len(words) > 4:
                continue
            if len(candidate) < 3:
                continue
            if candidate.lower() in {'the', 'and', 'or', 'der', 'die', 'das', 'ein', 'eine', 'und'}:
                continue
            if not is_content_phrase(words):
                continue
            phrases.add(candidate)

    return list(phrases)
