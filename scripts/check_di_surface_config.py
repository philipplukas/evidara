#!/usr/bin/env python3
"""Guard the document-intelligence surface config against a silently unusable job (#806, ADR-0057).

The failure this exists to stop is a *configuration* one, and it cost real time.

`RuntimeSettings.from_env` resolves the canonical surface URIs down one of two branches
(`document-intelligence/src/document_intelligence/config/runtime.py`):

  - **root branch** — `DI_SURFACES_ROOT_URI` is set, and every surface, including
    `canonical_retractions`, is *derived* from it by `SurfaceUris.from_root_uri`.
  - **explicit branch** — any of `DI_PUBLISHED_{DOCUMENTS,SECTIONS}_URI` /
    `DI_PROCESSING_MANIFESTS_URI` is set, and each URI is read from its own key.
    `canonical_retractions_uri` comes from `DI_CANONICAL_RETRACTIONS_URI` and is
    **`None` when that key is absent** — nothing derives it.

Production takes the explicit branch. Between #971 (which shipped ADR-0057's retraction
job) and 2026-09-16 it did not set `DI_CANONICAL_RETRACTIONS_URI`, so
`document_intelligence_canonical_retract` raised `missing_retraction_ledger_config` and
removed nothing. The capability was deployed and unusable — ADR-0052's "declared means
produced", read from the config side.

Nothing caught it because nothing looked: the three published URIs are present and
correct, the workloads start fine, and the gap only appears when an operator tries to
retract. That is the worst time to find it — #806's known-wrong Bundesverfassung rows sat
in the production index, served to users, the whole while.

WHY A FILE CHECK AND NOT A RUNTIME ASSERTION
--------------------------------------------
Failing `RuntimeSettings` when the key is missing would break every DI workload that
never retracts — the consumer, the bridge, the document service — to protect one
operator job. The requirement is real but it is not universal, so it is enforced where it
is decidable without a cluster: in the file that configures production.

This cannot prove the bucket exists or that the credentials reach it. It proves the one
thing checkable from the files, which is the one thing that was actually wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIGMAP = REPO_ROOT / "infra" / "hetzner" / "apps" / "configmap.yaml"

#: Setting any of these selects the explicit branch in `RuntimeSettings.from_env`.
EXPLICIT_SURFACE_KEYS = (
    "DI_PUBLISHED_DOCUMENTS_URI",
    "DI_PUBLISHED_SECTIONS_URI",
    "DI_PROCESSING_MANIFESTS_URI",
)

#: Derived on the root branch, read directly on the explicit one.
RETRACTIONS_KEY = "DI_CANONICAL_RETRACTIONS_URI"

ROOT_KEY = "DI_SURFACES_ROOT_URI"


def _display(path: Path) -> str:
    """Repo-relative when it is inside the repo, absolute otherwise.

    `Path.relative_to` RAISES for a path outside the repo, which made the guard
    explode on any caller pointing it elsewhere — including its own tests.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load(path: Path) -> dict[str, str]:
    """Read the ConfigMap's `data` block.

    Deliberately not `yaml.safe_load`: `scripts/` runs under a bare `python3` in
    pre-commit, and requiring PyYAML here would make the guard skip on a workstation
    that lacks it — a check that silently does not run is the shape of defect this
    file is about. The `data:` block is flat `KEY: "value"` pairs, so a line scan is
    sufficient and has no dependency.
    """
    data: dict[str, str] = {}
    in_data = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("data:"):
            in_data = True
            continue
        if in_data and raw and not raw.startswith((" ", "\t")):
            in_data = False  # dedented out of `data:`
        if not in_data:
            continue
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def main() -> int:
    if not CONFIGMAP.exists():
        print(f"FAIL: {CONFIGMAP} not found", file=sys.stderr)
        return 1

    data = _load(CONFIGMAP)
    failures: list[str] = []

    explicit_present = [key for key in EXPLICIT_SURFACE_KEYS if data.get(key)]

    if explicit_present and not data.get(ROOT_KEY):
        if not data.get(RETRACTIONS_KEY):
            failures.append(
                f"{_display(CONFIGMAP)} sets {', '.join(explicit_present)}, which selects the\n"
                "  EXPLICIT surface branch in RuntimeSettings.from_env — and that branch does NOT derive\n"
                f"  the retraction ledger. Without {RETRACTIONS_KEY}, canonical_retract raises\n"
                "  `missing_retraction_ledger_config` and silently cannot remove a known-wrong canonical\n"
                "  row (ADR-0057, #806).\n"
                "  Fix: add\n"
                f"    {RETRACTIONS_KEY}: \"s3://evidara-lakehouse/canonical/canonical_retractions\""
            )
        elif not data[RETRACTIONS_KEY].startswith("s3://"):
            failures.append(
                f"{RETRACTIONS_KEY} must be an s3:// URI, got {data[RETRACTIONS_KEY]!r}"
            )

    if failures:
        print("document-intelligence surface config check FAILED:\n", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}\n", file=sys.stderr)
        return 1

    if not explicit_present:
        # Honest about what did NOT run, rather than printing a pass that means nothing.
        print(
            f"NOT APPLICABLE: {_display(CONFIGMAP)} sets no explicit published surface URI, "
            "so the retraction ledger is derived from the root URI."
        )
        return 0

    print(f"OK: explicit surface URIs are paired with {RETRACTIONS_KEY}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
