#!/usr/bin/env python3
"""Compute `contracts/manifest.yaml`'s top-level version from pending changesets.

This is the ONLY writer of that key. Nothing else may edit it — the moment a
second path exists, the per-PR hand-edit comes back and with it the conflict
#913 is about.

    python3 scripts/release_contract_version.py --check    # what is pending
    python3 scripts/release_contract_version.py            # cut the version

Cutting the version bumps the top-level `version`, prepends a changelog comment
built from the changeset summaries, and deletes the consumed changeset files.
Commit the result; that commit changes no locked path, so the changeset gate
correctly skips it.

Exits non-zero when there is nothing pending, so a caller cannot mistake a no-op
for a release.

`apis.platform_control.version` is deliberately untouched here: it must equal the
generated spec's `info.version`, so it moves with the app in the PR that changes
the surface, not at release. See `scripts/contract_changesets.py`.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_changesets as cs  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "contracts" / "manifest.yaml"

# Anchored at column 0 so it cannot match the indented `apis.<name>.version`.
_TOP_LEVEL_VERSION = re.compile(r'^version:\s*"(?P<value>\d+\.\d+\.\d+)"', re.MULTILINE)


def render_changelog(version: str, changesets: list[cs.Changeset]) -> str:
    """The comment block the manifest carries above `version:`, one per entry."""
    lines: list[str] = []
    for record in changesets:
        note = " ".join(record.summary.split())
        marker = "Additive" if record.additive else "NOT ADDITIVE — consumers must change"
        lines.append(f"# {version}: {note} [{marker}]")
    return "\n".join(lines) + "\n"


def release(root: Path, manifest: Path) -> int:
    errors = cs.validate_all(root)
    if errors:
        for error in errors:
            print(f"❌ Invalid contract changeset: {error}", file=sys.stderr)
        return 2

    pending_paths = cs.discover(root)
    if not pending_paths:
        print(
            "❌ No pending changesets under contracts/changes/ — nothing to release.",
            file=sys.stderr,
        )
        return 1

    changesets = [cs.parse(root / p) for p in pending_paths]
    text = manifest.read_text(encoding="utf-8")
    match = _TOP_LEVEL_VERSION.search(text)
    if match is None:
        print("❌ contracts/manifest.yaml has no top-level `version`.", file=sys.stderr)
        return 2

    current = match.group("value")
    part = cs.aggregate_bump(changesets)
    new_version = cs.next_version(current, part)

    changelog = render_changelog(new_version, changesets)
    line_start = text.rfind("\n", 0, match.start()) + 1
    text = text[:line_start] + changelog + text[line_start:]

    match = _TOP_LEVEL_VERSION.search(text)
    assert match is not None
    text = text[: match.start("value")] + new_version + text[match.end("value") :]
    manifest.write_text(text, encoding="utf-8")

    for rel in pending_paths:
        (root / rel).unlink()

    print(f"contracts/manifest.yaml  version: {current} -> {new_version} ({part})")
    for record in changesets:
        print(f"  consumed {record.path}")
    print()
    print("Commit the manifest and the changeset deletions together.")
    return 0


def check(root: Path) -> int:
    errors = cs.validate_all(root)
    for error in errors:
        print(f"❌ Invalid contract changeset: {error}", file=sys.stderr)

    pending_paths = cs.discover(root)
    if not pending_paths:
        print("No pending contract changesets; the manifest version is current.")
        return 2 if errors else 0

    if errors:
        return 2

    changesets = [cs.parse(root / p) for p in pending_paths]
    text = (root / "contracts" / "manifest.yaml").read_text(encoding="utf-8")
    match = _TOP_LEVEL_VERSION.search(text)
    current = match.group("value") if match else "?"
    part = cs.aggregate_bump(changesets)
    print(f"{len(changesets)} pending changeset(s); next version would be "
          f"{cs.next_version(current, part)} ({part}):")
    for record in changesets:
        print(f" - {record.path} ({record.bump}) {record.summary.splitlines()[0]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report what is pending without writing anything",
    )
    args = parser.parse_args()
    if args.check:
        return check(REPO_ROOT)
    return release(REPO_ROOT, MANIFEST)


if __name__ == "__main__":
    raise SystemExit(main())
