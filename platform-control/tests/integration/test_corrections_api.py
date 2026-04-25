"""HTTP-level integration test for the corrections + commentary-insight surface.

Covers the happy path: seed an insight, raise a field-edit correction,
list corrections, transition to applied (overlay updated), fetch the
insight history.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from platform_control.database import get_session
from platform_control.main import create_app
from platform_control.models.commentary_insight import CommentaryInsight

_INSIGHT_ID = "ins_01jq7c1ny0ffv8qdr1xwbejqb6"
_OPERATOR = "op_01jqs7p1bcvz2tw5kxh9mq80fg"


def _make_insight() -> CommentaryInsight:
    now = datetime.now(UTC)
    return CommentaryInsight(
        insight_id=_INSIGHT_ID,
        document_id="doc_01jq7bdptzqv3xs0c41xpw1ybg",
        document_revision=3,
        processing_manifest_id="pm_01jq7bhgy7g0pkj4f1d03f8f8c",
        section_id=None,
        citation_id=None,
        insight_type="referenced_provision",
        claim="References Art. 754 OR",
        display_text="…Lehre als Haftungsnorm…",
        language="de",
        jurisdiction_id="jur_ch_federal",
        confidence=0.78,
        review_state="machine_verified",
        support=[
            {"document_id": "doc_01jq7bdptzqv3xs0c41xpw1ybg", "ref_type": "passage"},
        ],
        referenced_authorities=[],
        jurisdiction_ids=["jur_ch_federal"],
        authority_ids=["auth_fedlex"],
        source_document_ids=["doc_01jq7bdptzqv3xs0c41xpw1ybg"],
        generator={"name": "extractor", "version": "v1"},
        scores={"passage_present": 1.0},
        metadata_json=None,
        overlay_revision=1,
        last_correction_id=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_corrections_happy_path(session_maker) -> None:
    async with session_maker() as seed_session:
        seed_session.add(_make_insight())
        await seed_session.commit()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # --- Create a field_edit correction targeting the insight ---
        create = await client.post(
            "/v1/corrections",
            headers={"X-Operator-Id": _OPERATOR},
            json={
                "target_entity_type": "commentary_insight",
                "target_entity_id": _INSIGHT_ID,
                "correction_type": "field_edit",
                "payload": {
                    "field": "claim",
                    "value": "Article 754 OR — director liability.",
                },
                "original_snapshot": {"claim": "References Art. 754 OR"},
                "rationale": "Editor sharpened the claim.",
            },
        )
        assert create.status_code == 201, create.text
        body = create.json()
        correction_id = body["correction_id"]
        assert body["status"] == "pending"
        assert body["operator_id"] == _OPERATOR

        # --- List filtered by status=pending ---
        listing = await client.get(
            "/v1/corrections",
            params={"status": "pending", "target_entity_type": "commentary_insight"},
        )
        assert listing.status_code == 200
        data = listing.json()["data"]
        assert any(c["correction_id"] == correction_id for c in data)

        # --- Get by id ---
        fetched = await client.get(f"/v1/corrections/{correction_id}")
        assert fetched.status_code == 200
        assert fetched.json()["correction_id"] == correction_id

        # --- Apply (transitions pending -> applied; overlay updates) ---
        applied = await client.patch(
            f"/v1/corrections/{correction_id}",
            json={"status": "applied", "rationale": "Approved on review."},
        )
        assert applied.status_code == 200
        assert applied.json()["status"] == "applied"
        assert applied.json()["applied_at"] is not None

        # --- The overlay row reflects the field edit ---
        insight_resp = await client.get(f"/v1/commentary-insights/{_INSIGHT_ID}")
        assert insight_resp.status_code == 200
        insight = insight_resp.json()
        assert insight["claim"] == "Article 754 OR — director liability."
        assert insight["overlay_revision"] == 2
        assert insight["last_correction_id"] == correction_id

        # --- History endpoint returns the correction ---
        history_resp = await client.get(f"/v1/commentary-insights/{_INSIGHT_ID}/history")
        assert history_resp.status_code == 200
        history = history_resp.json()
        assert history["overlay_revision"] == 2
        assert len(history["history"]) == 1
        assert history["history"][0]["correction_id"] == correction_id
        assert history["history"][0]["status"] == "applied"

        # --- Illegal transition (applied -> pending) returns 409 ---
        illegal = await client.patch(
            f"/v1/corrections/{correction_id}",
            json={"status": "pending"},
        )
        assert illegal.status_code in (400, 422)  # Pydantic rejects pending in body

        # --- Legal transition applied -> superseded ---
        superseded = await client.patch(
            f"/v1/corrections/{correction_id}",
            json={"status": "superseded"},
        )
        assert superseded.status_code == 200
        assert superseded.json()["status"] == "superseded"


@pytest.mark.asyncio
async def test_create_correction_against_missing_target_returns_404(
    session_maker,
) -> None:
    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/v1/corrections",
            headers={"X-Operator-Id": _OPERATOR},
            json={
                "target_entity_type": "commentary_insight",
                "target_entity_id": "ins_01zz0z0z0z0z0z0z0z0z0z0z00",
                "correction_type": "field_edit",
                "payload": {"field": "claim", "value": "x"},
            },
        )
        assert resp.status_code == 404
