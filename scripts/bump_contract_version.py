#!/usr/bin/env python3
"""Declare a contract change: write a changeset, and move the API number with it.

There are TWO numbers, enforced by TWO different gates, and they now move at
DIFFERENT times:

  - `contracts/manifest.yaml`'s **top-level** `version` — no longer edited per
    PR. Every contract PR used to hand-edit it, which serialised the repo on one
    scalar (#913). A PR now drops a changeset under `contracts/changes/`, and
    `scripts/release_contract_version.py` computes the number once, at release,
    from the accumulated changesets. `check_contract_version_bump.py` requires
    the changeset.
  - `apis.platform_control.version` — which `check_contract_manifest.py` requires
    to equal the GENERATED spec's `info.version`. That is pinned to the app, so
    it cannot be deferred to a release and still moves in the PR, via `--api`.

Getting one and not the other is the single most repeated mistake against this
repo's contracts: three PRs from one lane missed the top-level bump in a single
day (2026-09-03). This script is the one command that cannot get the pairing
wrong.

## Why a changeset and not a merge driver

A custom git merge driver is not viable here: it needs `merge.<driver>.driver`
in each clone's local git config, which CI checkouts and new contributors do not
have. Git then falls back to the default merge silently — the guard would be
*absent* rather than wrong, which is the failure shape this repo has been bitten
by repeatedly. And a driver that auto-picked one side of a version bump would
discard the other PR's intent, which is worse than a conflict.

A changeset needs no local configuration, because there is nothing to merge:
two PRs write two different files.

## Usage

    python3 scripts/bump_contract_version.py --minor --summary "..."
    python3 scripts/bump_contract_version.py --patch --summary "..." --breaking
    python3 scripts/bump_contract_version.py --minor --summary "..." --api

`--api` bumps `platform_control.openapi.API_VERSION` and mirrors it into
`apis.platform_control.version`, keeping the equality the manifest gate asserts.
Use it when the platform-control OpenAPI surface changed; omit it for a
`contracts/events/` or hand-authored-spec change that leaves the app untouched.

Prints what it changed and never exits quietly into a state a gate rejects.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_changesets as cs  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "contracts" / "manifest.yaml"
CHANGES_DIR = REPO_ROOT / cs.CHANGESET_DIR
OPENAPI_MODULE = REPO_ROOT / "platform-control" / "src" / "platform_control" / "openapi.py"

_API_VERSION_CONST = re.compile(r'^API_VERSION\s*=\s*"(?P<value>\d+\.\d+\.\d+)"', re.MULTILINE)


def bump(version: str, part: str) -> str:
    """Kept as a re-export so callers and tests have one implementation."""
    return cs.next_version(version, part)


def slugify(summary: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", summary.lower()).strip("-")
    return "-".join(slug.split("-")[:6]) or "contract-change"


def changeset_filename(summary: str, slug: str | None) -> str:
    """Unique by construction.

    Two PRs choosing the same descriptive name would reintroduce the conflict
    this whole mechanism exists to remove — as an add/add on one path — so the
    random suffix is not cosmetic.
    """
    base = slug or slugify(summary)
    return f"{base}-{secrets.token_hex(4)}{cs.CHANGESET_SUFFIX}"


def write_changeset(path: Path, part: str, additive: bool, summary: str) -> None:
    body = (
        f"bump: {part}\n"
        f"additive: {'true' if additive else 'false'}\n"
        "summary: >-\n"
        + "".join(f"  {line}\n" for line in summary.strip().splitlines())
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--minor", action="store_const", const="minor", dest="part")
    group.add_argument("--patch", action="store_const", const="patch", dest="part")
    parser.add_argument(
        "--summary",
        required=True,
        help="what changed on the locked surface, in prose (the number alone "
        "tells a reader nothing)",
    )
    parser.add_argument(
        "--breaking",
        action="store_true",
        help="record the change as NOT additive: a consumer that ignores it breaks",
    )
    parser.add_argument("--slug", help="filename stem for the changeset (a suffix is added)")
    parser.add_argument(
        "--api",
        action="store_true",
        help="also bump platform_control.openapi.API_VERSION and mirror it into "
        "apis.platform_control.version (use when the platform-control surface changed)",
    )
    args = parser.parse_args()

    if len(args.summary.strip()) < cs.MIN_SUMMARY_CHARS:
        raise SystemExit(
            f"FAIL: --summary must be at least {cs.MIN_SUMMARY_CHARS} characters of prose."
        )

    path = CHANGES_DIR / changeset_filename(args.summary, args.slug)
    write_changeset(path, args.part, not args.breaking, args.summary)
    print(f"wrote {path.relative_to(REPO_ROOT)} ({args.part}, "
          f"{'additive' if not args.breaking else 'NOT additive'})")

    if args.api:
        openapi_text = OPENAPI_MODULE.read_text(encoding="utf-8")
        current_api = _API_VERSION_CONST.search(openapi_text)
        if current_api is None:
            raise SystemExit("FAIL: could not find API_VERSION in platform_control/openapi.py")
        old_api = current_api.group("value")
        new_api = bump(old_api, args.part)
        start, end = current_api.span("value")
        OPENAPI_MODULE.write_text(
            openapi_text[:start] + new_api + openapi_text[end:], encoding="utf-8"
        )
        print(f"platform_control/openapi.py  API_VERSION: {old_api} -> {new_api}")

        # Mirror into the manifest so `check_contract_manifest.py`'s equality holds.
        # Matched inside the `platform_control:` block only — a bare `version:` search
        # would hit the top-level key, which only the release step may write.
        manifest_text = MANIFEST.read_text(encoding="utf-8")
        api_block = re.compile(
            r'(?P<head>^  platform_control:.*?^    version:\s*")(?P<value>\d+\.\d+\.\d+)(?P<tail>")',
            re.MULTILINE | re.DOTALL,
        )
        match = api_block.search(manifest_text)
        if match is None:
            raise SystemExit("FAIL: could not find apis.platform_control.version in the manifest")
        MANIFEST.write_text(
            manifest_text[: match.start("value")] + new_api + manifest_text[match.end("value") :],
            encoding="utf-8",
        )
        print(f"contracts/manifest.yaml  apis.platform_control.version: -> {new_api}")

        print()
        # `check_contract_manifest.py` compares apis.platform_control.version to the
        # GENERATED spec's `info.version`, not to the module constant. Bumping
        # API_VERSION therefore leaves the repo failing that gate until the contract
        # is regenerated — a broken state this script must not exit quietly into.
        print("REQUIRED NEXT STEP — the repo is failing `check_contract_manifest.py` until you run:")
        print()
        print("    cd platform-control && uv run python ../scripts/generate_platform_control_contract.py")
        print()
        print("The gate compares the manifest against the GENERATED spec's info.version,")
        print("not against API_VERSION, so the constant alone is not enough.")

    print()
    print("Do NOT hand-edit contracts/manifest.yaml's top-level `version`: it is computed")
    print("at release by scripts/release_contract_version.py. Editing it per PR is what")
    print("made two concurrent contract PRs conflict (#913).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
