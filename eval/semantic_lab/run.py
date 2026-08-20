"""Emit the v0.5 semantic certificate for a frozen fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import certify, load_fixture


DEFAULT_FIXTURE = Path(__file__).parent / "fixtures" / "reporting_v0.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", nargs="?", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--parent", default="U")
    args = parser.parse_args()

    fixture = load_fixture(args.fixture)
    certificate = certify(fixture, args.parent)
    print(json.dumps(certificate.to_dict(), indent=2, sort_keys=True))
    return 0 if certificate.status == "CERTIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
