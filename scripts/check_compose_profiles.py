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

# `-f docker-compose.yml` / `--file=docker-compose.local.yml`, so the dependency
# pass knows which files a given command actually composes.
_FILE_RE = re.compile(r"(?:-f|--file)[ =]\S*?(docker-compose[A-Za-z0-9_.-]*\.yml)")


@dataclass(frozen=True)
class ProfileReference:
    profile: str
    source: str
    line: int
    # Compose files named with `-f` on the same command line. Empty when the
    # command resolves them elsewhere (a `compose()` shell wrapper, an env var),
    # in which case the dependency pass cannot know the file set and skips.
    files: tuple[str, ...] = ()


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
        files = tuple(dict.fromkeys(_FILE_RE.findall(line)))
        for match in _PROFILE_RE.finditer(line):
            yield ProfileReference(
                profile=match.group(1), source=source, line=number, files=files
            )


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


def merge_services(compose_documents: Iterable[dict]) -> dict[str, dict]:
    """Merge service definitions across the compose files, later files winning.

    Mirrors how the overlay is applied at runtime: `document-service` is declared
    in both files with different profiles, and the overlay's list replaces the
    base's rather than extending it.
    """
    merged: dict[str, dict] = {}
    for document in compose_documents:
        for name, service in ((document or {}).get("services") or {}).items():
            merged.setdefault(name, {}).update(service or {})
    return merged


def _depends_on(service: dict) -> list[str]:
    """Dependency target names, for both the list and mapping forms."""
    declared = service.get("depends_on")
    if isinstance(declared, dict):
        return [str(name) for name in declared]
    if isinstance(declared, list):
        return [str(name) for name in declared]
    return []


def selected_services(services: dict[str, dict], profiles: set[str]) -> set[str]:
    """Services compose would start for ``profiles``.

    A service with no `profiles` key is always started; one with profiles is
    started only when at least one of them is selected.
    """
    chosen: set[str] = set()
    for name, service in services.items():
        declared = {str(p) for p in (service.get("profiles") or [])}
        if not declared or (declared & profiles):
            chosen.add(name)
    return chosen


def evaluate_dependencies(
    documents_by_file: dict[str, dict],
    references: Iterable[ProfileReference],
) -> list[str]:
    """Every documented profile combination must resolve to a valid project.

    The `--profile` guard above only catches an *undefined* profile. It cannot
    catch a **missing** one, which is the failure that actually shipped: the
    compose-e2e harness documented `--profile apps --profile nats --profile
    minio`, all three defined, while `legal-search-api` (profile `apps`) depends
    on `opensearch` (profiles `search`/`full`/`lean-stack`). Compose rejects the
    whole project —

        service "legal-search-api" depends on undefined service "opensearch":
        invalid compose project

    — so the command in the file's own header could never have worked, and the
    profile check passed the whole time because every named profile existed.
    """
    grouped: dict[tuple[str, int, tuple[str, ...]], set[str]] = {}
    for reference in references:
        # Skip commands whose file set is not stated inline. `dev-lean-search-stack.sh`
        # composes ONLY docker-compose.yml through a shell wrapper, where
        # `document-service` still carries `lean-stack`; assuming the overlay is
        # always applied would report it as broken when it is fine. A guard that
        # fires falsely is worse than no guard.
        if not reference.files:
            continue
        key = (reference.source, reference.line, reference.files)
        grouped.setdefault(key, set()).add(reference.profile)

    errors: list[str] = []
    for (source, line, files), profiles in sorted(grouped.items()):
        services = merge_services(
            documents_by_file[name] for name in files if name in documents_by_file
        )
        if not services:
            continue
        chosen = selected_services(services, profiles)
        for name in sorted(chosen):
            for target in _depends_on(services.get(name) or {}):
                if target in chosen:
                    continue
                needed = sorted({str(p) for p in (services.get(target, {}).get("profiles") or [])})
                hint = (
                    f" Add one of --profile {', --profile '.join(needed)}."
                    if needed
                    else " That service is not defined at all."
                )
                errors.append(
                    f"{source}:{line}: --profile {' --profile '.join(sorted(profiles))} "
                    f"selects '{name}', which depends on '{target}' — not selected."
                    f"{hint} Compose refuses the whole project as invalid."
                )
    return errors


def collect(root: Path) -> tuple[set[str], dict[str, dict], list[ProfileReference]]:
    documents = []
    documents_by_file: dict[str, dict] = {}
    for name in COMPOSE_FILES:
        path = root / name
        if path.exists():
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            documents.append(document)
            documents_by_file[name] = document
    defined = load_defined_profiles(documents)

    references: list[ProfileReference] = []
    for glob in SCAN_GLOBS:
        for path in sorted(root.glob(glob)):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            references.extend(iter_references(text, relative))
    return defined, documents_by_file, references


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1], type=Path)
    args = parser.parse_args()

    defined, documents_by_file, references = collect(args.root)
    errors = evaluate(defined, references)
    # Only run the dependency pass once every named profile is known to exist;
    # otherwise an undefined profile reports twice as two different problems.
    if not errors:
        errors = evaluate_dependencies(documents_by_file, references)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        f"Compose profile check passed: {len(references)} reference(s) resolve to "
        f"{len(defined)} defined profile(s) ({', '.join(sorted(defined))}), "
        f"and every inline-file combination resolves its depends_on."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
