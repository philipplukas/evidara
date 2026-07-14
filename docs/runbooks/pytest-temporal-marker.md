# Pytest `temporal` marker and Temporal replay suite (platform-control)

Owner: Platform / DevEx
Last reviewed: 2026-07-14
Last verified: 2026-07-14
Applies to: `platform-control/tests/` — any test marked `@pytest.mark.temporal`, plus
`platform-control/tests/unit/test_temporal_replay.py`

## What

`temporal` marks a test that drives a real workflow on the temporalio SDK's local
time-skipping test server (`WorkflowEnvironment.start_time_skipping()`).

**These tests run by default.** `PYTEST_SKIP_TEMPORAL=1` opts out; CI refuses to
honour it. Both the marker registration
([`platform-control/pyproject.toml`](../../platform-control/pyproject.toml)) and the
skip logic ([`platform-control/tests/conftest.py`](../../platform-control/tests/conftest.py))
live next to each other.

This replaces the old `requires_network` marker / `PYTEST_NETWORK_TESTS=1` scheme
(#278), which inverted the default and was never opted into by any CI job — so
every test that started a Temporal workflow was skipped on every CI run for as long
as it existed (#564).

## Why the old marker was wrong

`start_time_skipping()` does not need the network to *run*. It starts a
`temporal-test-server` binary that binds a loopback port and talks to nothing.
It only touches the network to **fetch that binary the first time** — once per SDK
version, cached forever after.

So "requires network" described a cold cache, not the test. Naming the one-time
fetch as a permanent property of the test is what justified skipping it forever.
The fix is to cache the binary, not to skip the test:

- `tests/conftest.py` points the SDK's `download_dest_dir` at
  `platform-control/.temporal-test-server/` (gitignored) instead of the system temp
  dir the SDK defaults to, so the cache sits somewhere CI can persist.
- `.github/workflows/platform-control.yml` restores that directory with
  `actions/cache`, keyed on `platform-control/uv.lock` (which pins the temporalio
  version, which determines the binary). A cache miss is not fatal — the SDK
  re-fetches.
- Override the location with `TEMPORAL_TEST_SERVER_DIR=/some/path` if you keep a
  shared binary elsewhere.

## Why Temporal tests exist at all when Temporal is off

Per [ADR-0031](../adr/0031-temporal-argilla-firecrawl-disposition.md), Temporal is
**kept but switched off**: `wizard_orchestrator_backend` stays `in_memory`, and no
server or worker is deployed. The workflow code stays in the tree, which means it
can rot silently. These tests are the only thing that stops it. That is precisely
why CI is not allowed to skip them.

## The replay suite

`tests/unit/test_temporal_replay.py` covers every workflow in
`platform_control.temporal.workflows.ALL_WORKFLOWS` — the same list the worker
registers, so adding a workflow without replay coverage fails a test.

Two layers:

| Test | Needs test server? | Guards |
|---|---|---|
| `test_recorded_history_replays` | No — pure in-process | A workflow-code change breaking replay of **in-flight** executions started against the old code |
| `test_live_execution_replays` | Yes (`temporal` marker) | Determinism of the code as it stands; a worker restart mid-execution. Doubles as the recorder |

Recorded histories live in `platform-control/tests/data/temporal_histories/*.json`,
one per workflow, and are checked in **on purpose** — a history recorded against
today's code cannot catch tomorrow's replay-breaking edit.

### When `test_recorded_history_replays` fails

It fails with `NondeterminismError`. That means the change under review would wedge
every in-flight execution of that workflow the moment a worker running the new code
picked it up — a workflow task that fails and retries forever, not a clean error.

**Do not fix it by re-recording the history.** That deletes the evidence and ships
the break. Fix it by gating the new behaviour behind
[`workflow.patched` / `workflow.deprecate_patch`](https://docs.temporal.io/develop/python/versioning),
so old histories take the old path and new executions take the new one.

Re-recording is only correct when the workflow is genuinely new, or when no
execution of it can possibly be in flight (which, with Temporal switched off
everywhere, is currently true — but say so in the PR, don't assume it silently):

```bash
cd platform-control && RECORD_TEMPORAL_HISTORIES=1 uv run pytest \
    tests/unit/test_temporal_replay.py -k live_execution
```

## How to use the marker

### Run everything (default — includes Temporal)

```bash
cd platform-control && uv run pytest
```

### Run only the Temporal tests

```bash
cd platform-control && uv run pytest -m temporal
```

### Skip them (offline, cold binary cache)

```bash
cd platform-control && PYTEST_SKIP_TEMPORAL=1 uv run pytest
```

Not honoured when `CI` is set — `pytest` errors out instead. Cache the binary.

### Add the marker to a new test

Take the `temporal_env` fixture rather than calling `WorkflowEnvironment` directly,
so the binary cache location stays in one place:

```python
@pytest.mark.asyncio
@pytest.mark.temporal
async def test_thing(temporal_env: WorkflowEnvironment) -> None:
    async with Worker(temporal_env.client, ...):
        ...
```

## Related

- [ADR-0031](../adr/0031-temporal-argilla-firecrawl-disposition.md) — Temporal kept
  but switched off; Argilla deleted
- [#564](https://github.com/philipplukas/evidara/issues/564) — every Temporal test
  skipped in CI; replay coverage missing
- [#278](https://github.com/philipplukas/evidara/issues/278) — the original
  `requires_network` marker this supersedes
- [#560](https://github.com/philipplukas/evidara/issues/560),
  [#561](https://github.com/philipplukas/evidara/issues/561) — known Temporal bugs,
  deliberately deferred by ADR-0031 as entry criteria for any future rollout
