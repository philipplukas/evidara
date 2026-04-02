from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.extractor_profile import ExtractorProfile
from platform_control.seed_reference_data import ReferenceDataSeeder


def _write_seed_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


async def _count_rows(session_maker: async_sessionmaker[AsyncSession], model) -> int:
    async with session_maker() as session:
        result = await session.scalars(select(model))
        return len(list(result))


@pytest.mark.asyncio
async def test_seed_reference_data_dry_run_does_not_persist(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    _write_seed_file(
        tmp_path / "reference" / "jurisdictions.yaml",
        {
            "version": 1,
            "items": [{"jurisdiction_id": "jur_ch", "slug": "ch", "name": "Switzerland"}],
        },
    )
    _write_seed_file(
        tmp_path / "reference" / "authorities.yaml",
        {
            "version": 1,
            "items": [
                {
                    "authority_id": "auth_ch_fedlex",
                    "jurisdiction_id": "jur_ch",
                    "slug": "ch-fedlex",
                    "name": "Fedlex",
                }
            ],
        },
    )
    _write_seed_file(
        tmp_path / "reference" / "extractor_profiles.yaml",
        {
            "version": 1,
            "items": [
                {
                    "extractor_profile_id": "exp_court_decision_v1",
                    "name": "Court Decision v1",
                    "source_family": "court_decision",
                    "version": "v1",
                    "definition": {"format": "court_decision"},
                }
            ],
        },
    )

    seeder = ReferenceDataSeeder(session_maker)
    summary = await seeder.seed(tmp_path, dry_run=True)

    assert summary.created["jurisdictions"] == 1
    assert summary.created["authorities"] == 1
    assert summary.created["extractor_profiles"] == 1
    assert await _count_rows(session_maker, Jurisdiction) == 0
    assert await _count_rows(session_maker, Authority) == 0
    assert await _count_rows(session_maker, ExtractorProfile) == 0


@pytest.mark.asyncio
async def test_seed_reference_data_is_idempotent_and_updates_existing_rows(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    jurisdictions = tmp_path / "reference" / "jurisdictions.yaml"
    authorities = tmp_path / "reference" / "authorities.yaml"
    extractor_profiles = tmp_path / "reference" / "extractor_profiles.yaml"

    _write_seed_file(
        jurisdictions,
        {
            "version": 1,
            "items": [{"jurisdiction_id": "jur_ch", "slug": "ch", "name": "Switzerland"}],
        },
    )
    _write_seed_file(
        authorities,
        {
            "version": 1,
            "items": [
                {
                    "authority_id": "auth_ch_fedlex",
                    "jurisdiction_id": "jur_ch",
                    "slug": "ch-fedlex",
                    "name": "Fedlex",
                }
            ],
        },
    )
    _write_seed_file(
        extractor_profiles,
        {
            "version": 1,
            "items": [
                {
                    "extractor_profile_id": "exp_court_decision_v1",
                    "name": "Court Decision v1",
                    "source_family": "court_decision",
                    "version": "v1",
                    "definition": {"format": "court_decision"},
                }
            ],
        },
    )

    seeder = ReferenceDataSeeder(session_maker)
    first_summary = await seeder.seed(tmp_path, dry_run=False)
    second_summary = await seeder.seed(tmp_path, dry_run=False)

    _write_seed_file(
        authorities,
        {
            "version": 1,
            "items": [
                {
                    "authority_id": "auth_ch_fedlex",
                    "jurisdiction_id": "jur_ch",
                    "slug": "ch-fedlex",
                    "name": "Fedlex Updated",
                }
            ],
        },
    )
    third_summary = await seeder.seed(tmp_path, dry_run=False)

    assert first_summary.created["authorities"] == 1
    assert second_summary.unchanged["authorities"] == 1
    assert third_summary.updated["authorities"] == 1

    async with session_maker() as session:
        authority = await session.get(Authority, "auth_ch_fedlex")
        assert authority is not None
        assert authority.name == "Fedlex Updated"
