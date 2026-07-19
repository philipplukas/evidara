#!/usr/bin/env python3
"""Generate contracts/api/platform-control.openapi.yaml from the FastAPI app.

AGENTS.md declares the contract the source of truth. For platform-control it was
not: the file was hand-maintained and described *less* than the code did. It
modelled 4 of the 11 `AcquisitionProvider` variants, never mentioned
`execution_mode`, documented list responses as a bare `data` array when the real
ones carry `{data, limit, offset, total}`, and advertised an `Authorization:
Bearer <JWT>` scheme the service has never implemented.

Consumers that believed it shipped bugs: #614 (the admin editor knew 4 providers,
coerced the other 7 to firecrawl and persisted the damage with a 200) and #616
(the admin capped every list at 100 because the contract implied unbounded
arrays). Worse, the drift defeated the standard fix — #617 explicitly refused to
derive the provider list from the contract, because doing so would have
reproduced #614 with a generator's blessing.

So the contract is now an export of the app's own `/openapi.json`, and
`--check` is the drift guard: change a model without regenerating and the build
fails. The generator is deliberately dumb — it applies **no** overlay. Anything
the document needs that routes and models cannot express lives in
`platform_control.openapi` (title, version, description, tags, operation-id
policy), so the served document and the committed one are the same bytes. An
overlay here would be a second source of truth, which is the thing that broke.

`info.version` comes from `platform_control.openapi.API_VERSION` and is pinned to
`contracts/manifest.yaml` by scripts/check_contract_manifest.py; a spec change
therefore also trips scripts/check_contract_version_bump.py, which is correct —
a contract change should be a versioned event.

Usage:
    # from the repo root, needs the platform-control venv:
    cd platform-control && uv run python ../scripts/generate_platform_control_contract.py
    cd platform-control && uv run python ../scripts/generate_platform_control_contract.py --check
"""

from __future__ import annotations

import argparse
import difflib
import os
from pathlib import Path
import sys
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "contracts" / "api" / "platform-control.openapi.yaml"

HEADER = """\
# GENERATED FILE — DO NOT EDIT.
#
# Exported from the platform-control FastAPI app (its `/openapi.json`) by
# scripts/generate_platform_control_contract.py. This file is the contract
# *because* it is the app's own schema — hand-editing it re-opens the drift that
# caused #614 and #616 (see #618).
#
# To change this contract, change the code:
#   - endpoints/tags          platform-control/src/platform_control/routers/
#   - request/response shapes platform-control/src/platform_control/schemas/
#   - document metadata       platform-control/src/platform_control/openapi.py
# then regenerate:
#   cd platform-control && uv run python ../scripts/generate_platform_control_contract.py
#
# `--check` runs in scripts/check-platform-control.sh (pre-commit + CI).
"""


class _Dumper(yaml.SafeDumper):
    """Block style everywhere, and no anchors/aliases.

    PyYAML aliases repeated objects by identity (`&id001` / `*id001`). FastAPI
    reuses the same dict for, say, a shared response, so the default dump would
    emit aliases — legal YAML that many OpenAPI tools cannot read.
    """

    def ignore_aliases(self, data: Any) -> bool:
        return True


def _str_representer(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    """Render multi-line strings as literal blocks so descriptions stay readable."""
    if "\n" in data and not any(line.rstrip() != line for line in data.split("\n")):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_representer)


def render() -> str:
    """Return the contract YAML text for the current app."""
    # `Settings.environment` is required and has no default (#683). This is a build-time
    # export, not a deployment, so it declares "development" rather than inheriting one —
    # the value does not appear in the generated document.
    os.environ.setdefault("PLATFORM_CONTROL_ENVIRONMENT", "development")

    # Imported lazily: this module is importable from the repo root for `--help`,
    # but `platform_control` only resolves inside the platform-control venv.
    from platform_control.main import create_app

    schema = create_app().openapi()
    body = yaml.dump(
        schema,
        Dumper=_Dumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )
    return HEADER + body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed contract differs from the app's schema (drift guard).",
    )
    args = parser.parse_args()

    generated = render()
    relative = CONTRACT_PATH.relative_to(REPO_ROOT)

    if not args.check:
        CONTRACT_PATH.write_text(generated, encoding="utf-8")
        print(f"✅ Wrote {relative} from the FastAPI app.")
        return 0

    committed = CONTRACT_PATH.read_text(encoding="utf-8") if CONTRACT_PATH.exists() else ""
    if committed == generated:
        print(f"✅ {relative} matches the FastAPI app.")
        return 0

    diff = difflib.unified_diff(
        committed.splitlines(keepends=True),
        generated.splitlines(keepends=True),
        fromfile=f"{relative} (committed)",
        tofile=f"{relative} (generated from the app)",
    )
    sys.stderr.writelines(diff)
    print(
        f"\n❌ {relative} is out of date with the platform-control app.\n"
        "   The code is the contract. Regenerate and commit:\n"
        "     cd platform-control && uv run python ../scripts/"
        "generate_platform_control_contract.py\n"
        "   Then bump apis.platform_control.version in contracts/manifest.yaml and\n"
        "   API_VERSION in platform-control/src/platform_control/openapi.py together.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
