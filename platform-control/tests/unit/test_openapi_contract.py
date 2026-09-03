"""The invariants that make contracts/api/platform-control.openapi.yaml generatable.

The contract is an export of this app's `/openapi.json` (#618). These tests guard
the properties that export depends on — the ones a normal code change could break
silently, leaving the drift gate to fail with a confusing diff instead of a
sentence.

The drift gate itself (generated == committed) lives in
scripts/check-platform-control.sh, because it compares a file, not behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from platform_control.main import create_app
from platform_control.openapi import API_VERSION

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "contracts" / "manifest.yaml"


@pytest.fixture(scope="module")
def schema() -> dict:
    return create_app().openapi()


def test_operation_ids_are_unique(schema: dict) -> None:
    """Two endpoint functions sharing a name silently collide into one operationId.

    `generate_operation_id` derives the operationId from the function name alone,
    which is what keeps them client-friendly (`getRun`, not
    `get_run_v1_runs__run_id__get`). The cost is that the name must be unique
    across every router — `wizard.get_run` and `runs.get_run` once were not.
    """
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            operation_id = operation["operationId"]
            where = f"{method.upper()} {path}"
            if operation_id in seen:
                duplicates.append(f"{operation_id}: {seen[operation_id]} and {where}")
            seen[operation_id] = where
    assert not duplicates, (
        "Duplicate operationIds — rename the endpoint function so its name is unique:\n  "
        + "\n  ".join(duplicates)
    )


def test_operation_ids_are_camel_case(schema: dict) -> None:
    """Clients generated from the contract get these as method names."""
    offenders = [
        operation["operationId"]
        for operations in schema["paths"].values()
        for operation in operations.values()
        if "_" in operation["operationId"] or not operation["operationId"][0].islower()
    ]
    assert not offenders, f"operationIds must be camelCase: {offenders}"


def test_info_version_matches_contract_manifest(schema: dict) -> None:
    """The app, the contract and the manifest declare one version or none.

    scripts/check_contract_manifest.py compares the manifest to the *generated
    file*; this compares it to the *app*, so a version bump that misses one of
    the two fails here rather than in a CI job that only runs on contract diffs.
    """
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    declared = manifest["apis"]["platform_control"]["version"]
    assert schema["info"]["version"] == API_VERSION == declared, (
        "platform_control.openapi.API_VERSION and contracts/manifest.yaml "
        "apis.platform_control.version must be bumped together."
    )


def test_every_acquisition_provider_is_a_contract_variant(schema: dict) -> None:
    """The drift that caused #614: the contract knew 4 of 11 providers.

    The admin's version editor coerced the 7 it could not see into `firecrawl`,
    nulling their fields and persisting the damage with a 200. #617 could not fix
    that by generating from the contract, because the contract was the thing that
    was wrong. This asserts the union in the contract is the enum in the domain —
    so a new provider that never reaches the contract fails here.
    """
    from platform_control.domain import AcquisitionProvider

    mapping = schema["components"]["schemas"]["SourceVersionResponse"]["properties"][
        "acquisition_spec"
    ]["discriminator"]["mapping"]
    assert set(mapping) == {provider.value for provider in AcquisitionProvider}


#: List responses whose endpoints paginate. Not all of them do — `GET
#: /v1/sources/{source_id}/versions` returns every row — and the contract says so
#: per endpoint instead of implying one rule.
#:
#: The reference-data lists joined this set in #616. They were the remaining half
#: of that issue: unbounded, so the admin fetched all 2,169 jurisdictions on
#: every list render and reported the page length as the count.
PAGINATED_LIST_RESPONSES = {
    "AcquisitionCoverageListResponse",
    "AuthorityListResponse",
    "CapturedResourceListResponse",
    "CommentaryInsightListResponse",
    "CorpusListResponse",
    "CorrectionListResponse",
    "JurisdictionListResponse",
    "ProviderJobListResponse",
    "RawArtifactListResponse",
    "RunListResponse",
    "SourceListResponse",
}


def test_paginated_list_responses_document_their_envelope(schema: dict) -> None:
    """The drift that caused #616.

    The contract documented list responses as a bare `data` array. The paginated
    ones really carry `{data, limit, offset, total}`, so the admin concluded the
    arrays were unbounded, paginated client-side, and capped every list at 100.
    """
    schemas = schema["components"]["schemas"]
    for name in sorted(PAGINATED_LIST_RESPONSES):
        properties = set(schemas[name].get("properties", {}))
        missing = {"data", "limit", "offset", "total"} - properties
        assert not missing, f"{name} does not document {sorted(missing)}"


def test_no_list_response_documents_half_an_envelope(schema: dict) -> None:
    """A list response either paginates or it does not.

    `limit` without `total` is the shape that misleads a client into believing it
    has seen everything — which is the #616 failure told from the other side. This
    also catches a new paginated list that was never added to
    `PAGINATED_LIST_RESPONSES` above.
    """
    schemas = schema["components"]["schemas"]
    envelope = {"limit", "offset", "total"}
    for name in sorted(n for n in schemas if n.endswith("ListResponse")):
        present = envelope & set(schemas[name].get("properties", {}))
        expected = envelope if name in PAGINATED_LIST_RESPONSES else set()
        assert present == expected, (
            f"{name} documents {sorted(present)}; expected {sorted(expected)}. "
            "Either the endpoint paginates and must expose the whole envelope, or it "
            "does not and must expose none of it."
        )


#: The 4xx/5xx each operation can actually produce, keyed by operationId.
#:
#: `main.py` maps the domain errors to status codes centrally (NotFoundError ->
#: 404, ConflictError/InvalidStateTransitionError -> 409,
#: SignatureVerificationError -> 401, WebhookRetryableError -> 503, every other
#: PlatformControlError -> 400), but the *routes* have to declare them: the
#: contract is an export of this app, and an export cannot invent a response the
#: route never declared. That is #627 — ~45 operations silently stopped
#: documenting errors the hand-written spec used to list.
#:
#: Absence is a claim too. An operation missing here claims it cannot fail with a
#: domain error: `GET /v1/sources` cannot 404, `GET /v1/runs/readiness` reports an
#: unknown source as a failed *check* rather than a 404, and `POST /v1/schedules`
#: validates no foreign key. Adding a code that cannot happen is the same class of
#: lie as omitting one that can — see #618.
#:
#: 422 is excluded: FastAPI documents it from the request models.
EXPECTED_ERROR_RESPONSES = {
    "approveSourceVersion": {"404", "409"},
    "approveWizardRun": {"400", "404", "409"},
    "archiveCorpus": {"404"},
    "attachCompliancePolicy": {"404"},
    "cancelRun": {"404", "409"},
    "createAuthority": {"404"},
    "createCorpus": {"409"},
    "createCorrection": {"404"},
    "createReviewTask": {"404", "409"},
    "createRun": {"400", "404", "409"},
    "createSource": {"404", "409"},
    "createSourceVersion": {"404", "409"},
    "createSourceWithInitialVersion": {"404", "409"},
    "detachCompliancePolicy": {"404"},
    "deleteSchedule": {"404"},
    "getCommentaryInsight": {"404"},
    "getCommentaryInsightHistory": {"404"},
    "getCompliancePolicy": {"404"},
    "getCorpus": {"404"},
    "getCorrection": {"404"},
    "getReadiness": {"503"},
    "getReviewTask": {"404"},
    "getRun": {"404"},
    "getRunLifecycle": {"404"},
    "getRunPipelineHealth": {"404"},
    "getRunPreviewSummary": {"404"},
    "getSchedule": {"404"},
    "getSource": {"404"},
    "getWizardProject": {"404"},
    "getWizardRun": {"404"},
    "listRunCapturedResources": {"404"},
    "listRunDocumentLifecycle": {"404"},
    "listRunProcessingStatus": {"404"},
    "listRunProviderJobs": {"404"},
    "listRunRawArtifacts": {"404"},
    "listSourceVersions": {"404"},
    "previewSourceBlueprint": {"404", "409"},
    "receiveDocumentProcessed": {"400"},
    "receiveDocumentProcessingStatusUpdated": {"400"},
    "receiveDocumentWithdrawn": {"400"},
    "receiveFirecrawlWebhook": {"401", "503"},
    "recordReviewDecision": {"404", "409"},
    "rejectSourceVersion": {"404", "409"},
    "rejectWizardRun": {"400", "404", "409"},
    # 404 unknown run; 409 the run is not in a terminal state, or its project
    # has no discovery plan to restart from (#560).
    "restartWizardRun": {"404", "409"},
    "retryRun": {"400", "404", "409"},
    "saveWizardDiscoveryPlan": {"404", "409"},
    "saveWizardScope": {"404", "409"},
    "setBlueprintTemplateEnablement": {"404"},
    "slackInteraction": {"400"},
    "startWizardPilotRun": {"400", "404", "409"},
    "triggerRescoreFromCorrection": {"404", "409"},
    "updateAuthority": {"404"},
    "updateCompliancePolicy": {"404", "409"},
    "updateCorpus": {"404", "409"},
    "updateCorrectionStatus": {"404", "409"},
    "updateJurisdiction": {"404"},
    "updateSchedule": {"404"},
    "updateSourceVersion": {"404", "409"},
}

#: `GET /ready` answers 503 with the readiness *report* (`status: degraded`), not
#: an error body — it is a health verdict, not a raised exception.
NON_ERROR_BODY_RESPONSES = {("getReadiness", "503")}

_DOMAIN_ERROR_CODES = {"400", "401", "403", "404", "409", "500", "503"}


def _declared_error_codes(schema: dict) -> dict[str, set[str]]:
    return {
        operation["operationId"]: {
            code for code in operation["responses"] if code in _DOMAIN_ERROR_CODES
        }
        for operations in schema["paths"].values()
        for operation in operations.values()
    }


def test_routes_declare_the_errors_their_handlers_return(schema: dict) -> None:
    """#627: the app must declare what `main.py`'s exception handlers really send."""
    declared = {op: codes for op, codes in _declared_error_codes(schema).items() if codes}
    assert declared == EXPECTED_ERROR_RESPONSES


def test_error_responses_use_the_shared_error_body(schema: dict) -> None:
    """Every declared error is `{detail, correlation_id?}` — what `_error_payload` sends."""
    offenders = []
    checked = 0
    for operations in schema["paths"].values():
        for operation in operations.values():
            operation_id = operation["operationId"]
            for code, response in operation["responses"].items():
                if code not in _DOMAIN_ERROR_CODES:
                    continue
                if (operation_id, code) in NON_ERROR_BODY_RESPONSES:
                    continue
                checked += 1
                ref = response["content"]["application/json"]["schema"].get("$ref")
                if ref != "#/components/schemas/ErrorResponse":
                    offenders.append(f"{operation_id} {code}: {ref}")
    assert checked, "No error responses were checked — this assertion would pass vacuously."
    assert not offenders, (
        "Error responses must reference ErrorResponse (platform_control.schemas.errors), "
        "which is the body platform_control.main._error_payload builds:\n  "
        + "\n  ".join(offenders)
    )


def test_di_event_validation_errors_reference_an_existing_component(schema: dict) -> None:
    """The three `/v1/di/events/*` receivers point their 422 at FastAPI's own component.

    They validate a raw body themselves (the payload may be a Pub/Sub push
    envelope), so FastAPI documents no 422 for them and
    `VALIDATION_ERROR_RESPONSE` supplies one by `$ref`. If nothing else in the
    app emits `HTTPValidationError`, that ref dangles.
    """
    assert "HTTPValidationError" in schema["components"]["schemas"]
    for path in (
        "/v1/di/events/document-processing-status-updated",
        "/v1/di/events/document-processed",
        "/v1/di/events/document-withdrawn",
    ):
        response = schema["paths"][path]["post"]["responses"]["422"]
        ref = response["content"]["application/json"]["schema"]["$ref"]
        assert ref == "#/components/schemas/HTTPValidationError"


def test_settings_is_not_published_as_a_schema(schema: dict) -> None:
    """The service's own configuration model must never reach the contract (#682).

    `Settings` enumerates every credential the service holds by name
    (`firecrawl_webhook_secret`, `operator_api_key`, `s3_secret_access_key`, …). It
    leaked because `get_artifact_store`/`get_raw_artifact_publisher` took a bare
    `settings: Settings | None = None` parameter, which FastAPI classifies as a
    *request body* when the callable is used via `Depends`. Any dependency that grows
    the same signature shape re-opens this, so assert on the published document rather
    than on those two functions.
    """
    assert "Settings" not in schema["components"]["schemas"]

    published = yaml.dump(schema)
    for secret_field in (
        "firecrawl_webhook_secret",
        "operator_api_key",
        "service_api_key",
        "s3_secret_access_key",
        "legifrance_client_secret",
    ):
        assert secret_field not in published, (
            f"Settings field {secret_field!r} appears in the published schema — a "
            "Pydantic-typed parameter on a Depends()-injected callable was hoisted "
            "into a request body again (#682)."
        )


def test_firecrawl_webhook_declares_no_request_body(schema: dict) -> None:
    """It reads raw bytes to verify the HMAC, so it has no typed body to declare.

    Its docstring says exactly that; before #682 the contract contradicted it with
    `anyOf: [$ref Settings, null]`.
    """
    assert "requestBody" not in schema["paths"]["/v1/firecrawl/webhooks"]["post"]


_COMPLETENESS_SCORE_PATTERN = re.compile(
    r"percent|ratio|completeness|score|fraction|searchable", re.IGNORECASE
)
_COVERAGE_SCHEMAS = (
    "AcquisitionCoverageEntry",
    "AcquisitionCoverageSummary",
    "AcquisitionCoverageListResponse",
)


def test_coverage_never_publishes_a_completeness_score(schema: dict) -> None:
    """ADR-0042 rejected a completeness score outright — as a gate, not a rule to recall.

    > "Every such number needs a denominator ... A completeness score would be the single
    > most dangerous field we could ship here."

    The ledger reports raw counts and gaps so an operator reads `1377 / 1377` and draws
    their own conclusion. `searchable` is in the pattern for a different reason: this
    service cannot observe the index (ADR-0042 §4), so a field claiming to would be an
    inference dressed as a measurement.
    """
    schemas = schema["components"]["schemas"]
    offenders = []
    checked = 0
    for name in _COVERAGE_SCHEMAS:
        assert name in schemas, f"{name} is missing — this test would pass vacuously."
        for field in schemas[name].get("properties", {}):
            checked += 1
            if _COMPLETENESS_SCORE_PATTERN.search(field):
                offenders.append(f"{name}.{field}")
    assert checked, "No coverage fields were checked — this assertion would pass vacuously."
    assert not offenders, (
        "Acquisition coverage must not publish a percentage, ratio or completeness score "
        "(ADR-0042 'Rejected outright'), nor claim the index stage it cannot observe:\n  "
        + "\n  ".join(offenders)
    )
