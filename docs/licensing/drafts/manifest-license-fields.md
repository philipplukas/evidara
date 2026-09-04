# Manifest `license` fields — the exact edits, per option

> **DRAFT. Nothing here has been applied.** No `license` field is set anywhere in this repository
> except `tools/zed-evidara-extension/Cargo.toml:6`, which pre-dates this brief — see
> [§1a](../README.md#1a-one-manifest-does-declare-a-licence-and-it-says-apache-20).
>
> This page exists so that adopting a choice is a copy-paste, not a scavenger hunt.

## The eleven places a licence has to be declared

| # | File | Today | Notes |
|---|---|---|---|
| 1 | `package.json` (root, `evidara-doc-tools`) | absent, `private: true` | |
| 2 | `legal-search/api/package.json` | absent, `private: true` | |
| 3 | `legal-search/frontend/package.json` | absent, `private: true` | |
| 4 | `marketing/package.json` | absent, `private: true` | |
| 5 | `platform-control/admin/package.json` | absent, `private: true` | |
| 6 | `platform-control/pyproject.toml` | absent | |
| 7 | `document-intelligence/pyproject.toml` | absent | |
| 8 | `tools/evidara-cli/pyproject.toml` | absent | |
| 9 | `infra/coordinator/pyproject.toml` | absent | missed by the research memo |
| 10 | `tools/zed-evidara-mcp/pyproject.toml` | absent | missed by the research memo |
| 11 | `tools/zed-evidara-extension/Cargo.toml` | **`license = "Apache-2.0"`** | `publish = false`. The only existing declaration |

Plus four API contracts, which are a separate problem — see the last section.

---

## Option A — Apache-2.0

**`package.json` × 5**

```json
  "license": "Apache-2.0",
```

Keep `"private": true` on every one of them unless a package is actually meant to be published to
npm. `private` and `license` are orthogonal: `private` stops `npm publish`, `license` states terms.

**`pyproject.toml` × 5** — PEP 639 form (setuptools ≥ 77, hatchling ≥ 1.27; both surfaces satisfy
this):

```toml
[project]
license = "Apache-2.0"
license-files = ["LICENSE", "NOTICE"]
```

Do **not** use the legacy `license = { text = "..." }` table or a
`License :: OSI Approved :: ...` classifier alongside it — PEP 639 makes the classifier redundant
and some build backends now error on the combination.

`document-intelligence/pyproject.toml` and `tools/zed-evidara-mcp/pyproject.toml` build with
`setuptools`; the other three use `hatchling`. Both honour `license-files`.

**`Cargo.toml`** — already correct; no edit.

**Root files:** `LICENSE` from [`apache-2.0.LICENSE.txt`](apache-2.0.LICENSE.txt),
`NOTICE` from [`NOTICE.txt`](NOTICE.txt).

---

## Option B — MIT

Identical to Option A with `Apache-2.0` → `MIT`, `LICENSE` from
[`mit.LICENSE.txt`](mit.LICENSE.txt), and:

- `license-files = ["LICENSE"]` — **no `NOTICE`.** A NOTICE file has no meaning under MIT.
- `tools/zed-evidara-extension/Cargo.toml:6` **must be changed** from `Apache-2.0` to `MIT`.
  This is the one edit Option B forces that Option A does not.

---

## Option C — all rights reserved (the [§4(b)](../README.md#4-recommendation) recommendation)

**`package.json` × 5**

```json
  "license": "UNLICENSED",
```

`UNLICENSED` is npm's own convention for "no licence granted" and is correct here — but it is **not
an SPDX identifier**, which is exactly why it must not be copied into the OpenAPI specs (below).

**`pyproject.toml` × 5** — leave the `license` field **absent**. There is no SPDX identifier for
"all rights reserved", and `LicenseRef-Proprietary` in a `[project] license` field will fail
validation on some build backends. Say it in `LICENSE` and `README.md` instead.

**`tools/zed-evidara-extension/Cargo.toml:6`** — **must be changed.** Under this option the crate
would be the only Apache-2.0-licensed thing in an otherwise all-rights-reserved repo. Either:

```toml
# remove the line entirely, and rely on the root LICENSE, or:
license-file = "../../LICENSE"
```

`publish = false` already prevents an accidental crates.io release, so this is a consistency fix
rather than an exposure fix.

**Root file:** `LICENSE` from
[`all-rights-reserved.LICENSE.txt`](all-rights-reserved.LICENSE.txt).

---

## Option D — BSL 1.1

**`package.json` × 5**

```json
  "license": "SEE LICENSE IN LICENSE",
```

npm's escape hatch for a non-SPDX licence. `"BUSL-1.1"` *is* a registered SPDX identifier, so
`"license": "BUSL-1.1"` is also valid and more informative — but BSL requires the parameter block
to travel with the text, so pointing at the file is safer.

**`pyproject.toml` × 5**

```toml
[project]
license = "BUSL-1.1"
license-files = ["LICENSE"]
```

**Root file:** the canonical BSL 1.1 text from <https://mariadb.com/bsl11/> with the parameter block
from [`bsl-1.1.PARAMETERS.txt`](bsl-1.1.PARAMETERS.txt) filled in. That file is **parameters only**
and is deliberately not a licence.

---

## The four API contracts — a separate, mandatory fix

Three specs currently declare a licence that is both **contrary to `Cargo.toml`** and **invalid
under OpenAPI 3.1**:

```yaml
  license:
    name: Proprietary
    identifier: UNLICENSED
```

- `contracts/api/legal-search.openapi.yaml:22`
- `contracts/api/document-intelligence.openapi.yaml:16`
- `contracts/api/document-intelligence-runtime.openapi.yaml:13`

`info.license.identifier` **must** be an SPDX expression. `UNLICENSED` is npm vocabulary and has no
SPDX registration, so these three fields are non-conformant today regardless of what is chosen.

**Under Option A / B**, replace with:

```yaml
  license:
    name: Apache License 2.0        # or: MIT License
    identifier: Apache-2.0          # or: MIT
```

**Under Option C**, drop `identifier` — OpenAPI 3.1 permits `name` alone, and that is the only
conformant way to express a non-SPDX licence:

```yaml
  license:
    name: Proprietary — All rights reserved
```

**Under Option D**, `identifier: BUSL-1.1` is valid.

### The fourth contract needs a different route

`contracts/api/platform-control.openapi.yaml` carries **no `license` block at all**, because it is
generated from the FastAPI app (ADR-0034) and FastAPI emits none. Its header says so:

```text
# GENERATED FILE — DO NOT EDIT.
```

To give it one, set `license_info` on the FastAPI app in
`platform-control/src/platform_control/openapi.py` and **regenerate**:

```bash
cd platform-control && uv run python ../scripts/generate_platform_control_contract.py
```

Hand-editing the YAML will be caught: `scripts/check-platform-control.sh` runs the contract-drift
gate in pre-commit and CI, and hand-maintaining this file is what caused #614/#616 (see #618).

### Knock-on: generated clients

`legal-search/frontend/src/lib/api/generated/**` (68 files), `legal-search/api/src/lib/document-intelligence/generated/**`
(9 files) and `platform-control/admin/src/lib/api/generated/**` are produced by orval and
openapi-typescript from these specs. They do not currently reproduce `info.license`, so no
regeneration is required by a licence edit alone — but run the drift gates
(`npm run openapi:check` in the frontend) after changing any spec, as usual.
