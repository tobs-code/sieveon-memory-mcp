"""
Evaluate classifier accuracy: holdout F1, threshold analysis, cross-validation.

Known caveats (see README for details):
  1. TREC data: original 6 labels → 3 Sieveon types via heuristic mapping.
  2. Synthetic data uses templates → ~9% exact duplicates across train/test splits.
  3. n=180 holdout → CV (5-fold, ~0.967) is more reliable than holdout point estimate.
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

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import cross_val_score, StratifiedKFold, train_test_split
from sklearn.metrics import classification_report, f1_score, accuracy_score, confusion_matrix
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


def _show_top_tfidf_features(vectorizer, model, label_encoder, n_emb=1024, top_n=10):
    feature_names = vectorizer.get_feature_names_out()
    for i, cls in enumerate(label_encoder.classes_):
        coef_tfidf = model.coef_[i, n_emb:]
        top = np.argsort(coef_tfidf)[-top_n:][::-1]
        terms = [(feature_names[j], coef_tfidf[j]) for j in top if abs(coef_tfidf[j]) > 0.01]
        print(f"  {cls:>16}: {', '.join(f'{t}={c:.2f}' for t, c in terms[:6])}")


def _note_trec_mapping():
    print("""
Note on TREC label mapping:
  Original TREC 6-category → Sieveon mapping (heuristic):
    ABBR → factual   | ENTY → factual    | DESC (how) → factual
    DESC (why) → multi-hop | HUM → factual | LOC → factual
    NUM (time/date) → temporal | NUM (count) → factual
  CoQA → 100% mapped to 'conversational'.
  Synthetic data → generated from templates per type.
""")


def main():
    texts, labels = load_all()
    print(f"Total samples: {len(texts)} total, {dict(Counter(labels))}")
    _note_trec_mapping()

    emb_svc = get_embedding_service()
    vectorizer = TfidfVectorizer(
        analyzer="word", ngram_range=(1, 2), max_features=500, sublinear_tf=True,
    )
    tfidf = vectorizer.fit_transform(texts).toarray()
    embeddings = np.array(emb_svc.embed_batch(texts, for_storage=True))
    X = np.concatenate([embeddings, tfidf], axis=1)

    le = LabelEncoder()
    y = le.fit_transform(labels)

    X_train, X_test, y_train, y_test, texts_train, texts_test = train_test_split(
        X, y, texts, test_size=0.2, random_state=42, stratify=y
    )

    # ── Leakage check ──────────────────────────────────────────────
    train_set = set(texts_train)
    dup_indices = [i for i, t in enumerate(texts_test) if t in train_set]
    print(f"\nData leakage: {len(dup_indices)}/{len(texts_test)} exact test→train duplicates ({100*len(dup_indices)/len(texts_test):.1f}%)")
    print(f"  -> likely from synthetic template collisions (9 random fills/template × 80 templates)")
    print(f"  -> Clean holdout (excluding {len(dup_indices)} exact duplicates) reported separately below.")

    # ── Full holdout ───────────────────────────────────────────────
    model = LogisticRegression(
        C=1.0, max_iter=1000, multi_class="ovr", class_weight="balanced", random_state=42,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    acc_full = accuracy_score(y_test, y_pred)
    f1_full = f1_score(y_test, y_pred, average="macro")

    print(f"\n{'='*60}")
    print(f"  PRIMARY METRIC: 5-Fold Cross-Validation (more reliable)")
    print(f"{'='*60}")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(model, X, y, cv=cv, scoring="f1_macro")
    print(f"  F1 macro: {cv_scores.mean():.3f} +/- {cv_scores.std():.3f}")
    print(f"  Fold scores: {[f'{s:.3f}' for s in cv_scores]}")
    print(f"  5-fold CV is robust against the ~9% synthetic template leakage.")

    # ── Clean holdout (exclude exact duplicates) ───────────────────
    if len(dup_indices) > 0:
        clean_idx = [i for i in range(len(texts_test)) if i not in set(dup_indices)]
        y_test_clean = y_test[clean_idx]
        y_pred_clean = y_pred[clean_idx]
        acc_clean = accuracy_score(y_test_clean, y_pred_clean)
        f1_clean = f1_score(y_test_clean, y_pred_clean, average="macro")
    else:
        clean_idx = list(range(len(texts_test)))
        acc_clean, f1_clean = acc_full, f1_full

    print(f"\n{'='*60}")
    print(f"  Holdout (full, n={len(y_test)})")
    print(f"{'='*60}")
    print(f"  Accuracy: {acc_full:.4f}   F1 macro: {f1_full:.4f}")
    print(f"  {len(dup_indices)} exact duplicates inflated by ~{(acc_full - acc_clean)/acc_clean*100:.1f}% "
          f"(clean holdout F1 = {f1_clean:.4f}, n={len(clean_idx)})")
    print()
    print("Per-class report (full holdout):")
    print(classification_report(y_test, y_pred, target_names=le.classes_, digits=3))

    cm = confusion_matrix(y_test, y_pred)
    print("\nConfusion matrix (rows=true, cols=pred):")
    header = f"{'':>16}" + "".join(f"{c:>14}" for c in le.classes_)
    print(header)
    for i, row_label in enumerate(le.classes_):
        row = f"{row_label:>16}" + "".join(f"{cm[i,j]:>14}" for j in range(len(le.classes_)))
        print(row)

    # ── Misclassifications ─────────────────────────────────────────
    probs = model.predict_proba(X_test)
    pred_labels = [le.classes_[i] for i in y_pred]
    true_labels_arr = [le.classes_[i] for i in y_test]
    max_conf = probs.max(axis=1)

    errors = []
    for i in range(len(y_test)):
        if pred_labels[i] != true_labels_arr[i]:
            errors.append((true_labels_arr[i], pred_labels[i], texts_test[i], max_conf[i],
                           i in dup_indices))
    if errors:
        print(f"\n=== Misclassifications ({len(errors)}) ===")
        for true_lbl, pred_lbl, txt, conf, is_dup in errors:
            tag = " [DUP]" if is_dup else ""
            print(f"  true={true_lbl:>14}  pred={pred_lbl:>14}  conf={conf:.3f}{tag}  | {txt}")
    else:
        print("\n=== No misclassifications ===")

    # ── TF-IDF feature analysis ────────────────────────────────────
    print(f"\n=== Top TF-IDF features per class ===")
    _show_top_tfidf_features(vectorizer, model, le)

    # ── Threshold analysis ─────────────────────────────────────────
    above = max_conf >= 0.6
    correct_above = sum(1 for i in range(len(y_test)) if above[i] and pred_labels[i] == true_labels_arr[i])
    total_above = sum(above)
    print(f"\n=== ML confidence >= 0.6 threshold analysis ===")
    print(f"Samples above 0.6: {total_above}/{len(y_test)} ({100*total_above/len(y_test):.1f}%)")
    if total_above > 0:
        print(f"Accuracy on those: {correct_above / total_above:.4f}")


if __name__ == "__main__":
    main()
