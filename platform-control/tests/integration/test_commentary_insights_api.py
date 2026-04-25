from __future__ import annotations

import httpx
import pytest

from platform_control.database import get_session
from platform_control.domain import CommentaryInsightReviewState
from platform_control.main import create_app
from platform_control.models.commentary_insight import CommentaryInsight


def _seed_row(**overrides) -> CommentaryInsight:
    base = dict(
        insight_id="ins_01h8x7m6q9n8r2v5y0a3b1c4d6",
        document_id="doc_01h8x7m6q9n8r2v5y0a3b1c4xx",
        document_revision=1,
        processing_manifest_id="pm_01h8x7m6q9n8r2v5y0a3b1c4yy",
        section_id=None,
        citation_id=None,
        insight_type="commentary_anchor",
        claim="Initial claim text.",
        display_text="Initial display passage.",
        support=[{"snippet": "init"}],
        referenced_authorities=[],
        language="en",
        jurisdiction_id="jur_ch",
        authority_id=None,
        confidence=0.8,
        review_state=CommentaryInsightReviewState.MACHINE_GENERATED_UNREVIEWED,
        generator={"name": "di", "version": "0.1"},
        scores={
            "passage_present": 1.0,
            "citation_parseable": 1.0,
            "section_anchor_resolved": 0.0,
        },
    )
    base.update(overrides)
    return CommentaryInsight(**base)


def _build_app(session_maker):
    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    return app


@pytest.mark.asyncio
async def test_list_get_patch_history_flow(session_maker) -> None:
    async with session_maker() as seed_session:
        seed_session.add(_seed_row())
        seed_session.add(
            _seed_row(
                insight_id="ins_01h8x7m6q9n8r2v5y0a3b1c4dz",
                jurisdiction_id="jur_de",
                claim="Other-jurisdiction claim.",
            )
        )
        await seed_session.commit()

    app = _build_app(session_maker)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # --- List, no filter ---
        list_response = await client.get("/v1/commentary-insights")
        assert list_response.status_code == 200, list_response.text
        body = list_response.json()
        assert len(body["data"]) == 2

        # --- List filtered by jurisdiction ---
        filtered = await client.get("/v1/commentary-insights", params={"jurisdiction_id": "jur_ch"})
        assert filtered.status_code == 200
        assert len(filtered.json()["data"]) == 1
        assert filtered.json()["data"][0]["insight_id"] == "ins_01h8x7m6q9n8r2v5y0a3b1c4d6"

        # --- Get ---
        get_response = await client.get("/v1/commentary-insights/ins_01h8x7m6q9n8r2v5y0a3b1c4d6")
        assert get_response.status_code == 200
        original = get_response.json()
        assert original["claim"] == "Initial claim text."
        assert original["current_version"] == 1

        # --- Patch ---
        patch_response = await client.patch(
            "/v1/commentary-insights/ins_01h8x7m6q9n8r2v5y0a3b1c4d6",
            json={
                "operator_id": "op_alice",
                "rationale": "fix typo",
                "patch": {"claim": "Updated claim text."},
                "original_snapshot": {"claim": "Initial claim text."},
            },
        )
        assert patch_response.status_code == 200, patch_response.text
        patched = patch_response.json()
        assert patched["claim"] == "Updated claim text."
        assert patched["current_version"] == 2
        assert patched["last_correction_id"] is not None

        # --- History ---
        history_response = await client.get(
            "/v1/commentary-insights/ins_01h8x7m6q9n8r2v5y0a3b1c4d6/history"
        )
        assert history_response.status_code == 200
        history = history_response.json()["data"]
        assert len(history) == 1
        assert history[0]["correction_type"] == "field_edit"
        assert history[0]["status"] == "applied"
        assert history[0]["operator_id"] == "op_alice"
        assert history[0]["payload"] == {"claim": "Updated claim text."}


@pytest.mark.asyncio
async def test_patch_with_stale_snapshot_returns_409(session_maker) -> None:
    async with session_maker() as seed_session:
        seed_session.add(_seed_row())
        await seed_session.commit()

    app = _build_app(session_maker)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            "/v1/commentary-insights/ins_01h8x7m6q9n8r2v5y0a3b1c4d6",
            json={
                "operator_id": "op_alice",
                "patch": {"claim": "Updated claim text."},
                "original_snapshot": {"claim": "Stale value the operator never saw."},
            },
        )
        assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_patch_unknown_insight_returns_404(session_maker) -> None:
    app = _build_app(session_maker)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            "/v1/commentary-insights/ins_doesnotexist",
            json={
                "operator_id": "op_alice",
                "patch": {"claim": "x"},
                "original_snapshot": {"claim": "y"},
            },
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_with_unsupported_field_returns_422(session_maker) -> None:
    async with session_maker() as seed_session:
        seed_session.add(_seed_row())
        await seed_session.commit()

    app = _build_app(session_maker)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            "/v1/commentary-insights/ins_01h8x7m6q9n8r2v5y0a3b1c4d6",
            json={
                "operator_id": "op_alice",
                "patch": {"document_id": "doc_other"},
                "original_snapshot": {"document_id": "doc_x"},
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_history_for_unknown_insight_returns_404(session_maker) -> None:
    app = _build_app(session_maker)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/commentary-insights/ins_doesnotexist/history")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_correction_queue_lists_pending_and_applied(session_maker) -> None:
    async with session_maker() as seed_session:
        seed_session.add(_seed_row())
        await seed_session.commit()

    app = _build_app(session_maker)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Apply a patch to seed an applied correction.
        await client.patch(
            "/v1/commentary-insights/ins_01h8x7m6q9n8r2v5y0a3b1c4d6",
            json={
                "operator_id": "op_alice",
                "patch": {"claim": "Updated."},
                "original_snapshot": {"claim": "Initial claim text."},
            },
        )

        pending = await client.get("/v1/corrections/queue")
        assert pending.status_code == 200
        assert pending.json()["data"] == []

        applied = await client.get("/v1/corrections/queue", params={"status": "applied"})
        assert applied.status_code == 200
        applied_rows = applied.json()["data"]
        assert len(applied_rows) == 1
        assert applied_rows[0]["correction_type"] == "field_edit"
        assert applied_rows[0]["target_entity_type"] == "commentary_insight"

        # Filter by entity type and correction type.
        filtered = await client.get(
            "/v1/corrections/queue",
            params={
                "status": "applied",
                "target_entity_type": "commentary_insight",
                "correction_type": "field_edit",
            },
        )
        assert filtered.status_code == 200
        assert len(filtered.json()["data"]) == 1

        # Wrong correction_type filter — should be empty.
        empty = await client.get(
            "/v1/corrections/queue",
            params={"status": "applied", "correction_type": "annotation"},
        )
        assert empty.status_code == 200
        assert empty.json()["data"] == []
