"""
Evaluate classifier accuracy: holdout F1, threshold analysis, cross-validation.
"""
import json
import os
import sys
import numpy as np
from pathlib import Path
from collections import Counter

os.environ["TQDM_DISABLE"] = "1"
PROJ = Path(__file__).resolve().parent.parent
os.chdir(str(PROJ))
sys.path.insert(0, str(PROJ))

from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import cross_val_score, StratifiedKFold, train_test_split
from sklearn.metrics import classification_report, f1_score, accuracy_score
from src.extraction.embedding_service import get_embedding_service


def load_all(limit_per_class=200):
    texts, labels = [], []
    for p in [
        "docs/data/training_queries.jsonl",
        "docs/data/trec_queries.jsonl",
        "docs/data/coqa_conversational.jsonl",
    ]:
        fp = PROJ / p
        if not fp.exists():
            continue
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
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
    if limit_per_class:
        limited_texts, limited_labels = [], []
        counts = {}
        for txt, lbl in zip(texts, labels):
            c = counts.get(lbl, 0)
            if c < limit_per_class:
                limited_texts.append(txt)
                limited_labels.append(lbl)
                counts[lbl] = c + 1
        return limited_texts, limited_labels
    return texts, labels


def main():
    texts, labels = load_all()
    print(f"Total samples: {len(texts)}")
    print(f"Class distribution: {dict(Counter(labels))}")

    emb_svc = get_embedding_service()
    embeddings = emb_svc.embed_batch(texts, for_storage=True)
    X = np.array(embeddings)
    le = LabelEncoder()
    y = le.fit_transform(labels)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = LogisticRegression(
        C=1.0,
        max_iter=1000,
        multi_class="ovr",
        class_weight="balanced",
        random_state=42,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average="macro")
    f1_weighted = f1_score(y_test, y_pred, average="weighted")

    print(f"\n=== Test set (20% holdout, n={len(y_test)}) ===")
    print(f"Accuracy:       {acc:.4f}")
    print(f"F1 macro:       {f1_macro:.4f}")
    print(f"F1 weighted:    {f1_weighted:.4f}")
    print()
    print("Per-class report:")
    print(classification_report(y_test, y_pred, target_names=le.classes_, digits=3))

    probs = model.predict_proba(X_test)
    pred_labels = [le.classes_[i] for i in y_pred]
    true_labels = [le.classes_[i] for i in y_test]
    max_conf = probs.max(axis=1)

    above = max_conf >= 0.6
    correct_above = sum(
        1 for i in range(len(y_test)) if above[i] and pred_labels[i] == true_labels[i]
    )
    total_above = sum(above)
    print(f"\n=== ML confidence >= 0.6 threshold analysis ===")
    print(
        f"Samples above 0.6: {total_above}/{len(y_test)} ({100*total_above/len(y_test):.1f}%)"
    )
    if total_above > 0:
        print(f"Accuracy on those: {correct_above / total_above:.4f}")
    else:
        print("N/A")

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(model, X, y, cv=cv, scoring="f1_macro")
    print(f"\n=== 5-Fold CV F1-macro ===")
    print(f"Fold scores: {[f'{s:.4f}' for s in cv_scores]}")
    print(f"Mean +/- std: {cv_scores.mean():.4f} +/- {cv_scores.std():.4f}")


if __name__ == "__main__":
    main()
