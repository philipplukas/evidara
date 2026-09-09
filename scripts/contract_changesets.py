#!/usr/bin/env python3
"""The contract changeset format: one file per contract change, no shared scalar.

## Why this exists

`contracts/manifest.yaml`'s top-level `version` used to be hand-edited by every
PR that touched `contracts/api/` or `contracts/events/`. That single scalar
serialised the whole repo, in two distinct ways — both measured, not assumed:

  1. **Two PRs picking DIFFERENT successors conflict textually.** `--minor` off
     2.41.0 gives 2.42.0; `--patch` gives 2.41.1. Git cannot merge those, and
     the changelog comment block above the key conflicts with them too.
  2. **Two PRs picking the SAME successor merge cleanly and then FAIL the gate.**
     This is the surprising one. Git merges identical content without complaint,
     but the old guard compared the working manifest against
     `load_manifest_version_from_git(base)` where `base` is the *tip of the base
     branch*, not the merge base. Once PR A lands 2.42.0 on main, PR B's own
     2.42.0 is no longer "changed relative to base", so the gate goes red and
     demands a re-bump of work that was already correct.

A changeset removes both. Each PR adds its own file under `contracts/changes/`
with a unique name, so two PRs never touch the same line — or the same file. The
gate asks "did this change declare itself?", a question about the branch alone,
so nothing another PR does can invalidate an answer that was already true.

The number is then computed once, at release, by
`scripts/release_contract_version.py`, from the changesets that accumulated.

## What this is NOT

It does not touch `apis.platform_control.version` / `API_VERSION`. Those must
equal the *generated* spec's `info.version` (`check_contract_manifest.py`), so
they are pinned to the app and cannot be deferred to a release. Two PRs that
both change the platform-control surface still conflict — but they conflict in
`contracts/api/platform-control.openapi.yaml`'s own `info.version` line
regardless of anything here, because both regenerate the spec. That conflict is
inherent to two edits of one API surface; the manifest's top-level version was
conflicting between PRs that had *nothing to do with each other*.

## Format

    # contracts/changes/<unique-slug>.yaml
    bump: minor          # minor | patch
    additive: true       # false when a consumer must change to keep working
    summary: >-
      What changed on the locked surface, in prose.

`summary` is required and floored at MIN_SUMMARY_CHARS. The old gate enforced
only that a *number* moved, which a reader learns nothing from; the manifest's
changelog prose was pure convention and unenforced. This is strictly more than
the guard it replaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CHANGESET_DIR = "contracts/changes/"
CHANGESET_SUFFIX = ".yaml"
VALID_BUMPS = ("minor", "patch")

# A floor, not a quality judgement: it exists to reject "wip", "fix" and "n/a",
# which are the values a required free-text field actually attracts. Anything a
# reviewer would accept as a sentence clears it with room to spare.
MIN_SUMMARY_CHARS = 20


@dataclass(frozen=True)
class Changeset:
    path: str
    bump: str
    additive: bool
    summary: str


def is_changeset_path(path: str) -> bool:
    return path.startswith(CHANGESET_DIR) and path.endswith(CHANGESET_SUFFIX)


def discover(root: Path = Path(".")) -> list[str]:
    """Every changeset currently in the tree, sorted."""
    directory = root / CHANGESET_DIR
    if not directory.is_dir():
        return []
    return sorted(str(p.relative_to(root)) for p in directory.glob(f"*{CHANGESET_SUFFIX}"))


def parse(path: Path) -> Changeset:
    """Load one changeset, raising ValueError with a fixable message."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - message passthrough
        raise ValueError(f"{path}: not valid YAML ({exc})") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{path}: must be a YAML mapping.")

    bump = data.get("bump")
    if bump not in VALID_BUMPS:
        raise ValueError(
            f"{path}: `bump` must be one of {', '.join(VALID_BUMPS)} (got {bump!r})."
        )

    additive = data.get("additive")
    if not isinstance(additive, bool):
        raise ValueError(
            f"{path}: `additive` must be a boolean — true when a consumer that "
            f"ignores the change is unaffected, false when it must change "
            f"(got {additive!r})."
        )

    summary = data.get("summary")
    if not isinstance(summary, str) or len(summary.strip()) < MIN_SUMMARY_CHARS:
        raise ValueError(
            f"{path}: `summary` must be at least {MIN_SUMMARY_CHARS} characters of "
            "prose saying WHAT changed on the locked surface. The version number "
            "alone tells a reader nothing."
        )

    return Changeset(path=str(path), bump=bump, additive=additive, summary=summary.strip())


def validate_all(root: Path = Path(".")) -> list[str]:
    """Errors for every changeset in the tree. Empty list means all are valid.

    Called unconditionally by the gate, including when no locked path changed,
    so a malformed changeset can never sit in the tree unremarked, waiting to
    break the release step.
    """
    errors: list[str] = []
    for rel in discover(root):
        try:
            parse(root / rel)
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def aggregate_bump(changesets: list[Changeset]) -> str:
    """The strongest bump across pending changesets. `minor` dominates `patch`."""
    if not changesets:
        raise ValueError("no changesets to aggregate")
    return "minor" if any(c.bump == "minor" for c in changesets) else "patch"


def next_version(current: str, part: str) -> str:
    major, minor, patch = (int(piece) for piece in current.split("."))
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unsupported part: {part}")
