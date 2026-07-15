from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.domain import NORM_LEVEL_RANK, NormLevel
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.extractor_profile import ExtractorProfile
from platform_control.seed_reference_data import (
    AliasedIdRenameRequiredError,
    ReferenceDataSeeder,
)


def _write_seed_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_compliance_policies(path: Path, items: list[dict] | None = None) -> None:
    _write_seed_file(path, {"version": 1, "items": items or []})


async def _count_rows(session_maker: async_sessionmaker[AsyncSession], model) -> int:
    async with session_maker() as session:
        result = await session.scalars(select(model))
        return len(list(result))


@pytest.mark.asyncio
async def test_seed_reference_data_dry_run_does_not_persist(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    _write_compliance_policies(tmp_path / "reference" / "compliance_policies.yaml")
    _write_seed_file(
        tmp_path / "reference" / "jurisdictions.yaml",
        {
            "version": 1,
            "items": [
                {
                    "jurisdiction_id": "jur_ch",
                    "slug": "ch",
                    "name": "Switzerland",
                    "level": "federal",
                }
            ],
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
    compliance_policies = tmp_path / "reference" / "compliance_policies.yaml"
    jurisdictions = tmp_path / "reference" / "jurisdictions.yaml"
    authorities = tmp_path / "reference" / "authorities.yaml"
    extractor_profiles = tmp_path / "reference" / "extractor_profiles.yaml"

    _write_compliance_policies(compliance_policies)
    _write_seed_file(
        jurisdictions,
        {
            "version": 1,
            "items": [
                {
                    "jurisdiction_id": "jur_ch",
                    "slug": "ch",
                    "name": "Switzerland",
                    "level": "federal",
                }
            ],
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


@pytest.mark.asyncio
async def test_seed_attaches_compliance_policy_to_jurisdiction(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    _write_compliance_policies(
        tmp_path / "reference" / "compliance_policies.yaml",
        items=[
            {
                "compliance_policy_id": "cp_ch_fedlex_open_data",
                "name": "ch-fedlex-open-data",
                "robots_mode": "ignore",
                "max_requests_per_minute_per_host": 60,
                "max_concurrent_per_host": 4,
                "attribution_required": True,
                "attribution_text": "Source: Fedlex.",
                "contact_url": "https://evidara.ai/contact",
            }
        ],
    )
    _write_seed_file(
        tmp_path / "reference" / "jurisdictions.yaml",
        {
            "version": 1,
            "items": [
                {
                    "jurisdiction_id": "jur_ch",
                    "slug": "ch",
                    "name": "Switzerland",
                    "level": "federal",
                    "compliance_policy_id": "cp_ch_fedlex_open_data",
                },
                # Unattached jurisdiction stays unconstrained by design.
                {"jurisdiction_id": "jur_de", "slug": "de", "name": "Germany", "level": "federal"},
            ],
        },
    )
    _write_seed_file(tmp_path / "reference" / "authorities.yaml", {"version": 1, "items": []})
    _write_seed_file(
        tmp_path / "reference" / "extractor_profiles.yaml", {"version": 1, "items": []}
    )

    summary = await ReferenceDataSeeder(session_maker).seed(tmp_path, dry_run=False)

    assert summary.created["compliance_policies"] == 1
    assert summary.created["jurisdictions"] == 2

    async with session_maker() as session:
        policy = await session.get(CompliancePolicy, "cp_ch_fedlex_open_data")
        assert policy is not None
        assert policy.max_requests_per_minute_per_host == 60
        assert policy.attribution_required is True

        ch = await session.get(Jurisdiction, "jur_ch")
        de = await session.get(Jurisdiction, "jur_de")
        assert ch is not None
        assert ch.compliance_policy_id == "cp_ch_fedlex_open_data"
        assert de is not None
        assert de.compliance_policy_id is None


@pytest.mark.asyncio
async def test_seed_rejects_jurisdiction_with_missing_policy_reference(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    _write_compliance_policies(tmp_path / "reference" / "compliance_policies.yaml")
    _write_seed_file(
        tmp_path / "reference" / "jurisdictions.yaml",
        {
            "version": 1,
            "items": [
                {
                    "jurisdiction_id": "jur_ch",
                    "slug": "ch",
                    "name": "Switzerland",
                    "level": "federal",
                    "compliance_policy_id": "cp_does_not_exist",
                }
            ],
        },
    )
    _write_seed_file(tmp_path / "reference" / "authorities.yaml", {"version": 1, "items": []})
    _write_seed_file(
        tmp_path / "reference" / "extractor_profiles.yaml", {"version": 1, "items": []}
    )

    with pytest.raises(ValueError, match="missing compliance policy"):
        await ReferenceDataSeeder(session_maker).seed(tmp_path, dry_run=False)


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_seeder_raises_when_authority_alias_row_still_exists(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """The alias-pattern contract: a seed entry that declares a
    deprecated_alias must not silently collide with an existing aliased
    row. The seeder raises AliasedIdRenameRequiredError until a data migration
    has renamed the PK and re-pointed FKs. See issue #264."""
    _write_compliance_policies(tmp_path / "reference" / "compliance_policies.yaml")
    _write_seed_file(
        tmp_path / "reference" / "jurisdictions.yaml",
        {
            "version": 1,
            "items": [
                {
                    "jurisdiction_id": "jur_ch",
                    "slug": "ch",
                    "name": "Switzerland",
                    "level": "federal",
                }
            ],
        },
    )
    # First seed: insert under the old ID.
    _write_seed_file(
        tmp_path / "reference" / "authorities.yaml",
        {
            "version": 1,
            "items": [
                {
                    "authority_id": "auth_old_id",
                    "jurisdiction_id": "jur_ch",
                    "slug": "test-slug",
                    "name": "Test Authority",
                }
            ],
        },
    )
    _write_seed_file(
        tmp_path / "reference" / "extractor_profiles.yaml",
        {"version": 1, "items": []},
    )
    seeder = ReferenceDataSeeder(session_maker)
    await seeder.seed(tmp_path, dry_run=False)

    # Now rewrite seed to declare the new ID + alias, without running a
    # data migration first. The seeder must refuse to proceed.
    _write_seed_file(
        tmp_path / "reference" / "authorities.yaml",
        {
            "version": 1,
            "items": [
                {
                    "authority_id": "auth_new_id",
                    "jurisdiction_id": "jur_ch",
                    "slug": "test-slug",
                    "name": "Test Authority",
                    "deprecated_aliases": ["auth_old_id"],
                }
            ],
        },
    )
    with pytest.raises(AliasedIdRenameRequiredError) as exc_info:
        await seeder.seed(tmp_path, dry_run=False)
    assert exc_info.value.current_id == "auth_old_id"
    assert exc_info.value.target_id == "auth_new_id"
    assert exc_info.value.table == "authorities"


@pytest.mark.asyncio
async def test_seeder_no_ops_when_alias_row_has_already_been_renamed(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """Once the data migration has renamed the row, the alias no longer
    resolves — so the seeder finds the row under the new PK and upserts
    normally. The deprecated_aliases list can stay in the YAML as
    documentation without triggering the guard on every run."""
    _write_compliance_policies(tmp_path / "reference" / "compliance_policies.yaml")
    _write_seed_file(
        tmp_path / "reference" / "jurisdictions.yaml",
        {
            "version": 1,
            "items": [
                {
                    "jurisdiction_id": "jur_ch",
                    "slug": "ch",
                    "name": "Switzerland",
                    "level": "federal",
                }
            ],
        },
    )
    _write_seed_file(
        tmp_path / "reference" / "authorities.yaml",
        {
            "version": 1,
            "items": [
                {
                    "authority_id": "auth_new_id",
                    "jurisdiction_id": "jur_ch",
                    "slug": "test-slug",
                    "name": "Test Authority",
                    "deprecated_aliases": ["auth_old_id"],
                }
            ],
        },
    )
    _write_seed_file(
        tmp_path / "reference" / "extractor_profiles.yaml",
        {"version": 1, "items": []},
    )
    seeder = ReferenceDataSeeder(session_maker)
    first_summary = await seeder.seed(tmp_path, dry_run=False)
    second_summary = await seeder.seed(tmp_path, dry_run=False)

    assert first_summary.created["authorities"] == 1
    assert second_summary.unchanged["authorities"] == 1


@pytest.mark.asyncio
async def test_seeder_raises_when_jurisdiction_alias_row_still_exists(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """Same alias contract, but for jurisdictions."""
    _write_compliance_policies(tmp_path / "reference" / "compliance_policies.yaml")
    _write_seed_file(
        tmp_path / "reference" / "jurisdictions.yaml",
        {
            "version": 1,
            "items": [
                {
                    "jurisdiction_id": "jur_old",
                    "slug": "test",
                    "name": "Test Place",
                    "level": "federal",
                }
            ],
        },
    )
    _write_seed_file(
        tmp_path / "reference" / "authorities.yaml",
        {"version": 1, "items": []},
    )
    _write_seed_file(
        tmp_path / "reference" / "extractor_profiles.yaml",
        {"version": 1, "items": []},
    )
    seeder = ReferenceDataSeeder(session_maker)
    await seeder.seed(tmp_path, dry_run=False)

    _write_seed_file(
        tmp_path / "reference" / "jurisdictions.yaml",
        {
            "version": 1,
            "items": [
                {
                    "jurisdiction_id": "jur_new",
                    "slug": "test",
                    "name": "Test Place",
                    "level": "federal",
                    "deprecated_aliases": ["jur_old"],
                }
            ],
        },
    )
    with pytest.raises(AliasedIdRenameRequiredError) as exc_info:
        await seeder.seed(tmp_path, dry_run=False)
    assert exc_info.value.current_id == "jur_old"
    assert exc_info.value.target_id == "jur_new"
    assert exc_info.value.table == "jurisdictions"


async def test_repo_jurisdictions_and_compliance_policies_are_consistent() -> None:
    """File-level consistency check on the repo's own seed YAMLs.

    Pure YAML load + FK check — avoids the DB path so pre-existing authority
    name collisions (DE vs CH Bundesverwaltungsgericht) don't mask this.
    """
    repo_seed_dir = (
        Path(__file__).resolve().parents[2] / "src" / "platform_control" / "seeds" / "reference"
    )
    policies = yaml.safe_load((repo_seed_dir / "compliance_policies.yaml").read_text())
    jurisdictions = yaml.safe_load((repo_seed_dir / "jurisdictions.yaml").read_text())

    policy_ids = {item["compliance_policy_id"] for item in policies["items"]}
    assert policy_ids, "expected at least one seeded compliance policy"
    for item in jurisdictions["items"]:
        pid = item.get("compliance_policy_id")
        if pid is not None:
            assert pid in policy_ids, (
                f"jurisdiction {item['jurisdiction_id']} references unknown policy {pid}"
            )


def test_repo_jurisdiction_levels_are_declared_and_coherent() -> None:
    """Every seeded jurisdiction declares a level, and no child outranks its parent.

    `level` is what makes a document's rank in the hierarchy of norms derivable
    from its jurisdiction instead of guessed from its text (ADR-0033, #583). A
    missing or inverted level does not fail loudly at request time — it silently
    mis-ranks law, which is the failure mode the whole feature exists to prevent.

    The one legitimate equal-rank parent/child pair is a *scope refinement*:
    `jur_ch_federal` (federal) under `jur_ch` (federal). Equal is allowed;
    outranking a parent is not.
    """
    repo_seed_dir = (
        Path(__file__).resolve().parents[2] / "src" / "platform_control" / "seeds" / "reference"
    )
    jurisdictions = yaml.safe_load((repo_seed_dir / "jurisdictions.yaml").read_text())
    items = jurisdictions["items"]

    levels = {item["jurisdiction_id"]: NormLevel(item["level"]) for item in items}
    by_id = {item["jurisdiction_id"]: item for item in items}

    for item in items:
        parent_id = item.get("parent_id")
        if parent_id is None:
            continue
        assert parent_id in by_id, (
            f"jurisdiction {item['jurisdiction_id']} references unseeded parent {parent_id}"
        )
        child_rank = NORM_LEVEL_RANK[levels[item["jurisdiction_id"]]]
        parent_rank = NORM_LEVEL_RANK[levels[parent_id]]
        assert child_rank >= parent_rank, (
            f"jurisdiction {item['jurisdiction_id']} ({levels[item['jurisdiction_id']]}) "
            f"outranks its parent {parent_id} ({levels[parent_id]})"
        )

    # The demo case: a commune sits under its canton, which sits under the
    # Confederation. If this inverts, the dog question is unanswerable.
    assert levels["jur_ch_gemeinde_261"] is NormLevel.MUNICIPAL
    assert by_id["jur_ch_gemeinde_261"]["parent_id"] == "jur_ch_zh"
    assert levels["jur_ch_zh"] is NormLevel.CANTONAL
    assert levels["jur_ch_federal"] is NormLevel.FEDERAL
