"""
STRATA - LightMem-style Entropy Gate
Composite Score aus Text-Entropy und Embedding-Novelty
Nur vor KG-Write, Raw Event Log bekommt immer alles!
"""
import hashlib
import math
import time
from typing import Optional, Dict, List
import requests
import numpy as np
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import our embedding service
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.extraction.embedding_service import get_embedding_service, BaseEmbeddingService
from src.extraction.entity_utils import infer_entity_type, extract_noun_phrases, is_content_phrase


def escape_surrealql(value: str) -> str:
    """Escape a string for safe use in a SurrealQL string literal."""
    import re
    value = value.replace('\\', '\\\\')
    value = value.replace("'", "\\'")
    value = value.replace('\n', '\\n')
    value = value.replace('\r', '\\r')
    value = value.replace('\t', '\\t')
    value = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', value)
    return value


class EntropyGateConfig:
    def __init__(
        self,
        alpha: float = 0.35,       # Gewicht Text-Entropy
        beta: float = 0.65,        # Gewicht Embedding-Novelty
        threshold: float = 0.55,   # Initialer Default; TODO per gate_log kalibrieren
        min_length: int = 10,      # Unter X Zeichen immer skippen
        max_length: int = 1000     # Über X Zeichen immer skippen
    ):
        self.alpha = alpha
        self.beta = beta
        self.threshold = threshold
        self.min_length = min_length
        self.max_length = max_length


class EntropyGate:
    def __init__(self, embedding_service: Optional[BaseEmbeddingService] = None, config: Optional[EntropyGateConfig] = None):
        self.config = config or EntropyGateConfig()
        self.min_length = self.config.min_length  
        self.max_length = self.config.max_length  
        self.surreal_url = os.getenv("SURREALDB_URL", "http://127.0.0.1:8000/sql")
        self.auth = (os.getenv("SURREALDB_USER", "root"), os.getenv("SURREALDB_PASS", "root"))
        self.surreal_ns = os.getenv("SURREALDB_NS", "strata")  
        self.surreal_db = os.getenv("SURREALDB_DB", "strata")  
        self.embedding_service = embedding_service or get_embedding_service()

    def _query_surreal(self, sql: str) -> List[Dict]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "text/plain; charset=utf-8",
        }
        full_sql = f"USE NS {self.surreal_ns} DB {self.surreal_db};\n{sql}"
        response = requests.post(self.surreal_url, data=full_sql.encode("utf-8"), headers=headers, auth=self.auth, timeout=30)
        try:
            data = response.json()
            if isinstance(data, list):
                return data
            else:
                return [data]
        except Exception as e:
            print(f"SurrealDB query failed: {e}")
            print(f"Response: {response.text}")
            return []

    def _escape_surrealql(self, value: str) -> str:
        return escape_surrealql(value)

    def _hash_content(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def calculate_char_entropy(self, text: str) -> float:
        """
        Shannon-Entropy auf Zeichenebene (wie LightMem)
        Gibt *unnormalisierte* Entropy zurück (typisch 0-4.5)
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

    def calculate_novelty(self, text: str) -> float:
        """
        Novelty basierend auf Embedding-Ähnlichkeit mit bisherigen Inhalten in SurrealDB.
        Gibt Wert zwischen 0 (keine novelty) und 1 (maximale novelty).
        Nutzt SurrealDB's native Vektor-Funktionen.
        """
        if not text.strip():
            return 0.0
            
        # Generate embedding for the text
        embedding = self.embedding_service.embed_for_storage(text)
        emb_str = "[" + ", ".join(map(str, embedding)) + "]"
        
        # Search for top-k similar vectors in SurrealDB
        # We use cosine similarity and calculate 1.0 - avg_similarity for novelty
        sql = f"""
        SELECT vector::similarity::cosine(embedding, {emb_str}) AS similarity
        FROM event
        WHERE embedding IS NOT NONE 
          AND array::len(embedding) = {len(embedding)}
          AND (forgotten IS NONE OR forgotten = false)
        ORDER BY similarity DESC
        LIMIT 5;
        """
        
        results = self._query_surreal(sql)
        
        # Extract the results (the _query_surreal here returns [ {status: OK, result: [...]}, ... ])
        actual_results = []
        if results and len(results) > 1: # Index 0 is USE, Index 1 is the query
            actual_results = results[1].get("result", [])
        
        if not actual_results:
            # No similar content found - maximum novelty
            return 1.0
        
        # Calculate average similarity (lower = more novel)
        avg_similarity = sum(float(r["similarity"]) for r in actual_results) / len(actual_results)
        
        # Return inverse (novelty = 1 - similarity)
        return 1.0 - max(0.0, min(1.0, avg_similarity))

    def should_extract(self, text: str) -> Dict[str, any]:
        """
        Entscheidet basierend auf Composite-Score ob Text in KG extrahiert werden soll
        """
        if len(text) < self.config.min_length:
            return {
                "decision": "skip",
                "reason": "text_too_short",
                "text_length": len(text),
                "min_length": self.config.min_length
            }
        if len(text) > self.config.max_length:
            return {
                "decision": "skip",
                "reason": "text_too_long",
                "text_length": len(text),
                "max_length": self.config.max_length
            }
        
        # Calculate individual scores
        text_entropy = self.calculate_char_entropy(text)
        novelty = self.calculate_novelty(text)
        
        # Normalize entropy to 0-1 range (assuming max entropy of ~4.5)
        normalized_entropy = min(text_entropy / 4.5, 1.0)
        
        # Calculate composite score
        composite_score = (self.config.alpha * normalized_entropy) + (self.config.beta * novelty)
        
        # Make decision
        decision = "extract" if composite_score >= self.config.threshold else "ignore"
        
        # Log decision to database
        self._log_decision(text, normalized_entropy, novelty, composite_score, decision)
        
        return {
            "decision": decision,
            "text_entropy": text_entropy,
            "normalized_entropy": normalized_entropy,
            "novelty": novelty,
            "composite_score": composite_score,
            "threshold": self.config.threshold,
            "alpha": self.config.alpha,
            "beta": self.config.beta,
            "reason": f"Composite score {composite_score:.3f} {'meets' if decision == 'extract' else 'does not meet'} threshold {self.config.threshold:.3f}"
        }

    def _log_decision(self, text: str, entropy: float, novelty: float, composite_score: float, decision: str):
        """Log the entropy gate decision to database"""
        try:
            content_hash = self._hash_content(text)
            decision_escaped = self._escape_surrealql(decision)
            sql = f"""
            CREATE gate_log SET 
                content_hash = '{content_hash}',
                text_score = {entropy},
                novelty = {novelty},
                gate_score = {composite_score},
                decision = '{decision_escaped}';
            """
            result = self._query_surreal(sql)
            if not result or len(result) < 2 or result[1].get("status") != "OK":
                import sys
                sys.stderr.write(f"[Gate] _log_decision failed: {result}\n")
        except Exception as e:
            import sys
            sys.stderr.write(f"[Gate] _log_decision exception: {e}\n")

    def _extract_candidate_entities(self, text: str) -> List[str]:
        """
        Extrahiert Kandidaten-Entities aus dem Text.
        Nutzt Noun-Phrase-Extraktion (erkennt auch Kleinschreibung, nicht-englische Namen).
        Fallback auf grossgeschriebene Wörter und CamelCase.
        """
        import re as _re
        candidates = set()

        # 1. Noun-Phrase-Extraktion (erkennt auch deutsche Substantive)
        noun_phrases = extract_noun_phrases(text)
        for phrase in noun_phrases:
            candidates.add(phrase)

        # 2. Explizit nach deutschsprachigen Entities suchen
        #    Deutsche Nomen werden großgeschrieben, aber nicht unbedingt
        gmc_patterns = [
            _re.compile(r'\b(?:Der|Die|Das|Ein|Eine)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*)\b'),
            _re.compile(r'\b[A-ZÄÖÜ][a-zäöüß]+(?:maschine|system|werk|zeug|stoff|kraft|daten|prozess|steuerung|anlage|gerät)\b'),
            _re.compile(r'\b(?:[A-Z][a-z]+-)+[A-Z][a-z]+\b'),
        ]
        for pattern in gmc_patterns:
            for match in pattern.finditer(text):
                candidate = match.group(1) if match.lastindex else match.group(0)
                candidate = candidate.strip()
                if len(candidate) >= 3:
                    candidates.add(candidate)

        # 3. Mehrteilige Konzepte ohne Grossbuchstaben (z.B. "quantum computing", "social contract")
        concept_patterns = [
            _re.compile(r'\b[a-zäöüß]{3,}(?:\s+[a-zäöüß]{3,}){1,2}\b'),
        ]
        for pattern in concept_patterns:
            for match in pattern.finditer(text):
                candidate = match.group(0).strip()
                words = candidate.split()
                if len(words) >= 2 and len(candidate) >= 5:
                    if is_content_phrase(words):
                        candidates.add(candidate)

        # 4. CamelCase-Wörter (z.B. "EntropyGate", "FastMCP")
        for match in _re.finditer(r'\b([A-Z][a-z]+[A-Z][a-zA-Z]*)\b', text):
            candidate = match.group(1).strip()
            if len(candidate) >= 3:
                candidates.add(candidate)

        # 5. Abkürzungen (z.B. "ATP", "CRISPR", "DNA")
        for match in _re.finditer(r'\b([A-Z]{2,})\b', text):
            candidate = match.group(1).strip()
            if len(candidate) >= 2:
                candidates.add(candidate)

        return list(candidates)

    def _compute_relation_confidence(self, text: str, entity_a: str, entity_b: str) -> tuple[str, float]:
        """Berechne dynamische Konfidenz und Relationstyp zwischen zwei Entities basierend auf Embedding."""
        emb_service = self.embedding_service
        try:
            emb_a = emb_service.embed_for_storage(entity_a)
            emb_b = emb_service.embed_for_storage(entity_b)
            dot = sum(a * b for a, b in zip(emb_a, emb_b))
            norm = (sum(a * a for a in emb_a) ** 0.5) * (sum(b * b for b in emb_b) ** 0.5)
            similarity = dot / norm if norm > 0 else 0.0
            confidence = max(0.0, min(1.0, similarity))
            label = self._infer_relation_type(text, entity_a, entity_b, confidence)
            return label, confidence
        except Exception:
            return "co_occurs_with", 0.5

    def _infer_relation_type(self, text: str, entity_a: str, entity_b: str, confidence: float) -> str:
        """Bestimme den Beziehungstyp zwischen zwei Entities."""
        lower_text = text.lower()
        a_lower = entity_a.lower()
        b_lower = entity_b.lower()

        works_verbs = ['works at', 'works for', 'employed by', 'arbeitet bei', 'arbeitet für',
                       'angestellt bei', 'joined', 'led by', 'geführt von']
        for verb in works_verbs:
            if verb in lower_text:
                if a_lower in lower_text.split(verb)[0] if verb in lower_text else False:
                    return "works_at"

        located_verbs = ['located in', 'based in', 'situated in', 'befindet sich in', 'hat seinen sitz in']
        for verb in located_verbs:
            if verb in lower_text:
                return "located_in"

        created_verbs = ['created', 'developed', 'built', 'founded', 'gründete', 'entwickelte',
                         'erfand', 'implementierte']
        for verb in created_verbs:
            if verb in lower_text:
                return "created"

        if confidence > 0.85:
            return "strongly_related"
        elif confidence > 0.7:
            return "related_to"
        elif confidence > 0.5:
            return "co_occurs_with"
        else:
            return "weakly_related"

    def _ensure_entity(self, name: str) -> Optional[str]:
        """Legt eine Entity an, falls sie noch nicht existiert. Gibt die ID zurück."""
        name_escaped = self._escape_surrealql(name)
        entity_type = infer_entity_type(name, self.embedding_service)
        
        # Prüfen ob Entity bereits existiert
        check_sql = f"SELECT id FROM entity WHERE name = '{name_escaped}' LIMIT 1;"
        check_result = self._query_surreal(check_sql)
        if check_result and len(check_result) > 1:
            existing = check_result[1].get("result", [])
            if existing and len(existing) > 0:
                return existing[0].get("id")
        
        # Neue Entity anlegen
        create_sql = f"""
        CREATE entity SET 
            name = '{name_escaped}',
            type = '{entity_type}';
        """
        result = self._query_surreal(create_sql)
        if result and len(result) > 1:
            entity_result = result[1].get("result", [])
            if entity_result and len(entity_result) > 0:
                return entity_result[0].get("id")
        return None

    def _extract_to_kg(self, text: str, event_id: str, debug: bool = False):
        """
        Extrahiert Entities und semantische Beziehungen in den Knowledge Graph.
        Nutzt Embedding-Similarity für dynamische Konfidenz statt fixer Co-Occurrence.
        """
        candidates = self._extract_candidate_entities(text)
        if not candidates:
            if debug:
                print(f"  [KG] No candidate entities found in text")
            return {"entities_created": 0, "facts_created": 0}

        if debug:
            print(f"  [KG] Found candidate entities: {candidates}")

        entities_created = 0
        facts_created = 0
        entity_ids = []
        entity_names = []

        for name in candidates:
            eid = self._ensure_entity(name)
            if eid:
                entity_ids.append(eid)
                entity_names.append(name)
                entities_created += 1
                if debug:
                    print(f"  [KG] Entity: {name} -> {eid}")

        if len(entity_ids) >= 2:
            for i in range(len(entity_ids)):
                for j in range(i + 1, len(entity_ids)):
                    try:
                        predicate, confidence = self._compute_relation_confidence(
                            text, entity_names[i], entity_names[j]
                        )
                        if confidence >= 0.3:
                            relate_sql = f"""
                            RELATE {entity_ids[i]}->fact->{entity_ids[j]} 
                            SET predicate = '{predicate}',
                                source_event = {event_id},
                                confidence = {confidence:.4f};
                            """
                            relate_result = self._query_surreal(relate_sql)
                            if relate_result and len(relate_result) > 1 and relate_result[1].get("status") == "OK":
                                facts_created += 1
                                if debug:
                                    print(f"  [KG] Fact: {entity_names[i]} -[{predicate} ({confidence:.2f})]-> {entity_names[j]}")
                    except Exception as e:
                        if debug:
                            print(f"  [KG] Error creating fact: {e}")

        for eid in entity_ids:
            try:
                relate_sql = f"""
                RELATE {event_id}->fact->{eid} 
                SET predicate = 'mentions',
                    confidence = 0.8;
                """
                relate_result = self._query_surreal(relate_sql)
                if relate_result and len(relate_result) > 1 and relate_result[1].get("status") == "OK":
                    facts_created += 1
            except Exception as e:
                if debug:
                    print(f"  [KG] Error creating mention fact: {e}")

        return {"entities_created": entities_created, "facts_created": facts_created}

    def ingest(self, text: str, source: str = "unknown", debug: bool = False) -> Optional[str]:
        """
        Hauptfunktion: Ingest eines Textes in das Memory System
        1. IMMER in Raw Event Log speichern
        2. Entropy Gate entscheiden lassen ob KG-Extraction
        3. Bei 'extract': Entities und Facts in den Knowledge Graph extrahieren
        """

        if not text or not text.strip():
            print(f"Error: Empty or whitespace-only content rejected (source={source})")
            return None
        if len(text) > 100_000:
            print(f"Error: Content exceeds maximum storage length ({len(text)} > 100000) (source={source})")
            return None
        if '\x00' in text:
            print(f"Error: Content contains null bytes, rejecting (source={source})")
            return None

        # 0. Dedup: Prüfen ob exakt gleicher Content mit gleicher Source bereits existiert
        content_hash = self._hash_content(text)
        source_escaped_dedup = self._escape_surrealql(source)
        dedup_sql = f"""
        SELECT id FROM event 
        WHERE content_hash = '{content_hash}'
          AND source = '{source_escaped_dedup}'
          AND (forgotten IS NONE OR forgotten = false)
        LIMIT 1;
        """
        dedup_result = self._query_surreal(dedup_sql)
        if dedup_result and len(dedup_result) > 1:
            existing = dedup_result[1].get("result", [])
            if existing and len(existing) > 0:
                event_id = existing[0].get("id")
                if debug:
                    print(f"  [Dedup] Found existing event {event_id} for identical content and source")
                gate_result = self.should_extract(text)
                if gate_result["decision"] == "extract" and event_id:
                    kg_result = self._extract_to_kg(text, event_id, debug)
                return event_id

        # 1. IMMER in Raw Event Log speichern (ohne Gate!)
        embedding = self.embedding_service.embed_for_storage(text)
        text_escaped = self._escape_surrealql(text)
        source_escaped = self._escape_surrealql(source)
        sql = f"""
        CREATE event SET 
            content = '{text_escaped}',
            content_hash = '{content_hash}',
            source = '{source_escaped}',
            embedding = {embedding};
        """
        event_id = None
        result = None
        try:
            result = self._query_surreal(sql)
            if result and len(result) > 1:
                event_result = result[1].get("result", [])
                if event_result and isinstance(event_result, list) and len(event_result) > 0:
                    event_id = event_result[0].get("id")
        except Exception as e:
            import sys
            sys.stderr.write(f"[EntropyGate] Error saving to event log: {e}\n")
            if result:
                sys.stderr.write(f"[EntropyGate]   SurrealDB response: {result}\n")
        
        if event_id is None:
            import sys
            sys.stderr.write(f"[EntropyGate] WARNING: ingest returned no event_id\n")
            sys.stderr.write(f"[EntropyGate]   source={source}, content_length={len(text)}, hash={content_hash[:16]}...\n")
        
        # 2. Entropy Gate prüfen
        gate_result = self.should_extract(text)
        
        if debug:
            print(f"Entropy Gate Decision: {gate_result}")
        
        # 3. Falls extract: starte KG-Extraction
        if gate_result["decision"] == "extract" and event_id:
            kg_result = self._extract_to_kg(text, event_id, debug)
            if debug:
                print(f"  [KG] Extraction complete: {kg_result}")
        
        return event_id
