#!/usr/bin/env python3
"""Keep the `API_VERSION` single-owner rule true of the code it describes.

## What this is and is not

`API_VERSION` is a single contended scalar. On 2026-09-19 #1041 and #1042 both
moved it `0.33.0` -> `0.34.0`; both also edited
`contracts/api/platform-control.openapi.yaml` and `contracts/manifest.yaml`.
Whichever lands second conflicts, textually on three lines and semantically on
one number describing two surfaces.

#913 solved the *analogous* problem for `contracts/manifest.yaml`'s top-level
`version` by moving it to changesets. That treatment does **not** transfer here,
and the decision is not this script's to make — `scripts/contract_changesets.py`
already recorded it: `apis.platform_control.version` must equal the **generated**
spec's `info.version`, which is a committed file, so it is pinned to the app and
cannot be deferred to a release. What ships instead is a documented single-owner
lane in `docs/process/parallel-work-streams.md`.

A documented rule has one failure mode, and this repo has it on record: the
pointer goes stale. `CLAUDE.md`'s planning anchor named a closed issue for nine
days across two successions. So this check asserts that the rule still describes
reality:

- `API_VERSION` is assigned exactly once, in the file the rule names.
- `contracts/manifest.yaml` still carries `apis.platform_control.version`.
- The lane section still names both, plus the gate that ties them together.
- **Every path the section names exists.** A rule that points at a moved file is
  worse than no rule: it reads as current.
- The section does not restate the current version number. A fourth copy of a
  contended scalar is the problem, not the fix.

Exit codes: 0 the rule is present and true, 1 otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOC = REPO_ROOT / "docs" / "process" / "parallel-work-streams.md"

OPENAPI_MODULE = "platform-control/src/platform_control/openapi.py"
MANIFEST = "contracts/manifest.yaml"
GENERATED_SPEC = "contracts/api/platform-control.openapi.yaml"

SECTION_HEADING = "### The platform-control API version is a single-owner lane"

# Facts the rule must still state. Each is load-bearing: drop one and a reader
# cannot act on the rule without rediscovering it.
SECTION_REQUIREMENTS: tuple[tuple[str, str], ...] = (
    ("the constant", "API_VERSION"),
    ("the module that owns it", OPENAPI_MODULE),
    ("the generated spec it must match", GENERATED_SPEC),
    ("the manifest key", "apis.platform_control.version"),
    ("the gate that ties them together", "scripts/check_contract_manifest.py"),
    ("the one-lane rule", "At most one in-flight PR changes the platform-control API surface"),
    ("why this is not the #913 treatment", "#913"),
)

_ASSIGNMENT = re.compile(r'^API_VERSION\s*=\s*"(?P<value>\d+\.\d+\.\d+)"', re.MULTILINE)
# A path-looking token inside backticks: has a slash, no spaces.
_BACKTICKED_PATH = re.compile(r"`([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+/?)`")
# "API_VERSION = "1.2.3"" or "API_VERSION is 1.2.3" — a restatement of the value.
_VALUE_RESTATEMENT = re.compile(r"API_VERSION\s*(?:=|is|:)\s*[\"`']?\d+\.\d+\.\d+")


def extract_section(text: str, heading: str) -> str | None:
    start = text.find(heading)
    if start < 0:
        return None
    rest = text[start + len(heading) :]
    # Ends at the next heading of the same or higher level.
    end = re.search(r"^#{1,3} ", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def run(repo_root: Path, doc: Path) -> int:
    problems: list[str] = []

    module = repo_root / OPENAPI_MODULE
    if not module.exists():
        problems.append(
            f"{OPENAPI_MODULE} does not exist. The lane rule names it as the owner of "
            "API_VERSION; if the constant moved, move the rule with it."
        )
    else:
        assignments = _ASSIGNMENT.findall(module.read_text(encoding="utf-8"))
        if len(assignments) != 1:
            problems.append(
                f"{OPENAPI_MODULE}: expected exactly one `API_VERSION = \"x.y.z\"`, found "
                f"{len(assignments)}. The lane rule assumes one owner."
            )

    manifest = repo_root / MANIFEST
    if not manifest.exists():
        problems.append(f"{MANIFEST} does not exist.")
    elif "platform_control:" not in manifest.read_text(encoding="utf-8"):
        problems.append(f"{MANIFEST}: no `platform_control:` entry under `apis:`.")

    if not doc.exists():
        problems.append(f"{doc}: missing — the single-owner rule lives here.")
        return _report(problems)

    text = doc.read_text(encoding="utf-8")
    section = extract_section(text, SECTION_HEADING)
    if section is None:
        problems.append(
            f"{doc.name}: no '{SECTION_HEADING}' section. Two concurrent platform-control "
            "API PRs cannot merge; that has to be written down somewhere enforceable."
        )
        return _report(problems)

    for label, needle in SECTION_REQUIREMENTS:
        if needle not in section:
            problems.append(f"{doc.name}: the lane section no longer names {label} ({needle!r})")

    for path in sorted(set(_BACKTICKED_PATH.findall(section))):
        if not (repo_root / path).exists():
            problems.append(
                f"{doc.name}: the lane section points at `{path}`, which does not exist. "
                "A rule pointing at a moved file reads as current and is not."
            )

    restatement = _VALUE_RESTATEMENT.search(section)
    if restatement:
        problems.append(
            f"{doc.name}: the lane section restates the current version "
            f"({restatement.group(0)!r}). A fourth copy of the contended scalar is the "
            "problem, not the fix — describe the rule, not the number."
        )

    return _report(problems)


def _report(problems: list[str]) -> int:
    if problems:
        print("❌ The API_VERSION single-owner rule is missing or stale:", file=sys.stderr)
        for problem in problems:
            print(f"   {problem}", file=sys.stderr)
        return 1
    print("✅ API_VERSION single-owner lane documented, and it still describes the code.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    args = parser.parse_args(argv)
    return run(args.repo_root, args.doc)


if __name__ == "__main__":
    raise SystemExit(main())
