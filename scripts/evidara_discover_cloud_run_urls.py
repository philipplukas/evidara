#!/usr/bin/env python3
"""Parse `gcloud run services list --format=json` and emit shell exports for Evidara operator URLs.

Writes lines: export NAME='value' (shlex-quoted). Intended for: eval "$(gcloud ... | python3 ...)"
"""
from __future__ import annotations

import json
import shlex
import sys
from typing import Any


def _items(blob: Any) -> list[dict[str, Any]]:
    if isinstance(blob, list):
        return blob
    if isinstance(blob, dict):
        it = blob.get("items")
        if isinstance(it, list):
            return it
    return []


def _by_name(items: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for it in items:
        meta = it.get("metadata") or {}
        name = meta.get("name")
        if not isinstance(name, str) or not name:
            continue
        status = it.get("status") or {}
        url = status.get("url")
        if isinstance(url, str) and url.startswith("http"):
            out[name] = url.rstrip("/")
    return out


def _pick(by_name: dict[str, str], exact: str) -> str | None:
    if exact in by_name:
        return by_name[exact]
    for n, u in by_name.items():
        if n == exact or n.endswith(f"-{exact}") or exact in n:
            return u
    return None


def _guess_frontend(legal_search_api: str) -> str:
    if "legal-search-api" in legal_search_api:
        return legal_search_api.replace("legal-search-api", "legal-search-frontend", 1)
    return ""


def _guess_admin(platform_control_api: str) -> str:
    if "platform-control-api" in platform_control_api:
        return platform_control_api.replace("platform-control-api", "platform-control-admin", 1)
    return ""


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print("error: empty JSON from gcloud", file=sys.stderr)
        return 2
    try:
        blob = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON: {e}", file=sys.stderr)
        return 2

    by_name = _by_name(_items(blob))
    pc = _pick(by_name, "platform-control-api")
    ls = _pick(by_name, "legal-search-api")
    if not pc or not ls:
        names = ", ".join(sorted(by_name)) or "(none)"
        print(
            "error: could not resolve platform-control-api and/or legal-search-api URLs.\n"
            f"  Found services: {names}",
            file=sys.stderr,
        )
        return 2

    fe = _pick(by_name, "legal-search-frontend") or _guess_frontend(ls)
    ad = _pick(by_name, "platform-control-admin") or _guess_admin(pc)

    exports = {
        "EVIDARA_PLATFORM_CONTROL_URL": pc,
        "EVIDARA_LEGAL_SEARCH_URL": ls,
        "EVIDARA_LEGAL_SEARCH_FRONTEND_URL": fe or ls,
        "EVIDARA_PLATFORM_CONTROL_ADMIN_URL": ad or pc,
    }
    for k, v in exports.items():
        print(f"export {k}={shlex.quote(v)}")
    if not fe:
        print(
            "warn: legal-search-frontend not found; guessed frontend from API hostname",
            file=sys.stderr,
        )
    if not ad:
        print(
            "warn: platform-control-admin not found; guessed admin from API hostname",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
