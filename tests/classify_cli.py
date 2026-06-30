#!/usr/bin/env python3
"""CLI helper for cross-language classifier consistency tests."""
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.extraction.classifier import QueryClassifier

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/classify_cli.py <query>")
        sys.exit(1)

    query = sys.argv[1]
    classifier = QueryClassifier()
    q_type, confidence = classifier.classify(query)
    # Output format: <type>|<confidence>
    print(f"{q_type}|{confidence}")