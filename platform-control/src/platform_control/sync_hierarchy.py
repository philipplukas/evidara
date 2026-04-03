from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from platform_control.database import get_session_maker
from platform_control.services.hierarchy_sync_service import HierarchySyncService

DEFAULT_HIERARCHY_DIR = Path(__file__).resolve().parents[2] / "hierarchies"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync platform-control hierarchy data from YAML files."
    )
    parser.add_argument(
        "--hierarchy-dir",
        type=Path,
        default=DEFAULT_HIERARCHY_DIR,
        help="Directory containing jurisdictions.yaml, authorities.yaml, and scraping.yaml.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report changes without committing them.",
    )
    return parser.parse_args()


async def _run(hierarchy_dir: Path, dry_run: bool) -> None:
    session_maker = get_session_maker()
    async with session_maker() as session:
        summary = await HierarchySyncService(session).sync(hierarchy_dir, dry_run=dry_run)
    print(f"Hierarchy directory: {hierarchy_dir}")
    print(f"Dry run: {dry_run}")
    print(
        "jurisdictions: "
        f"created={summary.jurisdictions.created} "
        f"updated={summary.jurisdictions.updated} "
        f"unchanged={summary.jurisdictions.unchanged}"
    )
    print(
        "authorities: "
        f"created={summary.authorities.created} "
        f"updated={summary.authorities.updated} "
        f"unchanged={summary.authorities.unchanged}"
    )
    print(
        "scrape_targets: "
        f"created={summary.scrape_targets.created} "
        f"updated={summary.scrape_targets.updated} "
        f"unchanged={summary.scrape_targets.unchanged}"
    )


def main() -> None:
    args = parse_args()
    asyncio.run(_run(hierarchy_dir=args.hierarchy_dir, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
