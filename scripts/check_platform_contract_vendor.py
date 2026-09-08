#!/usr/bin/env python3
"""Ensure vendor/platform-contract.yaml matches the README contract pin.

The vendored file is a pinned copy of contracts/platform.yaml in
philipplukas/research-platform, which is measured against the live cluster there.
This check only asserts that the copy and the README pin agree; it cannot tell
whether the copy is stale relative to upstream, so refresh it deliberately.

Until 2026-09-08 this guarded a contract that named MacConfig as the platform
owner and described ingress class nginx, an evidare-* namespace pattern and a
shared-vault ClusterSecretStore -- none of which existed. The check was passing
the whole time, because a pin matching a fiction is still a matching pin.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


VENDOR_REL = Path("vendor/platform-contract.yaml")
README_PATH = Path("README.md")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
# README must document the same contractVersion as the vendored YAML (single line).
README_PIN_PATTERN = re.compile(
    r"^\*\*Pinned platform contract:\*\* `(\d+\.\d+\.\d+)`\s*$",
    re.MULTILINE,
)


def fail(message: str) -> int:
    print(f"❌ {message}", file=sys.stderr)
    return 1


def main() -> int:
    if not VENDOR_REL.is_file():
        return fail(f"Missing {VENDOR_REL} — copy from research-platform contracts/platform.yaml.")

    data = yaml.safe_load(VENDOR_REL.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return fail(f"{VENDOR_REL} must be a YAML mapping.")
    raw_version = data.get("contractVersion")
    if not isinstance(raw_version, str) or not SEMVER_PATTERN.match(raw_version):
        return fail(f"{VENDOR_REL} must set string contractVersion as semver (for example 0.1.0).")

    readme = README_PATH.read_text(encoding="utf-8")
    matches = README_PIN_PATTERN.findall(readme)
    if len(matches) != 1:
        return fail(
            "README.md must contain exactly one pin line of the form:\n"
            "**Pinned platform contract:** `X.Y.Z`\n"
            "(update it whenever you refresh the vendored YAML).",
        )

    readme_version = matches[0]
    if readme_version != raw_version:
        return fail(
            f"README pin ({readme_version}) does not match {VENDOR_REL} contractVersion ({raw_version}). "
            "Update both together when refreshing the vendored contract.",
        )

    print(f"✅ Platform contract pin matches vendored contractVersion ({raw_version}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
