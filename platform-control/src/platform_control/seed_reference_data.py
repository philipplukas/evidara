from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
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

DEFAULT_SEED_DIR = Path(__file__).resolve().parents[2] / "seeds"


class ReferenceDataSeeder:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self.session_maker = session_maker

    async def seed(self, seed_dir: Path, *, dry_run: bool) -> SeedSummary:
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

        async with self.session_maker() as session:
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
        for item in items:
            if item.compliance_policy_id is not None:
                policy = await session.get(CompliancePolicy, item.compliance_policy_id)
                if policy is None:
                    raise ValueError(
                        "Jurisdiction seed references missing compliance policy: "
                        f"{item.jurisdiction_id} -> {item.compliance_policy_id}"
                    )
            item_payload = item.model_dump()
            existing = await session.get(Jurisdiction, item.jurisdiction_id)
            await self._upsert_entity(
                existing=existing,
                create=lambda item_payload=item_payload: Jurisdiction(**item_payload),
                updates=item.model_dump(exclude={"jurisdiction_id"}),
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
            item_payload = item.model_dump()
            existing = await session.get(Authority, item.authority_id)
            await self._upsert_entity(
                existing=existing,
                create=lambda item_payload=item_payload: Authority(**item_payload),
                updates=item.model_dump(exclude={"authority_id"}),
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
