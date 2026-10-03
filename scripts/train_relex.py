"""Minimal GLiNER-Relex training entrypoint.

Reads training JSONL conforming to docs/eval_relex_training_contract_v1.json,
validates schema, label map, entity spans and the split-hygiene rule
(family/pair ids must not reach the model), fine-tunes the frozen base
model with gliner.training.Trainer, and writes checkpoint + manifest.

Contract constants (labels, seed, base model, forbidden features) come from
the contract file, never from CLI flags. --fold-id is carried into the
manifest verbatim; the runner assigns it, this script never derives it.

Usage:
    python scripts/train_relex.py --train <training.jsonl> --out <dir> --dry-run
    python scripts/train_relex.py --train <training.jsonl> --out <dir> \\
        --epochs 1 --batch-size 2 [--fold-id <id>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "docs" / "eval_relex_training_contract_v1_11.json").read_text())

LABELS = tuple(CONTRACT["labels"])
FORBIDDEN = tuple(CONTRACT["forbidden_model_features"])
ENTITY_INVENTORY = list(CONTRACT["entity_inventory"])
REGIME = CONTRACT.get("training_regime", {})
REL_PROMPTS = list(REGIME.get("train_relation_prompts", ["provides"]))


def validate_example(ex: dict, lineno: int) -> list[str]:
    problems: list[str] = []
    for key in CONTRACT["training_example_schema"]["required"]:
        if key not in ex:
            problems.append(f"line {lineno}: missing {key}")
    if problems:
        return problems
    if ex["relation"] not in LABELS:
        problems.append(f"line {lineno}: bad relation {ex['relation']!r}")
    sent = ex["sentence"]
    for role in ("X", "Y"):
        ent = ex["entities"].get(role, {})
        span = sent[ent.get("start", -1):ent.get("end", -1)]
        if span != ent.get("text", ""):
            problems.append(f"line {lineno}: {role} span does not match sentence")
    for j, extra in enumerate(ex.get("extra_entities", [])):
        span = sent[extra.get("start", -1):extra.get("end", -1)]
        if span != extra.get("text", ""):
            problems.append(f"line {lineno}: extra[{j}] span does not match sentence")
        if extra.get("label") not in ENTITY_INVENTORY:
            problems.append(f"line {lineno}: extra[{j}] label outside inventory")
        for role in ("X", "Y"):
            ent = ex["entities"].get(role, {})
            if not (extra.get("end", -1) <= ent.get("start", 10**9)
                    or extra.get("start", -1) >= ent.get("end", -1)):
                problems.append(f"line {lineno}: extra[{j}] overlaps {role}")
    elabels = ex.get("entity_labels", {})
    for role in ("X", "Y"):
        lab = elabels.get(role)
        if lab not in ENTITY_INVENTORY:
            problems.append(f"line {lineno}: {role} entity label {lab!r} "
                            f"outside production inventory")
    for feat in FORBIDDEN:
        if feat in ex and feat not in ("construction_family_id", "pair_id",
                                       "provenance", "split_key", "cue_phrase"):
            problems.append(f"line {lineno}: forbidden model feature {feat}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fold-id", default=None)
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch-size", type=int, default=2)
    args = ap.parse_args()

    try:
        rows = [json.loads(line) for line in
                Path(args.train).read_text(encoding="utf-8").splitlines()
                if line.strip()]
    except json.JSONDecodeError as exc:
        print(f"  PROBLEM input is not JSONL: {exc}", file=sys.stderr)
        return 1
    problems: list[str] = []
    for i, ex in enumerate(rows, 1):
        problems += validate_example(ex, i)
    if problems:
        for p in problems:
            print(f"  PROBLEM {p}")
        return 1

    blob = "\n".join(f'{e["sentence"]}|{e["entities"]["X"]["text"]}|'
                     f'{e["entities"]["Y"]["text"]}|{e["relation"]}' for e in rows)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    print(f"  examples: {len(rows)}  digest: {digest}")
    print(f"  labels: {LABELS}  split-hygiene: {FORBIDDEN} excluded from features")

    if args.dry_run:
        print("  dry-run: contract valid, no training executed")
        return 0

    return run_training(rows, digest, args)


def _words_with_offsets(sentence: str) -> list[tuple[str, int, int]]:
    words: list[tuple[str, int, int]] = []
    for match in __import__("re").finditer(r"\S+", sentence):
        words.append((match.group(0), match.start(), match.end()))
    return words


def _word_index(words: list[tuple[str, int, int]], start: int, end: int) -> tuple[int, int]:
    """Char span -> INCLUSIVE word span.

    The gliner processor indexes entity spans inclusively on both ends
    (token labels mark st:ed+1, span mapping drops end >= num_tokens),
    so the exclusive char end converts to last-word index, not one past it.
    Getting this wrong silently drops sentence-final entities and their
    relations.
    """
    lo = next(i for i, (_, ws, we) in enumerate(words) if ws <= start < we)
    hi = next(i for i, (_, ws, we) in enumerate(words) if ws < end <= we)
    return lo, hi


def to_gliner_sample(ex: dict) -> dict:
    """Contract example -> tokens + typed entity/relation word indices.

    X and Y carry their source production entity types (contract v1.1
    entity_labels); prompts offer the full production inventory. The only
    relation under supervision stays 'provides': clean_positive carries
    (X, Y, provides), hard negatives carry the same typed spans with no
    relation. Metadata never leaves this function.
    """
    sent = ex["sentence"]
    words = _words_with_offsets(sent)
    tokens = [w for w, _, _ in words]
    spans = {}
    for order, role in enumerate(("X", "Y")):
        ent = ex["entities"][role]
        spans[role] = _word_index(words, ent["start"], ent["end"])
    order = sorted(spans, key=lambda r: spans[r][0])
    elabels = ex.get("entity_labels", {})
    ner = [(spans[r][0], spans[r][1], elabels.get(r, "concept")) for r in order]
    dense = list(ner)
    for extra in ex.get("extra_entities", []):
        w = _word_index(words, extra["start"], extra["end"])
        dense.append((w[0], w[1], extra["label"]))
    dense = sorted(set(dense), key=lambda t: (t[0], t[1]))
    relations: list[tuple[int, int, str]] = []
    if ex["relation"] == "provides":
        head = order.index("X")
        tail = order.index("Y")
        relations = [(head, tail, "provides")]
    return {"tokens": tokens, "ner": ner, "dense_ner": dense,
            "relations": relations}


def run_training(rows: list[dict], digest: str, args) -> int:
    import torch
    from torch.utils.data import Dataset
    from gliner import GLiNER
    from gliner.data_processing import (
        RelationExtractionTokenProcessor, WordsSplitter,
    )
    from gliner.training import Trainer, TrainingArguments

    base = CONTRACT["model"]["base"]
    seed = CONTRACT["reproducibility"]["seed"]
    print(f"  loading base {base}")
    model = GLiNER.from_pretrained(base)
    for key in ("span_loss_coef", "adjacency_loss_coef", "relation_loss_coef"):
        if key in REGIME:
            setattr(model.config, key, REGIME[key])
    print(f"  loss coefs: span={model.config.span_loss_coef} "
          f"adj={getattr(model.config, 'adjacency_loss_coef', None)} "
          f"rel={getattr(model.config, 'relation_loss_coef', None)}")
    pattern = REGIME.get("trainable_name_pattern")
    if pattern:
        frozen, kept = 0, 0
        for name, param in model.named_parameters():
            if pattern in name:
                param.requires_grad = True
                kept += 1
            else:
                param.requires_grad = False
                frozen += 1
        print(f"  head-only: {kept} trainable / {frozen} frozen (pattern {pattern!r})")
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(base)
    processor = RelationExtractionTokenProcessor(
        model.config, tokenizer, WordsSplitter("whitespace"))
    classes_to_id = {lab: i + 1 for i, lab in enumerate(ENTITY_INVENTORY)}
    rel_classes_to_id = {"provides": 1}

    samples = [to_gliner_sample(ex) for ex in rows]
    for s in samples:
        s["classes_to_id"] = dict(classes_to_id)
        s["rel_class_to_ids"] = dict(rel_classes_to_id)
        s["entities"] = s.pop("ner")
        s["dense_entities"] = s.pop("dense_ner")

    class _DS(Dataset):
        def __len__(self):
            return len(samples)

        def __getitem__(self, i):
            return samples[i]

    def collate(batch):
        return _collate_impl(processor, batch, classes_to_id,
                             rel_classes_to_id, ENTITY_INVENTORY, REL_PROMPTS)

    use_cpu = not torch.cuda.is_available()
    targs = TrainingArguments(
        output_dir=args.out, seed=seed, do_train=True,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=REGIME.get("learning_rate", 5e-5),
        others_lr=REGIME.get("others_lr"),
        save_strategy="no", logging_steps=1, report_to="none",
        use_cpu=use_cpu, dataloader_drop_last=False,
    )
    trainer = Trainer(model=model, args=targs, train_dataset=_DS(),
                      data_collator=collate)
    trainer.train()

    out = Path(args.out)
    model.save_pretrained(str(out))
    weight_files = sorted(out.glob("*.safetensors")) or sorted(out.glob("*.bin"))
    ckpt_digest = hashlib.sha256(weight_files[0].read_bytes()).hexdigest()
    manifest = {
        "base_model": base,
        "label_map": list(LABELS),
        "seed": seed,
        "contract_version": CONTRACT["version"],
        "fold_id": args.fold_id,
        "training_data_digest": digest,
        "training_examples": len(rows),
        "epochs": args.epochs,
        "checkpoint_digest": ckpt_digest,
        "trainable_name_pattern": REGIME.get("trainable_name_pattern"),
        "train_relation_prompts": list(REL_PROMPTS),
        "loss_coefs": {k: getattr(model.config, k, None) for k in
                       ("span_loss_coef", "adjacency_loss_coef", "relation_loss_coef")},
    }
    (out / "training_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  trained: checkpoint {out} digest {ckpt_digest[:16]}")
    return 0

def shift_spans(ner_lists, plens):
    """Shift word spans of ner lists into prompted coordinates."""
    return [[(a + pl, b + pl, lab) for (a, b, lab) in ner]
            for ner, pl in zip(ner_lists, plens)]


def sparse_relation_batch(processor, samples, classes_to_id,
                          rel_classes_to_id, entity_prompts, rel_prompts):
    """Full relation-target computation from the sparse X/Y view only.

    v1.11 sampler decoupling: this is the single code path that feeds
    relation targets into training. Dense extra entities never enter it.
    Returns the batch dict with adj_matrix/rel_matrix tensors.
    """
    n = len(samples)
    raw_tokens = [s["tokens"] for s in samples]
    prompted, plens = processor.prepare_inputs(
        raw_tokens, entities=[list(entity_prompts)] * n,
        relations=[list(rel_prompts)] * n)
    sparse_shifted = shift_spans([s["entities"] for s in samples], plens)
    pre = [processor.preprocess_example(
        pt, ner, classes_to_id,
        s["relations"], rel_classes_to_id)
        for pt, ner, s in zip(prompted, sparse_shifted, samples)]
    merged = processor.create_batch_dict(
        pre, [dict(classes_to_id)] * n,
        [{v: k for k, v in classes_to_id.items()}] * n,
        [dict(rel_classes_to_id)] * n,
        [{v: k for k, v in rel_classes_to_id.items()}] * n)
    merged["rel_class_to_ids"] = [dict(rel_classes_to_id)] * n
    merged["tokens"] = raw_tokens
    merged["entities"] = [s["entities"] for s in samples]
    adj, rel = processor.create_relation_labels(merged)
    merged["adj_matrix"] = adj
    merged["rel_matrix"] = rel
    merged["rel_idx_all"] = [p["rel_idx"].tolist() for p in pre]
    merged["rel_label_all"] = [p["rel_label"].tolist() for p in pre]
    return merged


def _collate_impl(processor, batch, classes_to_id, rel_classes_to_id,
                  entity_inventory, rel_prompts):
    import torch as _torch
    raw_tokens = [s["tokens"] for s in batch]
    n = len(batch)
    prompted, plens = processor.prepare_inputs(
        raw_tokens, entities=[list(entity_inventory)] * n,
        relations=[list(rel_prompts)] * n)
    # Dual view (contract v1.11): entity supervision sees the dense
    # annotation (X/Y plus extras); relation targets come exclusively
    # from sparse_relation_batch, so dense entities can never
    # manufacture relation targets.
    dense_shifted = shift_spans(
        [s["dense_entities"] for s in batch], plens)
    dense_pre = [processor.preprocess_example(
        pt, ner, classes_to_id,
        s["relations"], rel_classes_to_id)
        for pt, ner, s in zip(prompted, dense_shifted, batch)]
    merged = processor.create_batch_dict(
        dense_pre, [dict(classes_to_id)] * n,
        [{v: k for k, v in classes_to_id.items()}] * n,
        [dict(rel_classes_to_id)] * n,
        [{v: k for k, v in rel_classes_to_id.items()}] * n)
    # tokenize_inputs prompts internally; pass raw tokens so the prompt
    # is built exactly once (passing prompted texts would double it).
    # NOTE: do not call tokenize_and_prepare_labels here: it would
    # re-tokenize merged["tokens"] and prepend a second prompt.
    tok_out = processor.tokenize_inputs(
        raw_tokens,
        [list(entity_inventory)] * n, blank=None,
        relations=[list(rel_prompts)] * n)
    out = dict(merged)
    out.update(tok_out)
    lab_batch = {
        "tokens": prompted,
        "entities": dense_shifted,
        "classes_to_id": [dict(classes_to_id)] * n,
        "seq_length": _torch.LongTensor([len(p) for p in prompted]),
    }
    out["labels"] = processor.create_labels(lab_batch)
    rel_b = sparse_relation_batch(processor, batch, classes_to_id,
                                  rel_classes_to_id, entity_inventory,
                                  rel_prompts)
    out["adj_matrix"] = rel_b["adj_matrix"]
    out["rel_matrix"] = rel_b["rel_matrix"]
    out["text_lengths"] = _torch.LongTensor([len(p) for p in prompted])
    return out




if __name__ == "__main__":
    raise SystemExit(main())
