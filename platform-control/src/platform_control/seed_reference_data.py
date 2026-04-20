from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from importlib import resources as importlib_resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.database import get_session_maker
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.extractor_profile import ExtractorProfile
from platform_control.seed_schemas import (
    AuthoritySeed,
    CompliancePolicySeed,
    ExtractorProfileSeed,
    JurisdictionSeed,
    SeedBundle,
    SeedSummary,
)

# Load seeds via importlib.resources so the same code path works in editable
# dev installs and in the production wheel that ships inside
# platform-control's Docker image (see `artifacts` in pyproject.toml).
DEFAULT_SEED_DIR = Path(str(importlib_resources.files("platform_control").joinpath("seeds")))


class AliasedIdRenameRequiredError(RuntimeError):
    """A seed entry declares a deprecated alias that still exists in the DB.

    Renaming a primary-key ID in-place would violate the UNIQUE constraints
    on `slug` / `name` (both columns have them). Seed upserts must therefore
    never silently resolve this collision — the caller runs a data migration
    first, then reseeds. See issue #264 for policy context.
    """

    def __init__(self, *, model_name: str, table: str, current_id: str, target_id: str) -> None:
        self.model_name = model_name
        self.table = table
        self.current_id = current_id
        self.target_id = target_id
        super().__init__(
            f"{model_name} row {current_id!r} is on the deprecated-alias list "
            f"for {target_id!r}. A data migration that renames the primary key "
            f"(and updates FK-referencing rows) must run before reseeding. "
            f"See issue #264 for the alias-pattern policy."
        )


class ReferenceDataSeeder:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self.session_maker = session_maker

    async def seed(self, seed_dir: Path, *, dry_run: bool) -> SeedSummary:
        async with self.session_maker() as session:
            return await self.seed_with_session(session, seed_dir, dry_run=dry_run)

    async def seed_with_session(
        self,
        session: AsyncSession,
        seed_dir: Path,
        *,
        dry_run: bool,
    ) -> SeedSummary:
        """Run the seed upserts against an already-open session.

        Used by HTTP handlers that receive a session via FastAPI dependency
        injection and want to reuse it (so one request maps to one
        transaction). The standalone CLI still calls ``seed()``, which opens
        its own session from ``session_maker``.
        """
        bundles = self._load_seed_bundles(seed_dir)
        counter_keys = (
            "compliance_policies",
            "jurisdictions",
            "authorities",
            "extractor_profiles",
        )
        summary = SeedSummary(
            dry_run=dry_run,
            seed_dir=seed_dir,
            created=dict.fromkeys(counter_keys, 0),
            updated=dict.fromkeys(counter_keys, 0),
            unchanged=dict.fromkeys(counter_keys, 0),
        )

        # Policies land before jurisdictions so jurisdictions.compliance_policy_id
        # resolves its FK on the first run. Jurisdictions without a policy
        # stay unconstrained (absence is the explicit operator signal).
        await self._upsert_compliance_policies(
            session, bundles["compliance_policies"].items, summary
        )
        await self._upsert_jurisdictions(session, bundles["jurisdictions"].items, summary)
        await self._upsert_authorities(session, bundles["authorities"].items, summary)
        await self._upsert_extractor_profiles(
            session,
            bundles["extractor_profiles"].items,
            summary,
        )

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

        return summary

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Seed file must contain a mapping: {path}")
        return data

    def _load_seed_bundles(
        self,
        seed_dir: Path,
    ) -> dict[str, Any]:
        bundle_map: dict[str, tuple[Path, TypeAdapter[Any]]] = {
            "compliance_policies": (
                seed_dir / "reference" / "compliance_policies.yaml",
                TypeAdapter(SeedBundle[CompliancePolicySeed]),
            ),
            "jurisdictions": (
                seed_dir / "reference" / "jurisdictions.yaml",
                TypeAdapter(SeedBundle[JurisdictionSeed]),
            ),
            "authorities": (
                seed_dir / "reference" / "authorities.yaml",
                TypeAdapter(SeedBundle[AuthoritySeed]),
            ),
            "extractor_profiles": (
                seed_dir / "reference" / "extractor_profiles.yaml",
                TypeAdapter(SeedBundle[ExtractorProfileSeed]),
            ),
        }

        loaded: dict[str, Any] = {}
        for name, (path, adapter) in bundle_map.items():
            if not path.exists():
                raise FileNotFoundError(f"Seed file not found: {path}")
            loaded[name] = adapter.validate_python(self._load_yaml(path))
        return loaded

    async def _upsert_compliance_policies(
        self,
        session: AsyncSession,
        items: list[CompliancePolicySeed],
        summary: SeedSummary,
    ) -> None:
        for item in items:
            item_payload = item.model_dump()
            existing = await session.get(CompliancePolicy, item.compliance_policy_id)
            await self._upsert_entity(
                existing=existing,
                create=lambda item_payload=item_payload: CompliancePolicy(**item_payload),
                updates=item.model_dump(exclude={"compliance_policy_id"}),
                session=session,
                summary=summary,
                summary_key="compliance_policies",
            )

    async def _upsert_jurisdictions(
        self,
        session: AsyncSession,
        items: list[JurisdictionSeed],
        summary: SeedSummary,
    ) -> None:
        # parent_id refers to another jurisdiction in the same bundle; the seed
        # file is authored parent-first, so by the time we reach a child the
        # parent is already in this session (session.get resolves it without a
        # flush). If a child lists a parent that wasn't seeded, we raise with
        # the same shape as the compliance-policy check.
        for item in items:
            if item.compliance_policy_id is not None:
                policy = await session.get(CompliancePolicy, item.compliance_policy_id)
                if policy is None:
                    raise ValueError(
                        "Jurisdiction seed references missing compliance policy: "
                        f"{item.jurisdiction_id} -> {item.compliance_policy_id}"
                    )
            if item.parent_id is not None:
                parent = await session.get(Jurisdiction, item.parent_id)
                if parent is None:
                    raise ValueError(
                        "Jurisdiction seed references missing parent: "
                        f"{item.jurisdiction_id} -> {item.parent_id}"
                    )
            existing = await session.get(Jurisdiction, item.jurisdiction_id)
            if existing is None:
                await self._check_alias_collision(
                    session=session,
                    model=Jurisdiction,
                    model_name="Jurisdiction",
                    table="jurisdictions",
                    target_id=item.jurisdiction_id,
                    aliases=item.deprecated_aliases,
                )
            item_payload = self._entity_payload(item, exclude={"deprecated_aliases"})
            await self._upsert_entity(
                existing=existing,
                create=lambda item_payload=item_payload: Jurisdiction(**item_payload),
                updates=self._entity_payload(
                    item, exclude={"jurisdiction_id", "deprecated_aliases"}
                ),
                session=session,
                summary=summary,
                summary_key="jurisdictions",
            )

    async def _upsert_authorities(
        self,
        session: AsyncSession,
        items: list[AuthoritySeed],
        summary: SeedSummary,
    ) -> None:
        for item in items:
            jurisdiction = await session.get(Jurisdiction, item.jurisdiction_id)
            if jurisdiction is None:
                raise ValueError(
                    "Authority seed references missing jurisdiction: "
                    f"{item.authority_id} -> {item.jurisdiction_id}"
                )
            existing = await session.get(Authority, item.authority_id)
            if existing is None:
                await self._check_alias_collision(
                    session=session,
                    model=Authority,
                    model_name="Authority",
                    table="authorities",
                    target_id=item.authority_id,
                    aliases=item.deprecated_aliases,
                )
            item_payload = self._entity_payload(item, exclude={"deprecated_aliases"})
            await self._upsert_entity(
                existing=existing,
                create=lambda item_payload=item_payload: Authority(**item_payload),
                updates=self._entity_payload(item, exclude={"authority_id", "deprecated_aliases"}),
                session=session,
                summary=summary,
                summary_key="authorities",
            )

    async def _upsert_extractor_profiles(
        self,
        session: AsyncSession,
        items: list[ExtractorProfileSeed],
        summary: SeedSummary,
    ) -> None:
        for item in items:
            item_payload = item.model_dump()
            existing = await session.get(ExtractorProfile, item.extractor_profile_id)
            await self._upsert_entity(
                existing=existing,
                create=lambda item_payload=item_payload: ExtractorProfile(**item_payload),
                updates=item.model_dump(exclude={"extractor_profile_id"}),
                session=session,
                summary=summary,
                summary_key="extractor_profiles",
            )

    @staticmethod
    async def _check_alias_collision(
        *,
        session: AsyncSession,
        model: type[Any],
        model_name: str,
        table: str,
        target_id: str,
        aliases: list[str],
    ) -> None:
        """Raise AliasedIdRenameRequiredError if any deprecated alias row exists.

        Prevents silently inserting a new row that would collide with an
        existing aliased row's UNIQUE slug/name. The caller is expected to
        run the matching data migration (rename PK + update FK references),
        after which the alias row will no longer exist and the seeder's
        normal upsert-by-PK path resolves.
        """
        for alias in aliases:
            row = await session.get(model, alias)
            if row is not None:
                raise AliasedIdRenameRequiredError(
                    model_name=model_name,
                    table=table,
                    current_id=alias,
                    target_id=target_id,
                )

    @staticmethod
    def _entity_payload(item: Any, *, exclude: set[str]) -> dict[str, Any]:
        """model_dump with extra fields (like deprecated_aliases) stripped.

        The model class doesn't have a `deprecated_aliases` column — that
        field only lives in the seed schema as metadata for the migration
        policy. Attempting to forward it into the SQLAlchemy constructor
        would raise TypeError.
        """
        return item.model_dump(exclude=exclude)

    @staticmethod
    async def _upsert_entity(
        *,
        existing: Any | None,
        create: Callable[[], Any],
        updates: dict[str, Any],
        session: AsyncSession,
        summary: SeedSummary,
        summary_key: str,
    ) -> None:
        if existing is None:
            session.add(create())
            summary.created[summary_key] += 1
            return

        changed = False
        for field_name, value in updates.items():
            if getattr(existing, field_name) != value:
                setattr(existing, field_name, value)
                changed = True

        if changed:
            summary.updated[summary_key] += 1
        else:
            summary.unchanged[summary_key] += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed platform-control reference data from YAML files."
    )
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=DEFAULT_SEED_DIR,
        help="Directory containing the seed YAML files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report changes without committing them.",
    )
    return parser.parse_args()


async def _run(seed_dir: Path, dry_run: bool) -> SeedSummary:
    seeder = ReferenceDataSeeder(get_session_maker())
    return await seeder.seed(seed_dir=seed_dir, dry_run=dry_run)


def main() -> None:
    args = parse_args()
    summary = asyncio.run(_run(seed_dir=args.seed_dir, dry_run=args.dry_run))
    print(f"Seed directory: {summary.seed_dir}")
    print(f"Dry run: {summary.dry_run}")
    for key in ("compliance_policies", "jurisdictions", "authorities", "extractor_profiles"):
        print(
            f"{key}: created={summary.created[key]} "
            f"updated={summary.updated[key]} unchanged={summary.unchanged[key]}"
        )


if __name__ == "__main__":
    main()
