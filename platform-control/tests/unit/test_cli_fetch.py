from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from platform_control.cli.fetch import record_cassette
from platform_control.cli.ingest import load_payloads
from platform_control.domain import ExecutionMode, SourceVersionStatus
from platform_control.errors import NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import (
    ProviderResource,
    ProviderStartResult,
)


class _CannedProvider:
    provider_name = "deterministic_http"

    def __init__(self, resources: list[ProviderResource]) -> None:
        self._resources = resources
        self.calls: list[tuple[Any, Any, Any]] = []

    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        self.calls.append((source, source_version, run))
        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"canned_{run.run_id}",
            request_payload={"seed_urls": [r.source_url for r in self._resources]},
            response_payload={"captured": len(self._resources)},
            inline_resources=self._resources,
        )

    def plan(self, source, source_version):  # pragma: no cover - not exercised here
        raise NotImplementedError


async def _seed_version(session, *, execution_mode: ExecutionMode = ExecutionMode.LIVE) -> str:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    source = Source(
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    session.add(source)
    await session.flush()
    version = SourceVersion(
        source_id=source.source_id,
        version_label="v1",
        status=SourceVersionStatus.APPROVED,
        execution_mode=execution_mode,
        acquisition_spec={
            "provider": "deterministic_http",
            "seed_urls": ["https://example.com/a"],
        },
    )
    session.add(version)
    await session.commit()
    return version.source_version_id


@pytest.mark.asyncio
async def test_record_writes_cassette_that_ingest_can_load(session, tmp_path: Path) -> None:
    source_version_id = await _seed_version(session)
    provider = _CannedProvider(
        [
            ProviderResource(
                source_url="https://example.com/a",
                final_url="https://example.com/a",
                content_type="text/html",
                body="<html>hello</html>",
                title="Hello",
                http_status=200,
                metadata={"provider": "deterministic_http"},
            )
        ]
    )

    cassette_path, result = await record_cassette(
        session=session,
        provider=provider,
        source_version_id=source_version_id,
        cassette_dir=tmp_path,
    )

    assert cassette_path.exists()
    assert cassette_path.name == f"{source_version_id}.json"
    assert len(result.inline_resources) == 1
    contents = json.loads(cassette_path.read_text())
    assert contents["provider_name"] == "deterministic_http"
    assert contents["inline_resources"][0]["title"] == "Hello"
    # The cassette is well-formed for CassetteProvider on replay.
    assert isinstance(contents["inline_resources"][0]["body"], str)


@pytest.mark.asyncio
async def test_record_refuses_shadow_source_version(session, tmp_path: Path) -> None:
    source_version_id = await _seed_version(session, execution_mode=ExecutionMode.SHADOW)
    provider = _CannedProvider([])

    with pytest.raises(ValueError, match="shadow mode"):
        await record_cassette(
            session=session,
            provider=provider,
            source_version_id=source_version_id,
            cassette_dir=tmp_path,
        )


@pytest.mark.asyncio
async def test_record_raises_when_version_missing(session, tmp_path: Path) -> None:
    provider = _CannedProvider([])

    with pytest.raises(NotFoundError):
        await record_cassette(
            session=session,
            provider=provider,
            source_version_id="sv_missing",
            cassette_dir=tmp_path,
        )


@pytest.mark.asyncio
async def test_cassette_is_loadable_by_ingest_loader_shape(session, tmp_path: Path) -> None:
    """Sanity check the on-disk JSON is well-formed for downstream tooling."""
    source_version_id = await _seed_version(session)
    provider = _CannedProvider(
        [
            ProviderResource(
                source_url="https://example.com/x",
                final_url="https://example.com/x",
                content_type="text/html",
                body="<p>x</p>",
            )
        ]
    )
    cassette_path, _ = await record_cassette(
        session=session,
        provider=provider,
        source_version_id=source_version_id,
        cassette_dir=tmp_path,
    )

    # load_payloads is agnostic about shape beyond "dict or list of dicts"; this
    # asserts the cassette parses cleanly for the general-purpose loader and
    # surfaces the recorded top-level object.
    loaded = load_payloads(cassette_path)
    assert len(loaded) == 1
    assert loaded[0]["provider_name"] == "deterministic_http"
