from pathlib import Path
import sys

required_headings = [
    "## Purpose",
    "## Current state",
    "## Source of truth",
    "## Minimal next tasks",
    "## Later expansion",
    "## Dependencies",
    "## Testing",
    "## Drift risks",
]

# Only check top-level component docs, not subdirectories or planning docs
component_files = [
    f for f in Path("docs/components").glob("*.md")
    if f.name not in ("first-vertical-slice.md",)
]

if not component_files:
    print("No component docs found.")
    sys.exit(0)

failed = False
for path in component_files:
    text = path.read_text(encoding="utf-8")
    missing = [h for h in required_headings if h not in text]
    if missing:
        failed = True
        print(f"FAIL: {path} missing headings: {', '.join(missing)}")
    else:
        print(f"OK: {path}")

sys.exit(1 if failed else 0)
