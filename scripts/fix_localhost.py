import os
import re

files_to_fix = [
    "scripts/profile_surreal.py",
    "src/extraction/entropy_gate.py",
    "scripts/debug_surreal_response.py",
    "scripts/debug_surrealdb.py",
    "sdb/example.py",
    "scripts/load_schema_simple.py",
    "scripts/load_schema_step_by_step.py",
    "scripts/load_schema_optimized.py",
    "src/extraction/extractor_integration.py",
    "src/maintenance/conservative_maintainer.py",
    "src/planner/executor.py",
    "src/eval/eval_harness.py",
    "test_e2e.py",
    "scripts/load_schema.py"
]

base_dir = "c:/Users/tobs/.cursor/workspace/sms"

for file_path in files_to_fix:
    full_path = os.path.join(base_dir, file_path)
    if not os.path.exists(full_path):
        continue
    print(f"Processing: {file_path}")
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = re.sub(r"localhost", "127.0.0.1", content)
    if new_content != content:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("  ✅ Fixed")
    else:
        print("  ✅ No changes needed")

print("\n✅ Done!")
