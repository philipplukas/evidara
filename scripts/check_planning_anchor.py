#!/usr/bin/env python3
"""Fail the build when `CLAUDE.md`'s planning anchor names a closed issue.

## Why this exists

`CLAUDE.md` opens with a **Current anchor** pointer: the one issue new work is
scoped against. It named **#628** for three days after #628 closed, then **#731**
for six days after *that* closed. Every agent briefed from the file in those nine
days was scoped against finished work.

`CLAUDE.md` already documents the failure, in its own words:

    **This pointer has gone stale twice** — it named #628 for three days after it
    closed, then #731 for six days after that.

A file that describes its own recurring defect and keeps having it is the proof
that documenting a pointer does not maintain it. So the pointer is checked.

## What it does

1. Parses the anchor issue number out of `CLAUDE.md` (the `**Current anchor: #N`
   line). Exactly one such line must exist — zero means the pointer was deleted,
   two means nobody can say which one is current.
2. Resolves that issue's state, preferring `gh` and falling back to the REST API
   with whatever token the environment already has (`GH_TOKEN` / `GITHUB_TOKEN`,
   which GitHub Actions sets for the repo itself).
3. `CLOSED` fails the build. `OPEN` passes.

## PASS, FAIL and DID-NOT-RUN are three outcomes

A gate whose prerequisites were absent did not pass (AGENTS.md, "A gate is
evidence only for the stages that actually ran"). With no `gh`, no token and no
network, this check cannot know anything about the anchor, so it prints
`DID-NOT-RUN` and names what was missing rather than printing a green line it has
not earned. `--require-network` turns that into a failure for callers that know
the network is supposed to be there.

Exit codes:
    0  PASS, or DID-NOT-RUN without --require-network
    1  FAIL — the anchor names a CLOSED issue
    2  the pointer itself is malformed (missing, duplicated, unparseable)
    3  DID-NOT-RUN with --require-network

Stdlib only: this runs in the docs-lint job, which installs no GitHub tooling
beyond what the runner image already carries.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANCHOR_FILE = REPO_ROOT / "CLAUDE.md"
DEFAULT_REPO = "philipplukas/evidara"

# The pointer, as CLAUDE.md writes it:
#   **Current anchor: #958 — the corpus states what is true, or refuses.**
ANCHOR_PATTERN = re.compile(r"^\*\*Current anchor:\s*#(?P<number>\d+)\b", re.MULTILINE)


class MalformedAnchor(Exception):
    """The pointer in CLAUDE.md cannot be read as exactly one issue number."""


@dataclass(frozen=True)
class Outcome:
    status: str  # "PASS" | "FAIL" | "DID-NOT-RUN"
    message: str

    @property
    def exit_code(self) -> int:
        return {"PASS": 0, "FAIL": 1, "DID-NOT-RUN": 0}[self.status]


def find_anchor(text: str) -> int:
    """The single issue number the anchor pointer names.

    Raises `MalformedAnchor` when there is not exactly one. Both directions are
    real failures: a deleted pointer leaves agents with no anchor at all, and two
    pointers leave them choosing.
    """
    matches = ANCHOR_PATTERN.findall(text)
    if not matches:
        raise MalformedAnchor(
            "no `**Current anchor: #N` line found. The planning anchor is the one "
            "pointer new work is scoped against; it may not be deleted silently."
        )
    if len(matches) > 1:
        raise MalformedAnchor(
            f"found {len(matches)} `**Current anchor:` lines (#{', #'.join(matches)}). "
            "Exactly one issue can be current."
        )
    return int(matches[0])


def _state_via_gh(number: int, repo: str) -> str | None:
    """Issue state via the `gh` CLI, or None when `gh` cannot answer."""
    if shutil.which("gh") is None:
        return None
    try:
        completed = subprocess.run(
            ["gh", "issue", "view", str(number), "--repo", repo, "--json", "state"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        return str(json.loads(completed.stdout)["state"]).upper()
    except (ValueError, KeyError, TypeError):
        return None


def _state_via_rest(number: int, repo: str) -> str | None:
    """Issue state via the REST API, or None when the request cannot be made."""
    url = f"https://api.github.com/repos/{repo}/issues/{number}"
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    state = payload.get("state")
    return str(state).upper() if state else None


def resolve_state(number: int, repo: str) -> str | None:
    """`OPEN` / `CLOSED`, or None when no transport could answer."""
    return _state_via_gh(number, repo) or _state_via_rest(number, repo)


def evaluate(number: int, state: str | None, repo: str) -> Outcome:
    """Turn a resolved (or unresolved) state into one of the three outcomes."""
    if state is None:
        return Outcome(
            "DID-NOT-RUN",
            f"could not resolve the state of {repo}#{number}. Neither `gh` nor the "
            "REST API answered — no CLI, no token (GH_TOKEN / GITHUB_TOKEN), or no "
            "network. The anchor was NOT checked.",
        )
    if state == "CLOSED":
        return Outcome(
            "FAIL",
            f"CLAUDE.md's planning anchor names {repo}#{number}, which is CLOSED.\n"
            "   Work scoped against a closed anchor is work against a finished plan — "
            "this pointer has already gone stale twice (#628 for three days, #731 for "
            "six).\n"
            "   Read the closed issue's final comments, then point `**Current anchor:` "
            "at its successor.",
        )
    return Outcome("PASS", f"planning anchor {repo}#{number} is {state}.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--anchor-file",
        type=Path,
        default=DEFAULT_ANCHOR_FILE,
        help="file carrying the `**Current anchor: #N` pointer (default: CLAUDE.md)",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("EVIDARA_ANCHOR_REPO", DEFAULT_REPO),
        help="owner/name of the repository holding the anchor issue",
    )
    parser.add_argument(
        "--require-network",
        action="store_true",
        help="treat DID-NOT-RUN as a failure (exit 3) instead of an honest abstention",
    )
    args = parser.parse_args(argv)

    try:
        text = args.anchor_file.read_text(encoding="utf-8")
    except OSError as error:
        print(f"❌ cannot read {args.anchor_file}: {error}", file=sys.stderr)
        return 2

    try:
        number = find_anchor(text)
    except MalformedAnchor as error:
        print(f"❌ {args.anchor_file.name}: {error}", file=sys.stderr)
        return 2

    outcome = evaluate(number, resolve_state(number, args.repo), args.repo)

    if outcome.status == "PASS":
        print(f"✅ PASS: {outcome.message}")
        return 0
    if outcome.status == "FAIL":
        print(f"❌ FAIL: {outcome.message}", file=sys.stderr)
        return 1

    print(f"⚠️  DID-NOT-RUN: {outcome.message}", file=sys.stderr)
    return 3 if args.require_network else 0


if __name__ == "__main__":
    raise SystemExit(main())
