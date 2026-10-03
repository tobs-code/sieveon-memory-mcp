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
CONTRACT = json.loads((ROOT / "docs" / "eval_relex_training_contract_v1_1.json").read_text())

LABELS = tuple(CONTRACT["labels"])
FORBIDDEN = tuple(CONTRACT["forbidden_model_features"])
ENTITY_INVENTORY = list(CONTRACT["entity_inventory"])


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
    lo = next(i for i, (_, ws, we) in enumerate(words) if ws <= start < we)
    hi = next(i for i, (_, ws, we) in enumerate(words) if ws < end <= we)
    return lo, hi + 1


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
    relations: list[tuple[int, int, str]] = []
    if ex["relation"] == "provides":
        head = order.index("X")
        tail = order.index("Y")
        relations = [(head, tail, "provides")]
    return {"tokens": tokens, "ner": ner, "relations": relations}


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

    class _DS(Dataset):
        def __len__(self):
            return len(samples)

        def __getitem__(self, i):
            return samples[i]

    def collate(batch):
        raw_tokens = [s["tokens"] for s in batch]
        n = len(batch)
        prompted, plens = processor.prepare_inputs(
            raw_tokens, entities=[list(ENTITY_INVENTORY)] * n,
            relations=[["provides"]] * n)
        shifted = []
        for s, pl in zip(batch, plens):
            shifted.append(
                [(a + pl, b + pl, lab) for (a, b, lab) in s["entities"]])
        pre = [processor.preprocess_example(
            pt, ner, classes_to_id,
            s["relations"], rel_classes_to_id)
            for pt, ner, s in zip(prompted, shifted, batch)]
        merged = processor.create_batch_dict(
            pre, [dict(classes_to_id)] * n,
            [{v: k for k, v in classes_to_id.items()}] * n,
            [dict(rel_classes_to_id)] * n,
            [{v: k for k, v in rel_classes_to_id.items()}] * n)
        merged["rel_class_to_ids"] = [dict(rel_classes_to_id)] * n
        # tokenize_inputs prompts internally; pass raw tokens so the prompt
        # is built exactly once (passing prompted texts would double it).
        # NOTE: do not call tokenize_and_prepare_labels here: it would
        # re-tokenize merged["tokens"] and prepend a second prompt.
        import torch as _torch
        tok_out = processor.tokenize_inputs(
            raw_tokens,
            [list(ENTITY_INVENTORY)] * n, blank=None,
            relations=[["provides"]] * n)
        out = dict(merged)
        out.update(tok_out)
        lab_batch = {
            "tokens": prompted,
            "entities": shifted,
            "classes_to_id": [dict(classes_to_id)] * n,
            "seq_length": _torch.LongTensor([len(p) for p in prompted]),
        }
        out["labels"] = processor.create_labels(lab_batch)
        adj, rel = processor.create_relation_labels(merged)
        out["adj_matrix"] = adj
        out["rel_matrix"] = rel
        out["text_lengths"] = _torch.LongTensor([len(p) for p in prompted])
        return out

    use_cpu = not torch.cuda.is_available()
    targs = TrainingArguments(
        output_dir=args.out, seed=seed, do_train=True,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
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
    }
    (out / "training_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  trained: checkpoint {out} digest {ckpt_digest[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
