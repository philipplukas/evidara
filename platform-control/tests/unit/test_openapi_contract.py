"""The invariants that make contracts/api/platform-control.openapi.yaml generatable.

The contract is an export of this app's `/openapi.json` (#618). These tests guard
the properties that export depends on — the ones a normal code change could break
silently, leaving the drift gate to fail with a confusing diff instead of a
sentence.

The drift gate itself (generated == committed) lives in
scripts/check-platform-control.sh, because it compares a file, not behaviour.
"""

from __future__ import annotations

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
#: /v1/sources/{source_id}/versions` and the reference-data lists return every
#: row — and the contract now says so per endpoint instead of implying one rule.
PAGINATED_LIST_RESPONSES = {
    "CapturedResourceListResponse",
    "CommentaryInsightListResponse",
    "CorpusListResponse",
    "CorrectionListResponse",
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
