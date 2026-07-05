"""
Interactive CLI for labeling queries.

Usage:
  # Label from stdin
  cat queries.txt | python scripts/label_queries.py -o data/manual_labels.jsonl

  # Label synthetic data (review generated queries)
  python scripts/label_queries.py -i data/training_queries.jsonl -o data/reviewed_labels.jsonl

Keys:
  [t] temporal  [f] factual  [m] multi-hop  [c] conversational  [u] update
  [s] skip      [q] quit (saves progress)
"""

import argparse
import json
import sys
import os


TYPE_KEYS = {
    "t": "temporal",
    "f": "factual",
    "m": "multi-hop",
    "c": "conversational",
    "u": "update",
}


def read_queries_from_stdin() -> list[dict]:
    lines = [l.strip() for l in sys.stdin if l.strip()]
    return [{"text": l, "type": None, "source": "manual"} for l in lines]


def read_jsonl(path: str) -> list[dict]:
    examples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def write_jsonl(path: str, examples: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")


def label(examples: list[dict]) -> list[dict]:
    labeled = 0
    skipped = 0

    try:
        for i, ex in enumerate(examples):
            if ex.get("type"):
                continue

            text = ex["text"]
            orig_type = ex.get("type_orig", "?")

            while True:
                prompt = (
                    f"\n[{i+1}/{len(examples)}] "
                    f"(orig: {orig_type}) "
                    f"{text}\n"
                    f"  [t]emporal  [f]actual  [m]ulti-hop  "
                    f"[c]onversational  [u]pdate  [s]kip  [q]uit: "
                )
                try:
                    key = input(prompt).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n  Quitting.")
                    return examples

                if key == "q":
                    return examples

                if key == "s":
                    ex["type"] = "skip"
                    skipped += 1
                    print(f"  → SKIPPED")
                    break

                if key in TYPE_KEYS:
                    ex["type"] = TYPE_KEYS[key]
                    labeled += 1
                    print(f"  → {TYPE_KEYS[key]}")
                    break

                print(f"  Unknown key: '{key}'")

    finally:
        # Save progress on any exit
        remaining = sum(1 for ex in examples if not ex.get("type"))
        print(f"\nLabeled: {labeled} | Skipped: {skipped} | Remaining: {remaining}")

    return examples


def main():
    parser = argparse.ArgumentParser(description="Label queries interactively")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-i", "--input", help="Input JSONL file")
    group.add_argument(
        "-s", "--stdin", action="store_true", help="Read from stdin (default)"
    )
    parser.add_argument(
        "-o", "--output", default="data/manual_labels.jsonl", help="Output JSONL file"
    )
    args = parser.parse_args()

    if args.input:
        examples = read_jsonl(args.input)
    else:
        examples = read_queries_from_stdin()

    if not examples:
        print("No input data found.")
        sys.exit(1)

    print(f"Loaded {len(examples)} queries for labeling.")

    out_path = args.output
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    labeled = label(examples)
    write_jsonl(out_path, labeled)
    print(f"Saved {sum(1 for ex in labeled if ex.get('type'))} labeled examples to {out_path}")


if __name__ == "__main__":
    main()
