#!/usr/bin/env python3
"""Ensure vendor/platform-contract.yaml matches the README contract pin."""

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
    r"^\*\*Pinned MacConfig platform contract:\*\* `(\d+\.\d+\.\d+)`\s*$",
    re.MULTILINE,
)


def fail(message: str) -> int:
    print(f"❌ {message}", file=sys.stderr)
    return 1


def main() -> int:
    if not VENDOR_REL.is_file():
        return fail(f"Missing {VENDOR_REL} — copy from MacConfig clusters/prod/platform-contract.yaml.")

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
            "**Pinned MacConfig platform contract:** `X.Y.Z`\n"
            "(update it whenever you bump contractVersion in the vendored YAML).",
        )

    readme_version = matches[0]
    if readme_version != raw_version:
        return fail(
            f"README pin ({readme_version}) does not match {VENDOR_REL} contractVersion ({raw_version}). "
            "Update both together when bumping the MacConfig contract pin.",
        )

    print(f"✅ MacConfig platform contract pin matches vendored contractVersion ({raw_version}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
