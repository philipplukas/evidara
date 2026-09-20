# AGPL-3.0 dependency compatibility audit

Run **2026-09-19** against `main` at `36a07ceb`, to answer one question before the relicence in
[`/LICENSE-HISTORY.md`](../../LICENSE-HISTORY.md): **does anything in the dependency graph make
AGPL-3.0-only unavailable?**

Answer: **no.** One finding needs a lawyer's eye eventually and is recorded in full below; it does
not block the change.

> Not legal advice. This is a record of what each package declares and how that was read.

## Method

Two independent passes per ecosystem, because each sees something the other cannot.

| Pass | What it reads | What it misses |
|---|---|---|
| JS, installed tree | the `license` field of every `package.json` under each surface's `node_modules`, recursing into nested trees | packages npm skipped as wrong-platform optional deps |
| JS, lockfile | the `license` npm recorded for every entry in each `package-lock.json` | nothing platform-specific — this is the complete resolution set |
| Python, installed | `License-Expression` / `Classifier: License ::` / `License` in each `*.dist-info/METADATA` in the surface's `uv` venv | extras not synced |
| Python, tree | `uv tree --invert --package <name>` to establish *why* a package is present | — |

Both JS passes were run with purpose-written scripts rather than a scanner database, so every row
is the publisher's own declaration. `npm ci` was run in all five JS surfaces and `uv sync --frozen`
in all three Python surfaces first; no surface reported `DID-NOT-RUN`. The docs toolchain
(`requirements-docs.txt`) was installed into a throwaway venv and read the same way.

Node 22.23.1 (`.nvmrc`), `uv` 0.5.9. `document-intelligence` was synced with
`--extra dev --extra service --extra test --extra llm`, which is the set the CI gate uses.

**What this cannot see:** whether a publisher's declaration is accurate, and what a package has
vendored inside itself. Both are taken at face value.

## The blocking set, searched for explicitly

These are the licences that would have stopped the change. Each was searched for by name across
every resolved package in every surface:

`SSPL` · `Elastic-2.0` / `ELv2` · `BUSL-1.1` / `BSL-1.1` · `CDDL` · `EPL-1.0` · `CC-BY-NC` and any
other non-commercial or source-available grant · `UNLICENSED` · absent `license` field ·
`GPL-2.0-only` · any `GPL`/`AGPL` at all.

**Result: zero hits, in all eight surfaces.** No package under any of those licences appears at any
depth.

The obvious trap was checked directly rather than assumed: the search client is
`@opensearch-project/opensearch@3.5.1`, declared **Apache-2.0**. OpenSearch is the Apache-2.0 fork;
no `elasticsearch` package is resolved anywhere in the repository.

## Totals, by resolved package

| Licence | root | ls/frontend | ls/api | pc/admin | marketing |
|---|---:|---:|---:|---:|---:|
| MIT (incl. `MIT-0`, `MIT OR Apache-2.0`, `Apache-2.0 AND MIT`) | 122 | 958 | 696 | 401 | 223 |
| Apache-2.0 | 7 | 73 | 61 | 23 | 18 |
| ISC | 35 | 47 | 40 | 10 | 6 |
| BSD-2/3-Clause, `0BSD`, `BSD` | 9 | 44 | 43 | 9 | 4 |
| MPL-2.0 (incl. `(MPL-2.0 OR Apache-2.0)`) | 1 | 15 | 12 | 15 | 14 |
| LGPL-3.0-or-later (incl. `Apache-2.0 AND LGPL-3.0-or-later`) | 0 | 14 | 0 | 14 | 14 |
| BlueOak-1.0.0 | 0 | 7 | 10 | 1 | 1 |
| CC0-1.0, Unlicense, `(MIT OR CC0-1.0)` | 1 | 3 | 3 | 2 | 1 |
| Python-2.0 (PSF) | 0 | 1 | 1 | 1 | 0 |
| CC-BY-4.0 | 0 | 1 | 1 | 1 | 1 |
| no `license` field | 1 | 2 | 5 | 0 | 0 |
| **Blocking set** | **0** | **0** | **0** | **0** | **0** |
| Total resolved | 175 | 1164 | 872 | 475 | 283 |

Python, by installed distribution: `platform-control` 83, `document-intelligence` 126,
`tools/evidara-cli` 26, docs toolchain 52. All MIT / BSD / Apache-2.0 / ISC / PSF-2.0 / MPL-2.0
except the rows resolved below.

## Every row that was not obviously permissive, resolved

### LGPL — compatible, one-way, in the direction we need

| Package | Where | Reading |
|---|---|---|
| `@img/sharp-libvips-*` (10 prebuilt binaries) + `@img/sharp-win32-*`, `@img/sharp-wasm32` (4 wrappers, `Apache-2.0 AND LGPL-3.0-or-later`) | frontend, admin, marketing — optional deps of Next.js image optimisation | LGPL-3.0-or-later |
| `psycopg` / `psycopg-binary` 3.3.3 | `platform-control/pyproject.toml:52`, **`[dependency-groups] dev` only** — the Testcontainers Postgres layer | LGPL-3.0-only |

The FSF states LGPLv3 "is compatible with GPLv3", and GPLv3 §13 permits combination with
AGPLv3 (<https://www.gnu.org/licenses/license-list.html>, fetched 2026-09-19). The direction of
travel is the permissive one: LGPL code can be taken into an AGPL work, not the reverse. `psycopg`
additionally never enters a shipped image — it is a test-time dependency.

This was the one row that would have *gained* significance under a permissive licence and loses it
under AGPL: LGPL §4's relinking obligation on a distributed binary is subsumed by what AGPL already
requires of us.

### MPL-2.0 — compatible, and the exception was checked rather than assumed

`lightningcss` (+ platform binaries), `axe-core`, `dompurify`; `certifi` and `tqdm` on the Python
side.

MPL-2.0 §3.3 gives what the FSF calls "indirect compatibility" with the GNU AGPL v3 **unless** the
file carries the Exhibit B "Incompatible With Secondary Licenses" notice. Exhibit B appears in
every copy of the MPL text — it is part of the licence's own boilerplate — so a naive grep finds it
and proves nothing. Grepping the three packages' files *excluding* their `LICENSE` returned no
match: the notice is nowhere applied to a source file. §3.3 therefore engages and the combination
is permitted.

`dompurify` declares `(MPL-2.0 OR Apache-2.0)` — a disjunction, so the project elects one arm.
Either works; electing **Apache-2.0** keeps file-level copyleft out of the picture entirely.

### CC-BY-4.0 — compatible; data, not code

`caniuse-lite`, via Browserslist, in all four Next.js surfaces. The FSF lists CC BY 4.0 as
"compatible with all versions of the GNU GPL" (same fetch). It is build-time browser-support data,
not linked code.

### Packages with no `license` field — all resolved to permissive by reading the file

npm's histogram shows eight; none is a direct dependency of any surface, and every one ships a
licence file:

| Package | Surface | What its licence file actually says |
|---|---|---|
| `busboy@1.6.0`, `streamsearch@1.1.0` | ls/api, **runtime** | MIT text, verbatim, "Copyright Brian White" |
| `ssh2@1.17.0`, `buildcheck@0.0.7`, `cpu-features@0.0.10` | ls/api, dev (Testcontainers) | same MIT text |
| `decko@1.2.0`, `stickyfill@1.1.1` | ls/frontend, dev | "The MIT License (MIT)" |
| `khroma@2.1.0` | root, dev (via `mermaid`) | "The MIT License (MIT)"; its readme says `MIT` |
| `google-crc32c==1.8.0` | Python, all surfaces | ships the full Apache-2.0 text as `LICENSE`; the METADATA simply omits the `License` key |

The npm convention of omitting `license` while shipping an MIT `LICENSE` file is a packaging
oversight upstream, not a licensing one. **Declared-and-empty is not the same as absent**, and the
distinction was worth eight file reads.

## The one finding that is not fully closed

**`regex==2026.4.4` declares `License-Expression: Apache-2.0 AND CNRI-Python`.**

Its `LICENSE.txt` explains why:

> This work was derived from the 're' module of CPython 2.6 and CPython 3.1, copyright (c)
> 1998-2001 by Secret Labs AB and licensed under CNRI's Python 1.6 license. All additions and
> alterations are licensed under the Apache 2.0 License.

This matters because the FSF holds that the CNRI licence covering Python 1.6b1–2.0 and 2.1 is
"a free software license but is incompatible with the GNU GPL", the stated reason being its Virginia
choice-of-law clause. The licence of Python **2.0.1, 2.1.1 and later** is GPL-compatible; only the
narrow CNRI window is not.

**Where it sits in the graph** (`uv tree --invert`):

```text
regex
├── dspy            → document-intelligence (extra: llm)
├── tiktoken → litellm → dspy   (extra: llm)
└── transformers    → docling (extra: docling), FlagEmbedding (extra: embeddings)
```

It is **not in the core runtime set**. Three of the four images install `--extra service` only and
do not contain it (`document-intelligence/Dockerfile:22`, `Dockerfile.document-service:22`,
`Dockerfile.runtime-ingress:20`); `Dockerfile.embeddings:46` installs `--extra embeddings` and does.

**Why this was not treated as a blocker:**

1. It is none of the licences the relicence was gated on — not SSPL, ELv2, BUSL, CDDL, EPL-1.0, a
   non-commercial grant, or GPL-2.0-only.
2. It is third-party-to-third-party. No Evidara code imports `regex`; `dspy` and `transformers` do.
3. The provenance claim is the package author's own characterisation, and it is questionable.
   CPython 2.6 and 3.1 were released under the PSF License Agreement v2, which the FSF *does* call
   GPL-compatible, and CPython's own LICENSE attributes the SRE module to Secret Labs under a
   separate permissive notice rather than under the CNRI agreement. The Apache-2.0 half covers
   everything written since.

**Why it is recorded anyway:** reading 3 as settled would be a conclusion that *fits* the evidence
rather than one the evidence *forces*. If the owner wants it eliminated rather than argued, the
route is the dependency graph above, not a licence field — the `llm`, `docling` and `embeddings`
extras are where it lives, and the `service` images are already clean.

## What this audit does not cover

- **`tools/zed-evidara-extension`** — 90 crates in `Cargo.lock`, which does not record licences, and
  no registry cache was consulted. The crate is `publish = false` and ships in nothing. Its own
  manifest licence was updated with the rest.
- **Container base images, and the deployed cluster software** (OpenSearch, Postgres, NATS). Those
  are deployed, not distributed as part of this work.
- **Whether a declaration is accurate.** Taken at face value throughout.
