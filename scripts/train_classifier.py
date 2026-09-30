"""
Train the ML classifier on all registered training files
(classifier._TRAINING_PATHS) with a per-class cap, then save to
docs/data/classifier_model.pkl so future starts skip training.

Usage:
    python scripts/train_classifier.py [--cap 600]
"""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

os.environ["TQDM_DISABLE"] = "1"

from src.extraction.classifier import QueryClassifier  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Retrain the query classifier")
    ap.add_argument("--cap", type=int, default=600,
                    help="max samples per class (default 600)")
    args = ap.parse_args()

    print("Training classifier (all registered sources)...\n")
    classifier = QueryClassifier()
    texts, labels = classifier._ml._load_training_data()
    print(f"  loaded {len(texts)} samples (pre-cap)")

    # Delete stale model so _ensure_ml cannot short-circuit anything;
    # train() below saves the fresh model itself.
    from src.extraction.classifier import _ML_MODEL_PATH
    if _ML_MODEL_PATH.exists():
        _ML_MODEL_PATH.unlink()
        print("  removed stale model")

    classifier._ml.train(texts, labels, cap_per_class=args.cap)

    if _ML_MODEL_PATH.exists():
        print(f"\nModel saved to {_ML_MODEL_PATH}")
        return 0
    print("\nWarning: model file was not created")
    return 1


if __name__ == "__main__":
    sys.exit(main())
