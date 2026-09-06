# Local dev loops: which stack, and when

There are two ways to run Evidara locally. They look interchangeable — both can start
`platform-control-api` and the admin — and they are not. Picking the wrong one costs either
a rebuild per edit, or a missing service that makes a run sit `PENDING` forever.

| Loop | Command | Reload | Use it for |
|---|---|---|---|
| **Inner** (seconds) | `bash scripts/platform-control-demo.sh dev` | yes — uvicorn `--reload` + Next HMR | writing code: UI work, API handlers, anything you iterate on |
| **Outer** (minutes) | `docker compose -f docker-compose.yml -f docker-compose.local.yml --profile apps --profile nats --profile minio --profile search up` | **no** | acceptance runs, NATS/MinIO/OpenSearch paths, e2e scripts, "does the built image work" |

Both `-f` flags and all four profiles are required, and neither is boilerplate:

- **Both files.** `docker-compose.local.yml` is an *overlay* that defines the app
  services; `postgres` and `opensearch` live in the base `docker-compose.yml`. Passing
  only the overlay selects services whose dependencies are then undefined, and compose
  rejects the whole project as invalid rather than starting a subset — so the failure is
  total, and its message names a service you never asked for.
- **`--profile search`.** OpenSearch declares `profiles: [search, full, lean-stack]`, so
  `--profile apps` alone selects `legal-search-api` with its dependency missing. This one
  was absent from `scripts/ch-fedlex-compose-e2e.sh`'s own header until 2026-07-22.

`python3 scripts/check_compose_profiles.py` is the gate that enforces this against every
compose command written in the docs, and it runs in CI.

## Why the compose stack is not a dev loop

`docker-compose.local.yml` builds `platform-control-api` and `platform-control-admin` from
their Dockerfiles with **no source volume mounts**, the API command carries **no `--reload`**,
and the admin image is a *production* Next build. So every code change costs a
`docker compose build` plus a recreate.

That is the correct design for what it is. The compose stack wires the fourteen services the
acceptance loop needs — NATS JetStream, MinIO, OpenSearch, the DI consumer, the projection
bridge, and `platform-control-worker`, without which `ris_ogd` runs sit `PENDING` forever with
`refused=false` and no `failure_reason` (a stall that reads like a provider bug and is really a
missing worker). Reproducing that by hand is not worth doing.

The inner loop keeps **infra in Docker and code on the host**: `scripts/platform-control-demo.sh`
starts only the `postgres` service and runs the API and admin natively.

## The inner loop

```bash
bash scripts/platform-control-demo.sh bootstrap   # once: Postgres + migrations + seed
bash scripts/platform-control-demo.sh dev         # Postgres + API + admin, Ctrl-C stops both
```

`dev` starts the API first and waits for `/health` before starting the admin — the admin's BFF
proxies `/api/platform-control/*` to `:8000`, so an admin started first serves a wall of
connection errors that look like real failures. Both children run under `setsid`, so Ctrl-C
signals the whole process group; without that, `uv run uvicorn` and `npm run dev` leave orphaned
grandchildren holding the ports and the next `dev` fails with "address already in use".

Prerequisites the loop does not install for you:

- **Node 22 via nvm** — `source ~/.config/nvm/nvm.sh; nvm use` in `platform-control/admin`.
  System Node breaks the build and makes gates dishonest.
- **`platform-control/admin/.env.local`** with the build-time role vars, or every list renders
  empty:

  ```text
  NEXT_PUBLIC_USER_ROLE=admin
  NEXT_PUBLIC_ADMIN_ALLOWED_ROLES=admin
  PLATFORM_CONTROL_API_URL=http://127.0.0.1:8000
  ```

### Ports — the two admins are not the same admin

| Surface | Inner loop | Compose |
|---|---|---|
| admin | `http://localhost:3000` (HMR) | `http://localhost:3100` (prod build) |
| API | `http://127.0.0.1:8000` | `http://127.0.0.1:8000` |

Both admins proxy to the same API on `:8000`. If both are up, it is easy to read the stale one
and conclude a change did not take. Check the port before debugging.

### Auth: the local stack runs keyless, by name

Auth fails closed. With no API key configured, **every protected route answers 503** and the
admin renders empty lists — which reads as a data bug rather than a config one.
`docker-compose.local.yml` opts in explicitly, and `scripts/platform-control-demo.sh`'s `api`
target now does the same (`PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED=1`, defaulted, so an
explicit value still wins). **Local only — never set in a deployment.**

### Seed the run states you cannot otherwise see

```bash
bash scripts/platform-control-demo.sh seed-demo-runs
```

Every run a local stack acquires ends `completed`, so `pending` / `running` / `failed` /
`cancelled` have never existed on a developer machine. Without this the attention chip, the
cancel row action, the failure copy and four of the five preset chips render nothing and cannot
be reviewed. Idempotent, `execution_mode: shadow`, nothing dispatched; refuses outside
`PLATFORM_CONTROL_ENVIRONMENT=development`.

## Seeing changes as an agent, not just as a human

The admin is client-rendered, so `curl` cannot confirm a UI change — the sidebar and lists are
not in the HTML from `/`. Drive the **dev** server with Playwright:

```bash
cd platform-control/admin        # run here so @playwright/test resolves
node .claude/skills/run-admin-panel/drive.mjs
```

Playwright does not wait on `document_idle`, so HMR does not block it. This is what makes the
agent loop as fast as the human one — no production build per iteration.

The narrower rule: **`claude-in-chrome` needs a production build; Playwright does not.** The
Chrome-extension automation times out against `npm run dev` ("Script injection timed out",
"waited 45000ms for document_idle") because Next 16 / React 19 HMR never reports the browser
idle. That is a limitation of the extension path, not of automation generally.

## Housekeeping

`docker compose -f docker-compose.yml -f docker-compose.local.yml down --remove-orphans` when
you are not mid-flight.
Compose warns about orphan `evidara-*` containers from previous runs of the outer loop; they
keep holding memory, and an old `platform-control-admin` still up on `:3100` is the most likely
way to end up reading a stale UI.

## Related

- [platform-control-local-demo.md](platform-control-local-demo.md) — the step-by-step demo walkthrough
- [local-dev-ram-guide.md](local-dev-ram-guide.md) — memory budgeting for the outer loop
- [local-vertical-slice.md](local-vertical-slice.md) — the full acquisition slice on compose
