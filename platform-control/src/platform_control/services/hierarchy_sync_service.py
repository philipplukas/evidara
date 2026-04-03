from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.scrape_target import ScrapeTarget


class HierarchyBundle[TItem: BaseModel](BaseModel):
    version: int
    items: list[TItem]

    model_config = ConfigDict(extra="forbid")


class JurisdictionHierarchyItem(BaseModel):
    jurisdiction_id: str
    path: str
    slug: str
    name: str

    model_config = ConfigDict(extra="forbid")


class AuthorityHierarchyItem(BaseModel):
    authority_id: str
    jurisdiction_path: str
    path: str
    slug: str
    name: str

    model_config = ConfigDict(extra="forbid")


class ScrapeTargetItem(BaseModel):
    scrape_target_id: str
    authority_path: str
    path: str
    enabled: bool = True
    selector: dict[str, Any]

    model_config = ConfigDict(extra="forbid")


@dataclass(slots=True)
class SyncCounts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0


@dataclass(slots=True)
class HierarchySyncSummary:
    jurisdictions: SyncCounts
    authorities: SyncCounts
    scrape_targets: SyncCounts


class HierarchySyncService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def sync(self, hierarchy_dir: Path, *, dry_run: bool = False) -> HierarchySyncSummary:
        jurisdiction_bundle = TypeAdapter(
            HierarchyBundle[JurisdictionHierarchyItem]
        ).validate_python(self._load_yaml(hierarchy_dir / "jurisdictions.yaml"))
        authority_bundle = TypeAdapter(HierarchyBundle[AuthorityHierarchyItem]).validate_python(
            self._load_yaml(hierarchy_dir / "authorities.yaml")
        )
        scrape_bundle = TypeAdapter(HierarchyBundle[ScrapeTargetItem]).validate_python(
            self._load_yaml(hierarchy_dir / "scraping.yaml")
        )

        summary = HierarchySyncSummary(
            jurisdictions=SyncCounts(),
            authorities=SyncCounts(),
            scrape_targets=SyncCounts(),
        )

        await self._sync_jurisdictions(jurisdiction_bundle.items, summary.jurisdictions)
        await self._sync_authorities(authority_bundle.items, summary.authorities)
        await self._sync_scrape_targets(scrape_bundle.items, summary.scrape_targets)
        if dry_run:
            await self.session.rollback()
        else:
            await self.session.commit()
        return summary

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Hierarchy file not found: {path}")
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Hierarchy file must contain a mapping: {path}")
        return payload

    async def _sync_jurisdictions(
        self, items: list[JurisdictionHierarchyItem], counts: SyncCounts
    ) -> None:
        for item in sorted(items, key=lambda x: x.path.count("/")):
            parent_path = self._parent_path(item.path)
            parent_id: str | None = None
            if parent_path is not None:
                parent = await self.session.scalar(
                    select(Jurisdiction).where(Jurisdiction.path == parent_path)
                )
                if parent is None:
                    raise ValueError(f"Missing parent jurisdiction path: {parent_path}")
                parent_id = parent.jurisdiction_id

            existing = await self.session.scalar(
                select(Jurisdiction).where(Jurisdiction.path == item.path)
            )
            if existing is None:
                existing = await self.session.get(Jurisdiction, item.jurisdiction_id)

            expected_depth = item.path.count("/")
            if existing is None:
                self.session.add(
                    Jurisdiction(
                        jurisdiction_id=item.jurisdiction_id,
                        parent_id=parent_id,
                        path=item.path,
                        depth=expected_depth,
                        slug=item.slug,
                        name=item.name,
                    )
                )
                counts.created += 1
                continue

            changed = False
            changed |= self._assign_if_different(existing, "parent_id", parent_id)
            changed |= self._assign_if_different(existing, "path", item.path)
            changed |= self._assign_if_different(existing, "depth", expected_depth)
            changed |= self._assign_if_different(existing, "slug", item.slug)
            changed |= self._assign_if_different(existing, "name", item.name)

            if changed:
                counts.updated += 1
            else:
                counts.unchanged += 1

    async def _sync_authorities(
        self, items: list[AuthorityHierarchyItem], counts: SyncCounts
    ) -> None:
        for item in sorted(items, key=lambda x: x.path.count("/")):
            jurisdiction = await self.session.scalar(
                select(Jurisdiction).where(Jurisdiction.path == item.jurisdiction_path)
            )
            if jurisdiction is None:
                raise ValueError(
                    f"Authority references unknown jurisdiction_path: {item.jurisdiction_path}"
                )

            parent_path = self._parent_path(item.path)
            parent_id: str | None = None
            if parent_path is not None:
                parent = await self.session.scalar(
                    select(Authority).where(Authority.path == parent_path)
                )
                if parent is not None:
                    parent_id = parent.authority_id

            existing = await self.session.scalar(
                select(Authority).where(Authority.path == item.path)
            )
            if existing is None:
                existing = await self.session.get(Authority, item.authority_id)

            expected_depth = item.path.count("/")
            if existing is None:
                self.session.add(
                    Authority(
                        authority_id=item.authority_id,
                        jurisdiction_id=jurisdiction.jurisdiction_id,
                        parent_id=parent_id,
                        path=item.path,
                        depth=expected_depth,
                        slug=item.slug,
                        name=item.name,
                    )
                )
                counts.created += 1
                continue

            changed = False
            changed |= self._assign_if_different(
                existing, "jurisdiction_id", jurisdiction.jurisdiction_id
            )
            changed |= self._assign_if_different(existing, "parent_id", parent_id)
            changed |= self._assign_if_different(existing, "path", item.path)
            changed |= self._assign_if_different(existing, "depth", expected_depth)
            changed |= self._assign_if_different(existing, "slug", item.slug)
            changed |= self._assign_if_different(existing, "name", item.name)

            if changed:
                counts.updated += 1
            else:
                counts.unchanged += 1

    async def _sync_scrape_targets(self, items: list[ScrapeTargetItem], counts: SyncCounts) -> None:
        for item in sorted(items, key=lambda x: x.path):
            authority = await self.session.scalar(
                select(Authority).where(Authority.path == item.authority_path)
            )
            if authority is None:
                raise ValueError(
                    f"Scrape target references unknown authority_path: {item.authority_path}"
                )

            existing = await self.session.scalar(
                select(ScrapeTarget).where(ScrapeTarget.path == item.path)
            )
            if existing is None:
                existing = await self.session.get(ScrapeTarget, item.scrape_target_id)

            expected_depth = item.path.count("/")
            if existing is None:
                self.session.add(
                    ScrapeTarget(
                        scrape_target_id=item.scrape_target_id,
                        path=item.path,
                        depth=expected_depth,
                        jurisdiction_id=authority.jurisdiction_id,
                        authority_id=authority.authority_id,
                        selector=item.selector,
                        enabled=item.enabled,
                    )
                )
                counts.created += 1
                continue

            changed = False
            changed |= self._assign_if_different(existing, "path", item.path)
            changed |= self._assign_if_different(existing, "depth", expected_depth)
            changed |= self._assign_if_different(
                existing, "jurisdiction_id", authority.jurisdiction_id
            )
            changed |= self._assign_if_different(existing, "authority_id", authority.authority_id)
            changed |= self._assign_if_different(existing, "selector", item.selector)
            changed |= self._assign_if_different(existing, "enabled", item.enabled)

            if changed:
                counts.updated += 1
            else:
                counts.unchanged += 1

    @staticmethod
    def _parent_path(path: str) -> str | None:
        if "/" not in path:
            return None
        return path.rsplit("/", 1)[0]

    @staticmethod
    def _assign_if_different(entity: Any, field_name: str, value: Any) -> bool:
        if getattr(entity, field_name) == value:
            return False
        setattr(entity, field_name, value)
        return True
