from pathlib import Path
import sys

required_prefixes = [
    "Owner:",
    "Last reviewed:",
    "Last verified:",
    "Applies to:",
]

failed = False
for path in Path("docs/runbooks").glob("*.md"):
    lines = path.read_text(encoding="utf-8").splitlines()
    head = "\n".join(lines[:12])
    missing = [p for p in required_prefixes if p not in head]
    if missing:
        failed = True
        print(f"FAIL: {path} missing metadata: {', '.join(missing)}")
    else:
        print(f"OK: {path}")

sys.exit(1 if failed else 0)
