#!/usr/bin/env python3
"""Fail if a platform-owned file under infra/ has been edited here.

WHY THIS EXISTS. On 2026-09-07 the shared cluster layer moved to
philipplukas/research-platform, and an Argo CD Application now reconciles it.
The copies under infra/hetzner/ were deliberately NOT deleted: they are the
fallback while the controller earns trust, and deleting them the same day it was
switched on would have spent evidence nobody had collected yet.

A fallback that people keep editing is not a fallback -- it is a second owner.
That is exactly the state this repository and from-sign-to-signal were in for
months: one cluster, two half-owners, each seeing the other's definitions as
duplicates of its own. Editing one of these files today changes nothing in the
cluster (Argo reconciles from the other repo) and silently forks the estate
again, which is the worst of both.

So: frozen. The fix for a real change is to make it in research-platform.

    python3 scripts/check_platform_ownership.py          # check
    python3 scripts/check_platform_ownership.py --list   # what is frozen, and why

Deleting these files is the LAST step of the cutover, not this one. When the
watchdog in research-platform reports ~14 clean days
(scripts/platform-watch.sh --report), remove the files and this guard together.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

MANIFEST = pathlib.Path("infra/PLATFORM-OWNED.txt")
UPSTREAM = "https://github.com/philipplukas/research-platform"


def load() -> list[tuple[str, str]]:
    if not MANIFEST.exists():
        sys.exit(f"missing {MANIFEST} — run from the repository root")
    rows = []
    for line in MANIFEST.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, path = line.split(maxsplit=1)
        rows.append((digest, path))
    return rows


def main() -> int:
    rows = load()

    if "--list" in sys.argv:
        print(f"{len(rows)} platform-owned files, reconciled from {UPSTREAM}:")
        for _, path in rows:
            print(f"  {path}")
        return 0

    changed, missing = [], []
    for digest, path in rows:
        p = pathlib.Path(path)
        if not p.exists():
            missing.append(path)
        elif hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            changed.append(path)

    if not changed and not missing:
        return 0

    print("Platform-owned files must not be edited in this repository.\n")
    for path in changed:
        print(f"  edited:  {path}")
    for path in missing:
        print(f"  removed: {path}")
    print(
        f"\nThese are reconciled from {UPSTREAM} by the Argo CD `platform`"
        "\nApplication. A change made here does not reach the cluster, and leaves the"
        "\ntwo copies disagreeing — the condition the extraction existed to end."
        "\n\nMake the change there instead. If you are running the final cutover, delete"
        "\nthe files, this guard and its pre-commit hook in one commit, rather than"
        "\nediting the manifest to match."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
