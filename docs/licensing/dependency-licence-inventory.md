# Dependency licence inventory

Supporting evidence for [§2.6 of the licensing decision brief](README.md#26-dependencies-nothing-copyleft-blocks-a-permissive-choice--with-three-caveats).
Audited **2026-09-03** against `origin/main` at `59721399`.

> Not legal advice. This is a record of what each package *declares*, and of how that was read.

## Method, and what it can and cannot see

Every licence below is the package's **own declared licence**, read from installed metadata — not
from a licence-scanner database, a README, or memory:

- **Python** — the `License-Expression` / `License` / `Classifier: License ::` fields of the
  installed `*.dist-info/METADATA` in each surface's `.venv`. Reported with the exact resolved
  version.
- **JavaScript, direct** — the `license` field of the installed `node_modules/<pkg>/package.json`,
  preferring the surface's own tree.
- **JavaScript, transitive** — the `license` field npm records for every resolved package in each
  surface's `package-lock.json`. This covers the surfaces whose `node_modules` are not installed
  locally (`marketing`, repo root), where the lock is the only evidence available.

**Limits, stated honestly:**

- A declared licence is what the publisher asserts. It is not an audit of that package's own
  vendored contents.
- Optional Python extras that are **not installed** cannot be read this way and are marked
  `NOT INSTALLED` below rather than guessed.
- Lockfile histograms count *resolved packages*, which includes multiple platform variants of the
  same library (`lightningcss-*`, `@img/sharp-*`) — a count of 13 MPL-2.0 rows is one library.

## Python surfaces

### `platform-control` — runtime dependencies

| Package | Resolved | Declared licence |
|---|---|---|
| aiosqlite | 0.22.1 | MIT |
| alembic | 1.18.4 | MIT |
| asyncpg | 0.31.0 | Apache-2.0 |
| boto3 | 1.43.36 | Apache-2.0 |
| croniter | 6.2.2 | MIT |
| fastapi | 0.135.2 | MIT |
| google-cloud-pubsub | 2.36.0 | Apache 2.0 |
| google-cloud-storage | 3.10.1 | Apache 2.0 |
| greenlet | 3.3.2 | MIT AND PSF-2.0 |
| httpx | 0.28.1 | BSD-3-Clause |
| nats-py | 2.15.0 | Apache-2.0 |
| prometheus-client | 0.25.0 | Apache-2.0 AND BSD-2-Clause |
| pydantic | 2.12.5 | MIT |
| pydantic-settings | 2.13.1 | MIT |
| pyyaml | 6.0.3 | MIT |
| sqlalchemy | 2.0.48 | MIT |
| temporalio | 1.24.0 | MIT |
| uvicorn | 0.42.0 | BSD-3-Clause |

**Clean.** No copyleft in the runtime set.

### `platform-control` — dev group

| Package | Resolved | Declared licence |
|---|---|---|
| jsonschema | 4.26.0 | MIT |
| **psycopg** | **3.3.3** | **LGPL-3.0-only** |
| pytest | 8.4.2 | MIT |
| pytest-asyncio | 1.3.0 | Apache-2.0 |
| referencing | 0.37.0 | MIT |
| ruff | 0.15.8 | MIT |
| testcontainers | 4.14.2 | Apache-2.0 |

**`psycopg[binary]` is the only copyleft direct dependency anywhere in the repo.** It is declared in
`[dependency-groups] dev` of `platform-control/pyproject.toml` and drives the Testcontainers
Postgres integration layer. LGPL obligations attach to *distributing a work that links the library*;
a test-time dependency that never enters a shipped image or wheel does not trigger them. **This does
not constrain the licence choice** — but it would if `psycopg` ever moved into the runtime set, and
that move should be a deliberate decision rather than a convenience import.

### `document-intelligence`

Runtime: `boto3` (Apache-2.0), `deltalake` 1.5.0 (Apache-2.0), `google-cloud-pubsub` /
`google-cloud-storage` (Apache 2.0), `jsonschema` (MIT), `nats-py` (Apache-2.0), `pdfplumber`
0.11.10 (MIT), `prometheus-client` (Apache-2.0 AND BSD-2-Clause), `pyarrow` 23.0.1 (Apache-2.0),
`PyYAML` (MIT).

Extras, installed: `ruff` (MIT), `fastapi` (MIT), `httpx` (BSD-3-Clause), `uvicorn` (BSD-3-Clause),
`dspy` 3.1.3 (MIT), `google-cloud-aiplatform` 1.146.0 (Apache 2.0), `instructor` 1.15.1 (MIT),
`openai` 2.31.0 (Apache-2.0), `pytest` 9.0.2 (MIT), `reportlab` 5.0.0 (BSD).

Extras, **not installed and therefore not verified here**: `docling`, `spacy`, `spacy-llm`,
`testcontainers`. `docling` is discussed at
`docs/adr/0037-binary-artifacts-and-layout-aware-pdf.md:109` as *"MIT, but pulls a large transitive
stack"* — that transitive stack is the part that has never been enumerated, and it is where an
adopted-later copyleft dependency would most plausibly appear.

**Note the one licence decision already on record:** `PyMuPDF`/`fitz` was **rejected for being
AGPL** (`0037-binary-artifacts-and-layout-aware-pdf.md:115`) in favour of `pdfplumber` (MIT).

### `tools/evidara-cli`

`httpx` (BSD-3-Clause), `pyyaml` (MIT), `typer` 0.24.1 (MIT); dev `pytest` (MIT), `ruff` (MIT).
**Clean, and this is the surface holding `envelope.py`** — the extraction candidate in
[§4(a)](README.md#4-recommendation). Its own imports are standard-library only.

### `infra/coordinator` and `tools/zed-evidara-mcp`

No local `.venv`, so declared licences were not read from metadata. Declared direct dependencies,
from their `pyproject.toml`: `fastapi`, `uvicorn[standard]`, `httpx`, `temporalio`, `pyyaml`,
`pydantic`, `pydantic-settings` (coordinator — all appear elsewhere in this table as
MIT/BSD/Apache-2.0); `mcp` (zed-evidara-mcp — not verified).

## JavaScript surfaces

### Direct dependencies

Only rows that are not plain MIT / Apache-2.0 / ISC / BSD are called out; the full run is
reproducible with the method above.

| Surface | Direct deps | Notable |
|---|---|---|
| `legal-search/api` | 12 + 14 dev | **none** — MIT / Apache-2.0 throughout |
| `legal-search/frontend` | 20 + 17 dev | **`dompurify` — `(MPL-2.0 OR Apache-2.0)`**; `lucide-react` ISC |
| `marketing` | 6 + 15 dev | **none** in the direct set |
| `platform-control/admin` | 15 + 16 dev | **none** in the direct set; `lucide-react`, `yaml` ISC |
| repo root (`evidara-doc-tools`) | 0 + 2 dev | **none** (`jsdom`, `mermaid`) |

**`dompurify` is a disjunction, so the project elects one.** Electing **Apache-2.0** means MPL's
file-level copyleft never engages and the election is compatible with either an Apache-2.0 or an
MIT root licence. The election should be recorded in `NOTICE` / `THIRD-PARTY-NOTICES`; it is
currently implicit.

### Full resolved trees, by declared licence

Counts are **resolved packages**, from each `package-lock.json`.

| Licence | `ls/api` | `ls/frontend` | `marketing` | `pc/admin` | root |
|---|---:|---:|---:|---:|---:|
| MIT | 676 | 936 | 212 | 387 | 120 |
| Apache-2.0 | 61 | 73 | 18 | 23 | 7 |
| ISC | 40 | 47 | 6 | 10 | 35 |
| BSD-3-Clause | 26 | 26 | 2 | 5 | 7 |
| BSD-2-Clause | 14 | 14 | 2 | 3 | 2 |
| **MPL-2.0** | **12** | **14** | **14** | **14** | 0 |
| Apache-2.0 AND MIT | 11 | 11 | 0 | 0 | 0 |
| **LGPL-3.0-or-later** | 0 | **10** | **10** | **10** | 0 |
| **Apache-2.0 AND LGPL-3.0-or-later** | 0 | **3** | **3** | **3** | 0 |
| BlueOak-1.0.0 | 10 | 7 | 1 | 0 | 0 |
| MIT OR Apache-2.0 | 9 | 9 | 9 | 9 | 0 |
| **CC-BY-4.0** | **1** | **1** | **1** | **1** | 0 |
| no `license` field | 5 | 2 | 0 | 0 | 1 |
| **AGPL / GPL / SSPL / BUSL / ELv2** | **0** | **0** | **0** | **0** | **0** |
| Total resolved | 872 | 1164 | 283 | 475 | 175 |

**The bottom two rows are the load-bearing ones.**

- **Zero** strong-copyleft or source-available packages appear at any depth in any surface. The two
  named risks from the research memo — **Soda Core (relicensed to ELv2 at v4)** and the **GPL/LGPL
  half of the Laws.Africa stack** — are not dependencies of this repo. They constrain future
  adoption, not the current choice.
- **No package with an absent `license` field is a direct dependency** of any surface.

What the copyleft rows actually are:

| Row | Packages | Why it is there | Does it constrain the choice? |
|---|---|---|---|
| MPL-2.0 | `lightningcss` + 12 platform binaries, `axe-core` (test only), `dompurify` | Tailwind v4 / Next.js CSS toolchain; a11y test harness | **No.** File-level copyleft; nothing is modified. `dompurify` can elect Apache-2.0 |
| LGPL-3.0-or-later | `@img/sharp-libvips-*` — 10 prebuilt native binaries, + 3 `Apache-2.0 AND LGPL-3.0-or-later` wrappers, + 1 wasm build | libvips, pulled by Next.js image optimisation | **No** for source. **Yes** for a *shipped container image*: LGPL §4 obligations (relinking, licence text) attach to the distributed binary |
| CC-BY-4.0 | `caniuse-lite` | Browserslist data | **No.** But it is data under an attribution licence — owed a `THIRD-PARTY-NOTICES` line if a bundle is redistributed |

## Rust surface

`tools/zed-evidara-extension` — 90 resolved packages in `Cargo.lock`. Direct: `schemars` 0.8,
`serde` 1.0, `zed_extension_api` 0.7.0. **Not audited for licences**, because `Cargo.lock` does not
record them and no `~/.cargo` registry cache was consulted; the Rust ecosystem's overwhelming
default is `MIT OR Apache-2.0` but that was not verified here and should not be relied on.

**This crate is the one manifest in the repo that declares a licence** —
`tools/zed-evidara-extension/Cargo.toml:6` says `license = "Apache-2.0"` — which is the
contradiction described in [§1a](README.md#1a-one-manifest-does-declare-a-licence-and-it-says-apache-20).

## What is *not* covered by this inventory

- **System and container base images.** `Dockerfile` base layers, the OpenSearch cluster, Postgres,
  NATS: all deployed rather than distributed, and out of scope here.
- **Transitive Python.** Only *direct* declarations were read. A full transitive Python audit
  (`uv tree` plus per-package metadata) is a separate job and is the right thing to run **before a
  first public release**, not before a licence choice.
- **Whether any package's own declaration is accurate.** Taken at face value.
