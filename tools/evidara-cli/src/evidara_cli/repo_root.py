"""Locate the Evidara monorepo root (directory containing contracts/api/)."""

from __future__ import annotations

from pathlib import Path


def resolve_repo_root(explicit: Path | None = None) -> Path:
    """Walk upward from ``explicit`` or cwd until ``contracts/api`` exists.

    If ``explicit`` is set but no marker is found in its ancestors, returns
    ``explicit.resolve()`` so callers can use a forced root (e.g. temp dirs in tests).
    """
    home = Path.home()

    if explicit is not None:
        ex = explicit.resolve()
        for root in [ex, *ex.parents]:
            if root == home:
                break
            if (root / "contracts" / "api").is_dir():
                return root
        return ex

    cwd = Path.cwd().resolve()
    for root in [cwd, *cwd.parents]:
        if root == home:
            break
        if (root / "contracts" / "api").is_dir():
            return root
    return cwd
