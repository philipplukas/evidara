# Local Dev RAM Guide

## Purpose

Keep local development stable on lower-memory laptops by running only the
services needed for the current task.

## Recommended RAM Targets

- Minimum usable (lite mode): about 4 GB free RAM
- Recommended (search mode): about 8 GB free RAM
- Comfortable (full mode + browser/tests): 12 GB+ free RAM

## Runtime Modes

Use `scripts/local-vertical-slice.sh` with an explicit mode:

```bash
# lowest RAM footprint
bash scripts/local-vertical-slice.sh up lite

# default for legal-search API/UI
bash scripts/local-vertical-slice.sh up search

# includes pubsub emulator for full event wiring sessions
bash scripts/local-vertical-slice.sh up full
```

## One-Command Compose App Stack

If you prefer no individual app startup, use:

```bash
bash scripts/local-vertical-slice.sh up-all search
```

or:

```bash
bash scripts/local-vertical-slice.sh up-all full
```

This starts infra plus app containers (`platform-control` API/admin and
`legal-search` API/frontend) and runs init/seed steps in one-shot containers.

After startup, verify quickly:

```bash
bash scripts/local-vertical-slice.sh check-all search
```

## What Each Mode Starts

- `lite`: postgres
- `search`: postgres, opensearch
- `full`: postgres, opensearch, pubsub emulator

## Typical Memory Envelope

- `postgres`: 150-300 MB
- `opensearch` (256m heap): about 600-1200 MB real usage
- `pubsub` emulator: 150-300 MB
- Docker engine overhead: 0.5-1.0 GB

Estimated totals:

- `lite`: about 0.8-1.6 GB
- `search`: about 1.6-2.8 GB
- `full`: about 1.8-3.1 GB

## Compose Limits Used

- `postgres` limited to 512 MB
- `opensearch` limited to 1 GB (`-Xms256m -Xmx256m`)
- `pubsub` limited to 256 MB

These limits improve predictability on low-RAM machines while keeping local
feature development workable.

## Suggested Workflows by Laptop Class

### 4 GB free RAM

- Start infra in `lite` mode
- Run only one app dev server at a time where possible
- Avoid running smoke/e2e continuously in the background

### 8 GB free RAM

- Start infra in `search` mode
- Either run host apps selectively, or use `up-all search` for convenience
- Run smoke tests manually when needed

### 12 GB+ free RAM

- Use `full` mode for event-wiring sessions
- Run multiple app dev servers plus targeted smoke/e2e checks

## Teardown

Stop only the active mode:

```bash
bash scripts/local-vertical-slice.sh down search
```

Stop compose app stack:

```bash
bash scripts/local-vertical-slice.sh down-all search
```

Or remove all resources/volumes:

```bash
docker compose down -v
```
