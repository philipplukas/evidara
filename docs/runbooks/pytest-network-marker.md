# Pytest `requires_network` marker (platform-control)

## What

A `requires_network` pytest marker that skips network-dependent tests by default
and runs them when `PYTEST_NETWORK_TESTS=1` is set. Introduced in #278.

Registered in [`platform-control/pyproject.toml`](../../platform-control/pyproject.toml)
(`[tool.pytest.ini_options].markers`); the skip logic lives in
[`platform-control/tests/conftest.py`](../../platform-control/tests/conftest.py)
as a `pytest_collection_modifyitems` hook.

## Why

The Temporal SDK's `WorkflowEnvironment.start_time_skipping()` helper downloads
an ephemeral test-server binary from `https://temporal.download/...`.
Sandboxed CI and dev environments block that host (HTTP 403), which breaks any
test that calls the helper. The repo has other tests that may also need
outbound network in future — the marker gives us a single, documented
escape hatch instead of a grab-bag of `@pytest.mark.skip` decorators.

Currently applied to two tests in `tests/unit/test_wizard_service.py`:

- `test_temporal_orchestrator_starts_workflow_and_signals`
- `test_temporal_orchestrator_starts_standalone_child_workflows`

## How to use it

### Run everything except network-dependent tests (default)

```bash
cd platform-control && uv run pytest
```

Network-marked tests will show as `SKIPPED [reason]` in the summary — visible,
not silently deselected.

### Run network-dependent tests (CI job or local debugging)

```bash
cd platform-control && PYTEST_NETWORK_TESTS=1 uv run pytest
```

Or target just the marked tests:

```bash
cd platform-control && PYTEST_NETWORK_TESTS=1 uv run pytest -m requires_network
```

### Add the marker to a new test

```python
import pytest

@pytest.mark.requires_network
def test_thing_that_needs_outbound() -> None:
    ...
```

If you also need `@pytest.mark.asyncio`, stack them:

```python
@pytest.mark.asyncio
@pytest.mark.requires_network
async def test_async_thing_that_needs_outbound() -> None:
    ...
```

## Escape hatches

- **Run the tests locally anyway**: `PYTEST_NETWORK_TESTS=1 uv run pytest`.
- **Want a dedicated CI job that runs them**: add a workflow step that sets the
  env var, runs `pytest -m requires_network`, and ensures its runner has
  outbound to `temporal.download` (and whatever else marked tests hit).
  Deferred from #278 — currently no such job exists.
- **Want the coverage without outbound**: see Option 1 in #278 — pin a
  pre-downloaded `temporal-test-server` binary in the runner image and pass
  its path via `TestServerConfig(existing_path=...)`. Tracked as a potential
  follow-up; not blocking.

## Related

- [#278](https://github.com/philipplukas/evidara/issues/278) — original flake
  report and option analysis
- [#279](https://github.com/philipplukas/evidara/issues/279) — M1 milestone
  (CI & Test Reliability)
