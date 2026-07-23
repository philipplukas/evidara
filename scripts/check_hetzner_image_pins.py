#!/usr/bin/env python3
"""Check that every Hetzner runtime image pin agrees on one commit SHA.

`infra/hetzner/apps/kustomization.yaml` pins the six app images via the kustomize
`images:` transformer. `infra/hetzner/apps/migrate-job.yaml` is deliberately NOT in
that kustomization's `resources:` — it is applied on its own by deploy-stage4.sh,
before the apps roll — so the transformer never reaches it and its tag has to be
bumped by hand.

It drifted, exactly as the warning comment in that file predicts. The migrate Job sat
at 6e1816a7 (#574) while the apps rolled at da39660d: 143 commits apart. The result
was a production database migrated to 20260713_0020 while the running code contained
20260714_0021, so `jurisdictions` had no `level` column and every ORM read of a
jurisdiction raised UndefinedColumn. Nothing failed at deploy time — the migrate Job
completed successfully, because from its own older image there was nothing left to
apply.

That is the failure this guard exists to make impossible: a *successful* migrate run
that silently applies no forward revision. A pin bump that forgets the Job now fails
the build instead of reaching production.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
KUSTOMIZATION = Path("infra/hetzner/apps/kustomization.yaml")
MIGRATE_JOB = Path("infra/hetzner/apps/migrate-job.yaml")

PLATFORM_CONTROL_IMAGE = "ghcr.io/philipplukas/evidara-platform-control"

# `image: <repo>:<tag>` in the Job's pod spec.
_IMAGE_RE = re.compile(r"^\s*image:\s*(?P<repo>[^\s:]+):(?P<tag>\S+)\s*$", re.MULTILINE)

# A full 40-hex commit SHA. The kustomization explains why a moving tag is not
# acceptable here: `latest` moves under the cluster on every merge, and a branch
# name says nothing about what is running.
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


def main() -> int:
    errors: list[str] = []

    kustomization_path = REPO_ROOT / KUSTOMIZATION
    migrate_path = REPO_ROOT / MIGRATE_JOB

    for path in (kustomization_path, migrate_path):
        if not path.is_file():
            _fail(f"{path.relative_to(REPO_ROOT)} does not exist")
            return 1

    doc = yaml.safe_load(kustomization_path.read_text(encoding="utf-8")) or {}
    pins = doc.get("images") or []
    if not pins:
        _fail(f"{KUSTOMIZATION} declares no `images:` pins")
        return 1

    # 1. Every pinned image agrees on one tag, and that tag is a full commit SHA.
    tags: dict[str, str] = {}
    for entry in pins:
        name = entry.get("name", "<unnamed>")
        tag = entry.get("newTag")
        if not tag:
            errors.append(f"{KUSTOMIZATION}: image `{name}` has no `newTag`")
            continue
        if not _SHA_RE.match(str(tag)):
            errors.append(
                f"{KUSTOMIZATION}: image `{name}` is pinned to `{tag}`, which is not a "
                "full 40-character commit SHA"
            )
        tags[name] = str(tag)

    distinct = sorted(set(tags.values()))
    if len(distinct) > 1:
        listed = "\n".join(f"    {name}: {tag}" for name, tag in sorted(tags.items()))
        errors.append(
            f"{KUSTOMIZATION}: the six app images are pinned to "
            f"{len(distinct)} different SHAs; they must roll together:\n{listed}"
        )

    # 2. The migrate Job runs the same platform-control build as the API it migrates
    #    for. A newer Job would be acceptable in principle, but "same SHA" is the rule
    #    the file's own comment states, and an exact match is the only one that can be
    #    checked without a git graph.
    migrate_text = migrate_path.read_text(encoding="utf-8")
    migrate_images = [
        m for m in _IMAGE_RE.finditer(migrate_text) if m.group("repo") == PLATFORM_CONTROL_IMAGE
    ]
    if not migrate_images:
        errors.append(
            f"{MIGRATE_JOB}: found no `image: {PLATFORM_CONTROL_IMAGE}:<sha>` — the migrate "
            "Job must run the platform-control image, which carries alembic and the seeds"
        )
    elif distinct:
        app_sha = distinct[0] if len(distinct) == 1 else tags.get(PLATFORM_CONTROL_IMAGE, "")
        for match in migrate_images:
            job_sha = match.group("tag")
            if job_sha != app_sha:
                errors.append(
                    f"{MIGRATE_JOB} is pinned to {job_sha}, but {KUSTOMIZATION} rolls the "
                    f"apps at {app_sha}.\n"
                    "    The migrate Job is not covered by the `images:` transformer, so it "
                    "must be bumped by hand in the same change.\n"
                    "    Left drifted, the Job completes successfully having applied nothing, "
                    "and the API rolls against a database missing its migrations."
                )

    if errors:
        for error in errors:
            _fail(error)
        return 1

    print(f"OK: hetzner app images and the migrate Job all pinned to {distinct[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
