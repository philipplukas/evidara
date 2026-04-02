from pathlib import Path
import re
import sys

link_pattern = re.compile(r"\[.*?\]\((?!http)(.*?)\)")

failed = False
for path in Path("docs").rglob("*.md"):
    # Skip template files — they contain intentional placeholder links
    if "templates" in path.parts:
        continue
    text = path.read_text(encoding="utf-8")
    for match in link_pattern.findall(text):
        if match.startswith("#") or match.startswith("mailto:"):
            continue
        target = (path.parent / match).resolve()
        if not target.exists():
            failed = True
            print(f"FAIL: {path} -> missing link target: {match}")

sys.exit(1 if failed else 0)
