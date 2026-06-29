"""
Extractor Integration for Strata
Coordinates the integration between extraction components and the broader system
"""
from typing import Dict, Any, Optional
import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.extraction.coarse_extractor import ExtractionPipeline
from src.extraction.entropy_gate import EntropyGate
from src.extraction.embedding_service import get_embedding_service


class ExtractorIntegration:
    """Main integration point for extraction components"""
    
    def __init__(self, entropy_gate: Optional[EntropyGate] = None):
        self.pipeline = ExtractionPipeline()
        self.entropy_gate = entropy_gate or EntropyGate()
        self.embedding_service = get_embedding_service()
        
    def process_text(self, text: str, source: str = "unknown") -> Dict[str, Any]:
        """
        Process text through the full extraction pipeline
        Applies entropy filtering to determine if extraction should proceed
        """
        # First, check with entropy gate to see if extraction is worthwhile
        entropy_result = self.entropy_gate.should_extract(text)
        
        result = {
            "text": text,
            "source": source,
            "entropy_gate_result": entropy_result,
            "extraction_result": None,
            "applied_extraction": False
        }
        
        # Only perform full extraction if entropy gate approves
        if entropy_result["decision"] == "extract":
            extraction_result = self.pipeline.process(text, apply_entropy_filter=False)
            result["extraction_result"] = extraction_result
            result["applied_extraction"] = True
            
            # Store extracted entities in the knowledge graph
            self._store_extracted_entities(extraction_result)
        
        return result
    
    def _store_extracted_entities(self, extraction_result: Dict[str, Any]):
        """Store extracted entities in the knowledge graph"""
        # This would integrate with the knowledge graph storage
        # For now, we'll just print what would be stored
        entities = extraction_result.get("entities", {})
        relations = extraction_result.get("relations", [])
        
        print(f"Would store {extraction_result['entity_count']} entities and {extraction_result['relation_count']} relations in knowledge graph")


# Example usage
if __name__ == "__main__":
    # Initialize the integrated extractor
    extractor = ExtractorIntegration()
    
    # Test with various types of content
    test_texts = [
        "John Smith works at Acme Corp in New York.",
        "The weather is nice today.",
        "Meeting scheduled for tomorrow at 3 PM with Alice Johnson.",
        "The quarterly report shows increased revenue.",
        "Short text."  # This might be filtered by entropy gate
    ]
    
    for i, text in enumerate(test_texts):
        print(f"\n--- Processing text {i+1} ---")
        result = extractor.process_text(text, f"test_source_{i+1}")
        
        print(f"Text: {text}")
        print(f"Entropy gate decision: {result['entropy_gate_result']['decision']}")
        print(f"Applied extraction: {result['applied_extraction']}")
        
        if result['applied_extraction']:
            extraction = result['extraction_result']
            print(f"Found {extraction['entity_count']} entities and {extraction['relation_count']} relations")