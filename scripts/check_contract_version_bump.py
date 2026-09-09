#!/usr/bin/env python3
"""Require a contract CHANGESET when locked contract files change.

Until 2026-09-09 this gate required the PR to hand-edit `contracts/manifest.yaml`'s
top-level `version`. That made every contract PR contend for one scalar, and
#913 named it as a blocker to running lanes in parallel. Two failure modes, both
reproduced before this was rewritten:

  - different successors (`--minor` vs `--patch`) conflict textually;
  - the SAME successor merges cleanly and then fails this gate, because the
    comparison was against the *tip of the base branch* rather than the merge
    base — so once PR A landed 2.42.0, PR B's identical and already-correct
    2.42.0 read as "did not change".

The rule is now: a locked-path change must ship a changeset under
`contracts/changes/`. Each PR writes its own file, so no two PRs touch the same
line, and the question this gate asks is answerable from the branch alone —
nothing another PR merges can invalidate an answer that was already true.
`scripts/release_contract_version.py` turns the accumulated changesets into the
manifest version, once, at release.

The protection is not weaker. The old gate accepted any changed digit and never
looked at the prose; a changeset must declare `bump`, `additive`, and a
non-placeholder `summary`, and every changeset in the tree is validated on every
run of this gate — including runs where no locked path changed, so a malformed
one cannot sit there unremarked.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_changesets as cs  # noqa: E402


LOCKED_PREFIXES = ("contracts/api/", "contracts/events/")
MANIFEST_PATH = "contracts/manifest.yaml"
# Uncommitted edits here are as invisible to a commit-range guard as edits to a
# locked path, and just as misleading — a developer who wrote the changeset but
# did not commit it would otherwise be told to write one.
WATCHED_PREFIXES = LOCKED_PREFIXES + (cs.CHANGESET_DIR,)


def run(args: list[str]) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "command failed")
    return proc.stdout


def changed_files_between(base: str, head: str) -> list[str]:
    """Return changed files between refs with resilient merge-base fallback."""
    try:
        changed_raw = run(["git", "diff", "--name-only", f"{base}...{head}"])
    except RuntimeError as exc:
        message = str(exc)
        if "no merge base" not in message.lower():
            raise
        print(
            "Warning: git diff with triple-dot failed due to missing merge base; "
            "falling back to two-dot range comparison."
        )
        changed_raw = run(["git", "diff", "--name-only", f"{base}..{head}"])
    return [line.strip() for line in changed_raw.splitlines() if line.strip()]


def uncommitted_locked_paths() -> list[str]:
    """Watched contract paths modified in the working tree but not yet committed.

    This guard compares COMMITS (`base...head`), which is correct in CI — the
    checkout is clean, so the commit range is the whole change. Locally it is a
    trap: a developer who has edited `contracts/api/*` but not committed gets
    "No locked contract files changed; changeset guard skipped", which reads as
    a pass over work the guard never looked at. That is exactly the class of
    silent abstention this repo keeps getting bitten by, and it bit here: the
    first local run of this gate on a real contract change reported "skipped".
    """
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        # Porcelain v1: 2 status chars, a space, then the path. Renames carry
        # "old -> new"; the destination is what matters here.
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip('"')
        if path.startswith(WATCHED_PREFIXES):
            paths.append(path)
    return sorted(set(paths))


def declared_changesets(changed_files: list[str]) -> list[str]:
    """Changesets added or modified in the range that still exist in the tree.

    A range that only *deletes* changesets is the release step, not a
    declaration, so existence on disk is required rather than mere presence in
    the diff.
    """
    return sorted(
        path
        for path in changed_files
        if cs.is_changeset_path(path) and Path(path).is_file()
    )


def evaluate(base: str, head: str) -> int:
    changed_files = changed_files_between(base, head)
    locked_changed = [p for p in changed_files if p.startswith(LOCKED_PREFIXES)]

    # Validated unconditionally — including when no locked path changed. A
    # gate that only inspects changesets on the PRs that add them lets a
    # malformed one survive in the tree until the release step trips over it.
    exit_code = 0
    for error in cs.validate_all():
        print(f"❌ Invalid contract changeset: {error}", file=sys.stderr)
        exit_code = 2

    # Reported whatever the committed verdict is, so a local run can never
    # present a clean result over edits it did not examine.
    pending = [p for p in uncommitted_locked_paths() if p not in changed_files]
    if pending:
        print(
            "⚠️  NOT EVALUATED: uncommitted changes to watched contract paths.\n"
            "    This guard compares commits, so these are invisible to it:",
            file=sys.stderr,
        )
        for path in pending:
            print(f"      - {path}", file=sys.stderr)
        print(
            "    Commit them and re-run; the result below covers committed work only.",
            file=sys.stderr,
        )

    if not locked_changed:
        if pending:
            print(
                "DID-NOT-RUN: no locked contract files changed in the commit range, "
                "but uncommitted ones exist (listed above)."
            )
        else:
            print("No locked contract files changed; changeset guard skipped.")
        return exit_code

    print("Locked contract files changed:")
    for path in locked_changed:
        print(f" - {path}")

    declared = declared_changesets(changed_files)
    if not declared:
        print(
            "❌ Locked contract files changed but no changeset was added under\n"
            f"   {cs.CHANGESET_DIR}.\n"
            "   Fix:  python3 scripts/bump_contract_version.py --minor \\\n"
            '           --summary \"what changed on the locked surface\"\n'
            "   Add --api when the platform-control OpenAPI surface changed; that also\n"
            "   moves API_VERSION and apis.platform_control.version, which a SECOND gate\n"
            "   (check_contract_manifest.py) asserts equal to the generated spec.\n"
            f"   Do NOT hand-edit {MANIFEST_PATH}'s top-level version — it is computed\n"
            "   at release by scripts/release_contract_version.py, which is what keeps\n"
            "   two concurrent contract PRs from conflicting (#913).",
            file=sys.stderr,
        )
        return 2

    print("Contract changeset(s) declared:")
    for path in declared:
        record = cs.parse(Path(path))
        additive = "additive" if record.additive else "NOT additive"
        print(f" - {path} ({record.bump}, {additive})")
    print("✅ Locked contract change is declared; version is computed at release.")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Require a contracts/changes/ changeset on locked contract changes."
    )
    parser.add_argument("--base", required=True, help="Base git ref/sha")
    parser.add_argument("--head", default="HEAD", help="Head git ref/sha (default: HEAD)")
    args = parser.parse_args()
    return evaluate(args.base, args.head)


if __name__ == "__main__":
    raise SystemExit(main())
