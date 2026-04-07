#!/usr/bin/env python3
"""Enforce manifest version bump when locked contract files change."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

import yaml


LOCKED_PREFIXES = ("contracts/api/", "contracts/events/")
MANIFEST_PATH = "contracts/manifest.yaml"


def run(args: list[str]) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "command failed")
    return proc.stdout


def load_manifest_version_from_file(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Missing manifest file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("version"), str):
        raise RuntimeError("contracts/manifest.yaml must define a string 'version'.")
    return data["version"].strip()


def load_manifest_version_from_git(ref: str) -> str | None:
    proc = subprocess.run(
        ["git", "show", f"{ref}:{MANIFEST_PATH}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    data = yaml.safe_load(proc.stdout)
    if not isinstance(data, dict) or not isinstance(data.get("version"), str):
        raise RuntimeError(f"{MANIFEST_PATH} at {ref} is missing string 'version'.")
    return data["version"].strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Require contracts/manifest.yaml version bump on contract changes."
    )
    parser.add_argument("--base", required=True, help="Base git ref/sha")
    parser.add_argument("--head", default="HEAD", help="Head git ref/sha (default: HEAD)")
    args = parser.parse_args()

    changed_raw = run(["git", "diff", "--name-only", f"{args.base}...{args.head}"])
    changed_files = [line.strip() for line in changed_raw.splitlines() if line.strip()]
    locked_changed = [p for p in changed_files if p.startswith(LOCKED_PREFIXES)]

    if not locked_changed:
        print("No locked contract files changed; version bump guard skipped.")
        return 0

    print("Locked contract files changed:")
    for path in locked_changed:
        print(f" - {path}")

    if MANIFEST_PATH not in changed_files:
        print(
            "❌ Locked contract files changed but contracts/manifest.yaml was not updated.",
            file=sys.stderr,
        )
        return 2

    current_version = load_manifest_version_from_file(Path(MANIFEST_PATH))
    base_version = load_manifest_version_from_git(args.base)
    if base_version is None:
        print(
            "Manifest is newly introduced relative to base; treating as valid version declaration."
        )
        return 0

    if current_version == base_version:
        print(
            f"❌ contracts/manifest.yaml version did not change (still {current_version}).",
            file=sys.stderr,
        )
        return 2

    print(
        f"✅ contracts/manifest.yaml version bumped: {base_version} -> {current_version}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
