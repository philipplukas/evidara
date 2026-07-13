#!/usr/bin/env python3
"""Check that every Docker Compose profile referenced by the repo actually exists.

`scripts/dev-lean-search-stack.sh` shipped referencing a `lean-stack` profile that was
never added to `docker-compose.yml`. Compose does not fail on an unknown profile — it
silently starts only the profile-less services — so `npm run dev:cross-surface:live`
appeared to work while OpenSearch, the Document Service and the BFF never came up.

This guard fails loudly instead: every `--profile <name>` used in a compose command,
in scripts, docs, or workflows, must be defined by one of the compose files.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

import yaml

COMPOSE_FILES = ("docker-compose.yml", "docker-compose.local.yml")

SCAN_GLOBS = (
    "scripts/*.sh",
    "docs/**/*.md",
    ".github/workflows/*.yml",
    "docker-compose*.yml",
    "README.md",
    "justfile",
)

# `--profile foo` / `--profile=foo`. A leading letter keeps shell expansions such as
# `--profile "$MODE"` out of the results — those cannot be resolved statically.
_PROFILE_RE = re.compile(r"--profile[ =]([A-Za-z][A-Za-z0-9_.-]*)")

# Other CLIs take a `--profile` flag too (the Databricks CLI uses `--profile dev`).
# Only treat a reference as a Compose profile when the command it sits in mentions
# compose — either `docker compose ...` or a wrapper function named `compose`.
_COMPOSE_HINT = "compose"


@dataclass(frozen=True)
class ProfileReference:
    profile: str
    source: str
    line: int


def load_defined_profiles(compose_documents: Iterable[dict]) -> set[str]:
    """Collect every profile named by any service across the compose files."""
    profiles: set[str] = set()
    for document in compose_documents:
        services = (document or {}).get("services") or {}
        for service in services.values():
            for profile in (service or {}).get("profiles") or []:
                profiles.add(str(profile))
    return profiles


def iter_references(text: str, source: str) -> Iterator[ProfileReference]:
    """Yield compose profile references, joining backslash-continued shell lines."""
    logical: list[tuple[str, int]] = []
    start_line = 1
    buffer = ""

    for offset, raw in enumerate(text.splitlines(), start=1):
        if not buffer:
            start_line = offset
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        logical.append((buffer + stripped, start_line))
        buffer = ""
    if buffer:
        logical.append((buffer, start_line))

    for line, number in logical:
        if _COMPOSE_HINT not in line:
            continue
        for match in _PROFILE_RE.finditer(line):
            yield ProfileReference(profile=match.group(1), source=source, line=number)


def evaluate(defined: set[str], references: Iterable[ProfileReference]) -> list[str]:
    errors: list[str] = []
    for reference in references:
        if reference.profile not in defined:
            errors.append(
                f"{reference.source}:{reference.line}: compose profile "
                f"'{reference.profile}' is not defined in any of {', '.join(COMPOSE_FILES)}. "
                "Compose silently starts nothing for an unknown profile."
            )
    return errors


def collect(root: Path) -> tuple[set[str], list[ProfileReference]]:
    documents = []
    for name in COMPOSE_FILES:
        path = root / name
        if path.exists():
            documents.append(yaml.safe_load(path.read_text(encoding="utf-8")))
    defined = load_defined_profiles(documents)

    references: list[ProfileReference] = []
    for glob in SCAN_GLOBS:
        for path in sorted(root.glob(glob)):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            references.extend(iter_references(text, relative))
    return defined, references


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1], type=Path)
    args = parser.parse_args()

    defined, references = collect(args.root)
    errors = evaluate(defined, references)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        f"Compose profile check passed: {len(references)} reference(s) resolve to "
        f"{len(defined)} defined profile(s) ({', '.join(sorted(defined))})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
