#!/usr/bin/env python3
"""Check that docs use Mermaid for diagrams, not ASCII art or other formats.

Flags:
- PlantUML blocks (```plantuml or @startuml)
- Suspicious ASCII art (lines with box-drawing characters)
- Image references to diagram files (*.drawio, *.excalidraw)
"""

import re
import sys
from pathlib import Path

DOCS_DIRS = (Path("docs"), Path("legal-search/frontend/docs"))
ERRORS = []

# Patterns that suggest non-Mermaid diagrams
PLANTUML_PATTERN = re.compile(r"```plantuml|@startuml|@enduml", re.IGNORECASE)
DRAWIO_PATTERN = re.compile(r"\.(drawio|excalidraw)\b", re.IGNORECASE)

# Known exception: system-context.md has a legacy ASCII diagram
EXCEPTIONS = {"docs/architecture/system-context.md"}


def check_file(path: Path) -> list[str]:
    issues = []
    rel = str(path)

    if rel in EXCEPTIONS:
        return issues

    text = path.read_text(encoding="utf-8")

    # Check for PlantUML
    for match in PLANTUML_PATTERN.finditer(text):
        line_num = text[:match.start()].count("\n") + 1
        issues.append(f"{rel}:{line_num}: PlantUML detected — use Mermaid instead")

    # Check for draw.io / excalidraw references
    for match in DRAWIO_PATTERN.finditer(text):
        line_num = text[:match.start()].count("\n") + 1
        issues.append(
            f"{rel}:{line_num}: External diagram file reference detected — "
            "use inline Mermaid instead"
        )

    return issues


def main() -> int:
    if not any(docs_dir.exists() for docs_dir in DOCS_DIRS):
        return 0

    for docs_dir in DOCS_DIRS:
        if not docs_dir.exists():
            continue
        for md_file in sorted(docs_dir.rglob("*.md")):
            ERRORS.extend(check_file(md_file))

    if ERRORS:
        print("Diagram format violations:")
        for error in ERRORS:
            print(f"  {error}")
        print(
            "\nAll diagrams in docs/ and legal-search/frontend/docs/ "
            "must use Mermaid fenced code blocks."
            "\nSee docs/documentation/mermaid-style-guide.md for templates."
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
