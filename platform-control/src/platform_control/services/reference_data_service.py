from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.schemas.reference_data import (
    CreateAuthorityRequest,
    CreateJurisdictionRequest,
    UpdateAuthorityRequest,
    UpdateJurisdictionRequest,
)


class ReferenceDataService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_jurisdictions(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        q: str | None = None,
    ) -> tuple[list[Jurisdiction], int]:
        """Return one page of jurisdictions and the total hit count.

        Paginated since #616: 2,169 jurisdictions are seeded today and the
        municipal work in #584 adds 2,110 Gemeinden, so serving the whole table
        on every admin list render is neither cheap nor bounded. Mirrors
        ``SourceService.list_sources``.
        """
        base = select(Jurisdiction).order_by(Jurisdiction.name.asc())
        if q:
            base = base.where(Jurisdiction.name.ilike(f"%{q}%"))
        count_result = await self.session.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar() or 0
        result = await self.session.scalars(base.limit(limit).offset(offset))
        return list(result), total

    async def create_jurisdiction(self, request: CreateJurisdictionRequest) -> Jurisdiction:
        jurisdiction = Jurisdiction(name=request.name, slug=request.slug)
        self.session.add(jurisdiction)
        await self.session.commit()
        await self.session.refresh(jurisdiction)
        return jurisdiction

    async def update_jurisdiction(
        self,
        jurisdiction_id: str,
        request: UpdateJurisdictionRequest,
    ) -> Jurisdiction:
        jurisdiction = await self.session.get(Jurisdiction, jurisdiction_id)
        if jurisdiction is None:
            raise NotFoundError(f"Jurisdiction not found: {jurisdiction_id}")

        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(jurisdiction, field, value)

        await self.session.commit()
        await self.session.refresh(jurisdiction)
        return jurisdiction

    async def list_authorities(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        q: str | None = None,
    ) -> tuple[list[Authority], int]:
        """Return one page of authorities and the total hit count. See #616."""
        base = select(Authority).order_by(Authority.name.asc())
        if q:
            base = base.where(Authority.name.ilike(f"%{q}%"))
        count_result = await self.session.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar() or 0
        result = await self.session.scalars(base.limit(limit).offset(offset))
        return list(result), total

    async def create_authority(self, request: CreateAuthorityRequest) -> Authority:
        if request.jurisdiction_id is not None:
            await self._require_jurisdiction(request.jurisdiction_id)

        authority = Authority(
            jurisdiction_id=request.jurisdiction_id,
            name=request.name,
            slug=request.slug,
        )
        self.session.add(authority)
        await self.session.commit()
        await self.session.refresh(authority)
        return authority

    async def update_authority(
        self,
        authority_id: str,
        request: UpdateAuthorityRequest,
    ) -> Authority:
        authority = await self.session.get(Authority, authority_id)
        if authority is None:
            raise NotFoundError(f"Authority not found: {authority_id}")

        payload = request.model_dump(exclude_unset=True)
        if "jurisdiction_id" in payload and payload["jurisdiction_id"] is not None:
            await self._require_jurisdiction(payload["jurisdiction_id"])

        for field, value in payload.items():
            setattr(authority, field, value)

        await self.session.commit()
        await self.session.refresh(authority)
        return authority

    async def _require_jurisdiction(self, jurisdiction_id: str) -> Jurisdiction:
        jurisdiction = await self.session.get(Jurisdiction, jurisdiction_id)
        if jurisdiction is None:
            raise NotFoundError(f"Jurisdiction not found: {jurisdiction_id}")
        return jurisdiction
