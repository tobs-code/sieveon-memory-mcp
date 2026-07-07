"""
Train the ML classifier with a capped subset of training data (1000 TREC samples).
Saves the model to docs/data/classifier_model.pkl so future starts skip training.
"""

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

os.environ["TQDM_DISABLE"] = "1"

from src.extraction.classifier import QueryClassifier

TREC_PATH = PROJECT_ROOT / "docs" / "data" / "trec_queries.jsonl"
TRAINING_PATH = PROJECT_ROOT / "docs" / "data" / "training_queries.jsonl"
COQA_PATH = PROJECT_ROOT / "docs" / "data" / "coqa_conversational.jsonl"
TREC_LIMIT = 1000


def load_jsonl(path, limit=None):
    texts, labels = [], []
    if not path.exists():
        print(f"  skipping (not found): {path.name}")
        return texts, labels
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break
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
    print(f"  loaded {len(texts)} samples from {path.name}")
    return texts, labels


def main():
    print("Training classifier...\n")

    all_texts, all_labels = [], []

    texts, labels = load_jsonl(TREC_PATH, limit=TREC_LIMIT)
    all_texts.extend(texts)
    all_labels.extend(labels)

    texts, labels = load_jsonl(TRAINING_PATH)
    all_texts.extend(texts)
    all_labels.extend(labels)

    texts, labels = load_jsonl(COQA_PATH)
    all_texts.extend(texts)
    all_labels.extend(labels)

    print(f"\nTotal: {len(all_texts)} samples")

    classifier = QueryClassifier()
    classifier.train(all_texts, all_labels)

    model_path = PROJECT_ROOT / "docs" / "data" / "classifier_model.pkl"
    if model_path.exists():
        print(f"\nModel saved to {model_path}")
    else:
        print("\nWarning: model file was not created")


if __name__ == "__main__":
    main()
