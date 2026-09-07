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

# Every other Evidara image reference under infra/hetzner/.
#
# This used to describe the marketing Deployment (ADR-0039) as deliberately outside
# apps/kustomization.yaml, "so the public surface is not coupled to a platform rollout
# it has no part in", and therefore exempt from agreeing with the app SHA. #884 undid
# that: marketing is now a base under `resources:` with an `images:` entry, so it rolls
# in lockstep like everything else.
#
# The exemption is what made #884 invisible here. This gate's rule was "pinned to a
# commit", and marketing was pinned to 32a13330 — which IS a commit, just a pre-squash
# branch one that is not reachable from `main`. A gate cannot tell those apart from the
# tag alone, so the fix is structural rather than a smarter tag check: every Evidara
# image under infra/hetzner must be transformer-managed (untagged, with a matching
# `images:` entry), and migrate-job.yaml is the single, named exception.
HETZNER_DIR = Path("infra/hetzner")
EVIDARA_IMAGE_PREFIX = "ghcr.io/philipplukas/evidara-"

# Helm values files are out of scope: they configure third-party charts and reach the
# cluster through `helm upgrade`, not `kubectl apply`, so this guard could not tell a
# drifted one from a current one anyway.
#
# `runners/values-heavy.yaml` is a REAL instance of the hazard below — the ARC heavy
# pool runs `evidara-runner-heavy:latest` — and it is excluded knowingly, not by
# oversight: that pool is CI capacity with no user-facing state, its own file already
# carries a longer warning about Helm-revision drift (#534), and repinning it is a
# change to how CI is provisioned rather than to how the product is served. If it is
# ever brought under a pin, delete this exclusion in the same change.
EXCLUDED_DIRS = ("runners", "values")

PLATFORM_CONTROL_IMAGE = "ghcr.io/philipplukas/evidara-platform-control"

# `image: <repo>:<tag>` in the Job's pod spec.
_IMAGE_RE = re.compile(r"^\s*image:\s*(?P<repo>[^\s:]+):(?P<tag>\S+)\s*$", re.MULTILINE)

# `image: <repo>` with no tag at all — the transformer-managed form every workload
# except the migrate Job uses.
_UNTAGGED_IMAGE_RE = re.compile(r"^\s*image:\s*(?P<repo>[^\s:]+)\s*$", re.MULTILINE)

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

    # 3. No Evidara image anywhere under infra/hetzner/ is pinned to a moving tag.
    #    `latest` here is not a smaller version of the same mistake as a drifted SHA —
    #    it is a worse one: the drift happens on someone else's merge, at a time nobody
    #    chose, and `kubectl describe` still reports the tag it was applied with.
    covered = {kustomization_path.resolve(), migrate_path.resolve()}
    for path in sorted((REPO_ROOT / HETZNER_DIR).rglob("*.yaml")):
        if path.resolve() in covered:
            continue
        if path.relative_to(REPO_ROOT / HETZNER_DIR).parts[0] in EXCLUDED_DIRS:
            continue
        for match in _IMAGE_RE.finditer(path.read_text(encoding="utf-8")):
            repo, tag = match.group("repo"), match.group("tag")
            if not repo.startswith(EVIDARA_IMAGE_PREFIX):
                continue
            if not _SHA_RE.match(tag):
                errors.append(
                    f"{path.relative_to(REPO_ROOT)}: `{repo}` is pinned to `{tag}`, which is "
                    "not a full 40-character commit SHA.\n"
                    "    Nothing transforms this tag, so a moving one is rolled by whoever "
                    "merges next, not by whoever deploys."
                )

    # 4. Every Evidara image under infra/hetzner is transformer-managed, and the
    #    migrate Job is the only exception.
    #
    #    This is the guard #884 needed and did not have. Checks 1-3 all reason about a
    #    tag that is already there; none of them can notice a workload that opted OUT
    #    of the transformer by writing its own. Marketing did exactly that for the
    #    whole life of the deployment, and check 3 waved it through because the tag it
    #    wrote was a syntactically perfect SHA.
    #
    #    Requiring an untagged reference plus a matching `images:` entry also closes a
    #    second hole in the same place: an untagged image with NO entry does not fail
    #    to deploy, it silently resolves to `:latest`.
    pinned_names = set(tags)
    for path in sorted((REPO_ROOT / HETZNER_DIR).rglob("*.yaml")):
        if path.resolve() == migrate_path.resolve():
            continue  # the one deliberate exception, enforced by check 2 instead
        if path.relative_to(REPO_ROOT / HETZNER_DIR).parts[0] in EXCLUDED_DIRS:
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        for match in _IMAGE_RE.finditer(text):
            if match.group("repo").startswith(EVIDARA_IMAGE_PREFIX):
                errors.append(
                    f"{rel}: `{match.group('repo')}` carries an inline tag.\n"
                    "    Only infra/hetzner/apps/migrate-job.yaml may do that. Everything else "
                    "is pinned once, in the `images:` transformer.\n"
                    "    An inline tag is how marketing came to serve a commit that was not on "
                    "`main` while every pin bump rolled past it (#884)."
                )
        for match in _UNTAGGED_IMAGE_RE.finditer(text):
            repo = match.group("repo")
            if not repo.startswith(EVIDARA_IMAGE_PREFIX):
                continue
            if repo not in pinned_names:
                errors.append(
                    f"{rel}: `{repo}` has no tag and no entry in {KUSTOMIZATION}'s `images:`.\n"
                    "    That does not fail to deploy — it resolves to `:latest`, which moves "
                    "under the cluster on someone else's merge."
                )

    if errors:
        for error in errors:
            _fail(error)
        return 1

    print(f"OK: hetzner app images and the migrate Job all pinned to {distinct[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
