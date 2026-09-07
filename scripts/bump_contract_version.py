#!/usr/bin/env python3
"""Bump the contract versions that must move together, correctly, in one command.

There are TWO numbers and they are enforced by TWO different gates:

  - `contracts/manifest.yaml`'s **top-level** `version` — the only key
    `check_contract_version_bump.py` reads. It fires on any change under
    `contracts/api/` or `contracts/events/`.
  - `apis.platform_control.version` — which `check_contract_manifest.py` requires
    to equal `platform_control.openapi.API_VERSION`, the value the app serves as
    `info.version`.

Getting one and not the other is the single most repeated mistake against this
repo's contracts: three PRs from one lane missed the top-level bump in a single
day (2026-09-03), and `AGENTS.md` had to grow a paragraph about it. The rule is
not hard — it is just invisible, because neither gate mentions the other.

## Why this script exists rather than a merge driver

Two PRs that both bump the top-level version conflict on one line. Nothing can
prevent that: it is a single shared scalar, and a merge driver that picked one
side automatically would silently discard the other PR's intent, which is worse
than a conflict.

What this removes is the *cost* of the conflict. Resolving it by hand means
remembering both numbers, the equality constraint, and which gate reads which —
in the middle of a rebase. Here it is one command that cannot get the pairing
wrong.

## Usage

    python3 scripts/bump_contract_version.py --minor          # additive change
    python3 scripts/bump_contract_version.py --patch          # editorial only
    python3 scripts/bump_contract_version.py --minor --api    # also bump API_VERSION

`--api` bumps `platform_control.openapi.API_VERSION` and mirrors it into
`apis.platform_control.version`, keeping the equality the manifest gate asserts.
Use it when the platform-control OpenAPI surface changed; omit it for a
`contracts/events/` or hand-authored-spec change that leaves the app untouched.

Prints what it changed and exits non-zero if it changed nothing, so a caller
cannot mistake a no-op for success.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "contracts" / "manifest.yaml"
OPENAPI_MODULE = REPO_ROOT / "platform-control" / "src" / "platform_control" / "openapi.py"

# Anchored at column 0 so it cannot match the indented `apis.<name>.version`.
_TOP_LEVEL_VERSION = re.compile(r'^version:\s*"(?P<value>\d+\.\d+\.\d+)"', re.MULTILINE)
_API_VERSION_CONST = re.compile(r'^API_VERSION\s*=\s*"(?P<value>\d+\.\d+\.\d+)"', re.MULTILINE)


def bump(version: str, part: str) -> str:
    major, minor, patch = (int(piece) for piece in version.split("."))
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unsupported part: {part}")


def _replace_once(text: str, pattern: re.Pattern[str], new_value: str, label: str) -> tuple[str, str]:
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"FAIL: could not find {label}")
    old = match.group("value")
    start, end = match.span("value")
    return text[:start] + new_value + text[end:], old


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--minor", action="store_const", const="minor", dest="part")
    group.add_argument("--patch", action="store_const", const="patch", dest="part")
    parser.add_argument(
        "--api",
        action="store_true",
        help="also bump platform_control.openapi.API_VERSION and mirror it into "
        "apis.platform_control.version (use when the platform-control surface changed)",
    )
    args = parser.parse_args()

    manifest_text = MANIFEST.read_text(encoding="utf-8")
    current = _TOP_LEVEL_VERSION.search(manifest_text)
    if current is None:
        raise SystemExit("FAIL: contracts/manifest.yaml has no top-level `version`")
    new_top = bump(current.group("value"), args.part)
    manifest_text, old_top = _replace_once(
        manifest_text, _TOP_LEVEL_VERSION, new_top, "the top-level `version`"
    )
    print(f"contracts/manifest.yaml  version: {old_top} -> {new_top}")

    if args.api:
        openapi_text = OPENAPI_MODULE.read_text(encoding="utf-8")
        current_api = _API_VERSION_CONST.search(openapi_text)
        if current_api is None:
            raise SystemExit("FAIL: could not find API_VERSION in platform_control/openapi.py")
        new_api = bump(current_api.group("value"), args.part)
        openapi_text, old_api = _replace_once(
            openapi_text, _API_VERSION_CONST, new_api, "API_VERSION"
        )
        OPENAPI_MODULE.write_text(openapi_text, encoding="utf-8")
        print(f"platform_control/openapi.py  API_VERSION: {old_api} -> {new_api}")

        # Mirror into the manifest so `check_contract_manifest.py`'s equality holds.
        # Matched inside the `platform_control:` block only — a bare `version:` search
        # would hit the top-level key that was just bumped.
        api_block = re.compile(
            r'(?P<head>^  platform_control:.*?^    version:\s*")(?P<value>\d+\.\d+\.\d+)(?P<tail>")',
            re.MULTILINE | re.DOTALL,
        )
        match = api_block.search(manifest_text)
        if match is None:
            raise SystemExit("FAIL: could not find apis.platform_control.version in the manifest")
        manifest_text = (
            manifest_text[: match.start("value")] + new_api + manifest_text[match.end("value") :]
        )
        print(f"contracts/manifest.yaml  apis.platform_control.version: -> {new_api}")

    MANIFEST.write_text(manifest_text, encoding="utf-8")

    print()
    if args.api:
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
    print("Then add a line to the manifest saying WHAT changed and whether it is additive —")
    print("the number alone tells a reader nothing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
