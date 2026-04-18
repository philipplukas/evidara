# Temporal test server — skip policy in restricted networks

Owner: Platform / DevEx
Last reviewed: 2026-04-18
Last verified: 2026-04-18
Applies to: `platform-control/tests/unit/test_wizard_service.py` (and any future test that uses `temporalio.testing.WorkflowEnvironment.start_time_skipping`)

## Why

Temporal's `WorkflowEnvironment.start_time_skipping()` downloads an ephemeral test server binary from `https://temporal.download/temporal-test-server/...` on first use. Sandboxed CI runners and developer environments without egress to that host fail deterministically with:

```
RuntimeError: Failed starting test server: HTTP status client error
(403 Forbidden) for url (https://temporal.download/temporal-test-server/default?...)
```

Rather than fail every PR, we mark these tests with `@pytest.mark.temporal` and skip them by default. They run only when `EVIDARA_TEMPORAL_TESTS=1` is set (see §Running locally / in allow-listed CI).

See issue [#278](https://github.com/philipplukas/evidara/issues/278) for the decision.

## Which tests are marked

As of 2026-04-18, in `platform-control/tests/unit/test_wizard_service.py`:

- `test_temporal_orchestrator_starts_workflow_and_signals`
- `test_temporal_orchestrator_starts_standalone_child_workflows`

Any new test that calls `WorkflowEnvironment.start_time_skipping()` (or otherwise requires the test server download) MUST carry `@pytest.mark.temporal`.

## Running locally / in allow-listed CI

```bash
# From platform-control/, with outbound access to temporal.download:
EVIDARA_TEMPORAL_TESTS=1 uv run pytest tests/unit/test_wizard_service.py -m temporal
```

## Escape hatch for durable coverage

If we want these tests in the default signal without depending on the download, pin a pre-fetched binary into the runner image and switch to `TestServerConfig(existing_path=...)` (see option 1 in [#278](https://github.com/philipplukas/evidara/issues/278)). At that point the marker can be dropped.

## How the skip is wired

- Marker declared in `platform-control/pyproject.toml` → `[tool.pytest.ini_options].markers`
- Skip enforcement in `platform-control/tests/conftest.py` via `pytest_collection_modifyitems`, gated on `EVIDARA_TEMPORAL_TESTS`
