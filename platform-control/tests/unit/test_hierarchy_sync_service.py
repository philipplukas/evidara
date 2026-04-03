from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.scrape_target import ScrapeTarget
from platform_control.services.hierarchy_sync_service import HierarchySyncService


def _write_hierarchy_files(
    root: Path,
    *,
    jurisdictions: list[dict],
    authorities: list[dict],
    scraping: list[dict],
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "jurisdictions.yaml").write_text(
        yaml.safe_dump({"version": 1, "items": jurisdictions}, sort_keys=False), encoding="utf-8"
    )
    (root / "authorities.yaml").write_text(
        yaml.safe_dump({"version": 1, "items": authorities}, sort_keys=False), encoding="utf-8"
    )
    (root / "scraping.yaml").write_text(
        yaml.safe_dump({"version": 1, "items": scraping}, sort_keys=False), encoding="utf-8"
    )
    return root


@pytest.mark.asyncio
async def test_sync_creates_hierarchy_entities(session, tmp_path: Path) -> None:
    hierarchy_dir = _write_hierarchy_files(
        tmp_path / "hierarchies",
        jurisdictions=[
            {"jurisdiction_id": "jur_ch", "path": "ch", "slug": "ch", "name": "Switzerland"},
            {
                "jurisdiction_id": "jur_ch_federal",
                "path": "ch/federal",
                "slug": "ch-federal",
                "name": "Swiss Confederation",
            },
        ],
        authorities=[
            {
                "authority_id": "auth_fedlex",
                "jurisdiction_path": "ch/federal",
                "path": "ch/federal/fedlex",
                "slug": "fedlex",
                "name": "Fedlex",
            }
        ],
        scraping=[
            {
                "scrape_target_id": "stg_ch_fedlex_law",
                "authority_path": "ch/federal/fedlex",
                "path": "ch/federal/fedlex/law",
                "enabled": True,
                "selector": {"seed_url": "https://www.fedlex.admin.ch"},
            }
        ],
    )

    summary = await HierarchySyncService(session).sync(hierarchy_dir)
    assert summary.jurisdictions.created == 2
    assert summary.authorities.created == 1
    assert summary.scrape_targets.created == 1


@pytest.mark.asyncio
async def test_sync_sets_jurisdiction_parent_and_depth(session, tmp_path: Path) -> None:
    hierarchy_dir = _write_hierarchy_files(
        tmp_path / "hierarchies",
        jurisdictions=[
            {"jurisdiction_id": "jur_ch", "path": "ch", "slug": "ch", "name": "Switzerland"},
            {
                "jurisdiction_id": "jur_ch_federal",
                "path": "ch/federal",
                "slug": "ch-federal",
                "name": "Swiss Confederation",
            },
        ],
        authorities=[],
        scraping=[],
    )

    await HierarchySyncService(session).sync(hierarchy_dir)
    child = await session.get(Jurisdiction, "jur_ch_federal")
    assert child is not None
    assert child.parent_id == "jur_ch"
    assert child.depth == 1


@pytest.mark.asyncio
async def test_sync_sets_authority_parent_and_depth(session, tmp_path: Path) -> None:
    hierarchy_dir = _write_hierarchy_files(
        tmp_path / "hierarchies",
        jurisdictions=[
            {"jurisdiction_id": "jur_ch", "path": "ch", "slug": "ch", "name": "Switzerland"},
            {
                "jurisdiction_id": "jur_ch_federal",
                "path": "ch/federal",
                "slug": "ch-federal",
                "name": "Swiss Confederation",
            },
        ],
        authorities=[
            {
                "authority_id": "auth_fedlex",
                "jurisdiction_path": "ch/federal",
                "path": "ch/federal/fedlex",
                "slug": "fedlex",
                "name": "Fedlex",
            },
            {
                "authority_id": "auth_fedlex_law",
                "jurisdiction_path": "ch/federal",
                "path": "ch/federal/fedlex/law",
                "slug": "fedlex-law",
                "name": "Fedlex Law Collection",
            },
        ],
        scraping=[],
    )

    await HierarchySyncService(session).sync(hierarchy_dir)
    child = await session.get(Authority, "auth_fedlex_law")
    assert child is not None
    assert child.parent_id == "auth_fedlex"
    assert child.depth == 3


@pytest.mark.asyncio
async def test_sync_updates_existing_rows(session, tmp_path: Path) -> None:
    session.add(
        Jurisdiction(
            jurisdiction_id="jur_ch",
            path="ch",
            depth=0,
            slug="ch",
            name="Old Switzerland",
        )
    )
    await session.commit()

    hierarchy_dir = _write_hierarchy_files(
        tmp_path / "hierarchies",
        jurisdictions=[
            {"jurisdiction_id": "jur_ch", "path": "ch", "slug": "ch", "name": "Switzerland"}
        ],
        authorities=[],
        scraping=[],
    )
    summary = await HierarchySyncService(session).sync(hierarchy_dir)
    updated = await session.get(Jurisdiction, "jur_ch")
    assert updated is not None
    assert updated.name == "Switzerland"
    assert summary.jurisdictions.updated == 1


@pytest.mark.asyncio
async def test_sync_second_run_marks_unchanged(session, tmp_path: Path) -> None:
    hierarchy_dir = _write_hierarchy_files(
        tmp_path / "hierarchies",
        jurisdictions=[
            {"jurisdiction_id": "jur_ch", "path": "ch", "slug": "ch", "name": "Switzerland"}
        ],
        authorities=[],
        scraping=[],
    )
    service = HierarchySyncService(session)
    await service.sync(hierarchy_dir)
    summary = await service.sync(hierarchy_dir)
    assert summary.jurisdictions.unchanged == 1


@pytest.mark.asyncio
async def test_scrape_target_is_linked_to_authority_and_jurisdiction(
    session, tmp_path: Path
) -> None:
    hierarchy_dir = _write_hierarchy_files(
        tmp_path / "hierarchies",
        jurisdictions=[
            {"jurisdiction_id": "jur_at", "path": "at", "slug": "at", "name": "Austria"},
            {
                "jurisdiction_id": "jur_at_federal",
                "path": "at/federal",
                "slug": "at-federal",
                "name": "Republic of Austria",
            },
        ],
        authorities=[
            {
                "authority_id": "auth_ris",
                "jurisdiction_path": "at/federal",
                "path": "at/federal/ris",
                "slug": "ris",
                "name": "RIS",
            }
        ],
        scraping=[
            {
                "scrape_target_id": "stg_at_ris_law",
                "authority_path": "at/federal/ris",
                "path": "at/federal/ris/law",
                "enabled": True,
                "selector": {"seed_url": "https://www.ris.bka.gv.at"},
            }
        ],
    )
    await HierarchySyncService(session).sync(hierarchy_dir)
    target = await session.get(ScrapeTarget, "stg_at_ris_law")
    assert target is not None
    assert target.authority_id == "auth_ris"
    assert target.jurisdiction_id == "jur_at_federal"


@pytest.mark.asyncio
async def test_missing_jurisdiction_parent_path_raises(session, tmp_path: Path) -> None:
    hierarchy_dir = _write_hierarchy_files(
        tmp_path / "hierarchies",
        jurisdictions=[
            {
                "jurisdiction_id": "jur_ch_federal",
                "path": "ch/federal",
                "slug": "ch-federal",
                "name": "Swiss Confederation",
            }
        ],
        authorities=[],
        scraping=[],
    )
    with pytest.raises(ValueError, match="Missing parent jurisdiction path"):
        await HierarchySyncService(session).sync(hierarchy_dir)


@pytest.mark.asyncio
async def test_missing_scrape_authority_path_raises(session, tmp_path: Path) -> None:
    hierarchy_dir = _write_hierarchy_files(
        tmp_path / "hierarchies",
        jurisdictions=[
            {"jurisdiction_id": "jur_ch", "path": "ch", "slug": "ch", "name": "Switzerland"}
        ],
        authorities=[],
        scraping=[
            {
                "scrape_target_id": "stg_missing",
                "authority_path": "ch/federal/fedlex",
                "path": "ch/federal/fedlex/law",
                "enabled": True,
                "selector": {"seed_url": "https://www.fedlex.admin.ch"},
            }
        ],
    )
    with pytest.raises(ValueError, match="unknown authority_path"):
        await HierarchySyncService(session).sync(hierarchy_dir)


@pytest.mark.asyncio
async def test_upsert_by_path_updates_existing_id_match(session, tmp_path: Path) -> None:
    session.add(
        Authority(
            authority_id="auth_old",
            jurisdiction_id=None,
            parent_id=None,
            path="ch/federal/fedlex",
            depth=2,
            slug="old",
            name="Old Name",
        )
    )
    session.add(
        Jurisdiction(
            jurisdiction_id="jur_ch",
            path="ch",
            depth=0,
            slug="ch",
            name="Switzerland",
        )
    )
    session.add(
        Jurisdiction(
            jurisdiction_id="jur_ch_federal",
            parent_id="jur_ch",
            path="ch/federal",
            depth=1,
            slug="ch-federal",
            name="Swiss Confederation",
        )
    )
    await session.commit()

    hierarchy_dir = _write_hierarchy_files(
        tmp_path / "hierarchies",
        jurisdictions=[
            {"jurisdiction_id": "jur_ch", "path": "ch", "slug": "ch", "name": "Switzerland"},
            {
                "jurisdiction_id": "jur_ch_federal",
                "path": "ch/federal",
                "slug": "ch-federal",
                "name": "Swiss Confederation",
            },
        ],
        authorities=[
            {
                "authority_id": "auth_new",
                "jurisdiction_path": "ch/federal",
                "path": "ch/federal/fedlex",
                "slug": "fedlex",
                "name": "Fedlex",
            }
        ],
        scraping=[],
    )
    summary = await HierarchySyncService(session).sync(hierarchy_dir)

    by_path = await session.scalar(select(Authority).where(Authority.path == "ch/federal/fedlex"))
    assert by_path is not None
    assert by_path.authority_id == "auth_old"
    assert by_path.slug == "fedlex"
    assert summary.authorities.updated == 1


@pytest.mark.asyncio
async def test_sync_dry_run_rolls_back_changes(session, tmp_path: Path) -> None:
    hierarchy_dir = _write_hierarchy_files(
        tmp_path / "hierarchies",
        jurisdictions=[
            {"jurisdiction_id": "jur_ch", "path": "ch", "slug": "ch", "name": "Switzerland"}
        ],
        authorities=[],
        scraping=[],
    )
    await HierarchySyncService(session).sync(hierarchy_dir, dry_run=True)
    stored = await session.get(Jurisdiction, "jur_ch")
    assert stored is None
