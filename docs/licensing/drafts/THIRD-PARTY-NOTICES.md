# THIRD-PARTY-NOTICES — draft

> **DRAFT. NOT IN EFFECT.** This file lives under `docs/licensing/drafts/` on purpose. It becomes
> real when it is copied to the repository root as `THIRD-PARTY-NOTICES.md`. Delete this block and
> the "Sources for each entry" section when adopting.
>
> **This file is owed regardless of which licence is chosen.** The obligations below come from the
> third parties' licences, not from ours. Nothing in it depends on the outcome of the decision in
> [the brief](../README.md).

Evidara redistributes or bundles the third-party material listed here. Each entry names the
component, its licence, and — where the licence requires it — reproduces the notice.

---

## 1. Material copied into this repository

These files were copied from an upstream project and are stored in this repository's own tree.
Their licences require the notices below.

### circle-flags

`legal-search/frontend/public/flags/ch.svg`
`legal-search/frontend/public/flags/at.svg`

Copied verbatim (md5-identical) from [circle-flags](https://github.com/HatScripts/circle-flags).

```text
MIT License

Copyright (c) HatScripts

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### shadcn/ui

`legal-search/frontend/src/components/ui/**` (24 files), installed by the shadcn CLI as configured
in `legal-search/frontend/components.json` and subsequently modified.

Origin: [shadcn-ui/ui](https://github.com/shadcn-ui/ui). MIT License, Copyright (c) 2023 shadcn.
The MIT text above applies to these files with that copyright line substituted.

---

## 2. Bundled dependencies with attribution or reciprocity obligations

These are not copied into the tree; they are installed as dependencies and end up in **built
artifacts** (container images, static exports, npm bundles). The obligations attach to distributing
those artifacts, not to distributing this source.

| Component | Licence | Obligation when a built artifact is distributed |
|---|---|---|
| `dompurify` | `MPL-2.0 OR Apache-2.0` (dual) | **This project elects Apache-2.0.** Recording the election here is what makes it an election |
| `lightningcss` (+ platform binaries) | MPL-2.0 | Unmodified. Source availability for the MPL files; no effect on surrounding code |
| `axe-core` | MPL-2.0 | Test-only; not in any distributed artifact |
| `@img/sharp-libvips-*` | LGPL-3.0-or-later | **Prebuilt native binaries** pulled by Next.js image optimisation. LGPL section 4 obligations (licence text, relinking) attach to a distributed image |
| `caniuse-lite` | CC-BY-4.0 | Attribution required. Data, not code |
| `greenlet` | MIT AND PSF-2.0 | Both notices |
| `prometheus-client` (Python) | Apache-2.0 AND BSD-2-Clause | Both notices; upstream ships its own NOTICE |
| `psycopg` | LGPL-3.0-only | **Dev/test only.** Listed so it is noticed if it ever moves into the runtime set |

## 3. Data

| Dataset | Where | Source | Terms |
|---|---|---|---|
| Swiss commune registry (2,110 entries) | `country-overlays/ch/municipalities.yaml`, and the generated `jur_ch_gemeinde_*` block of `platform-control/src/platform_control/seeds/reference/jurisdictions.yaml` | BFS *Amtliches Gemeindeverzeichnis der Schweiz*, snapshot 01.01.2026, via `agvchapp.bfs.admin.ch` | **[TO CONFIRM]** BFS/opendata.swiss datasets normally carry *"Freie Nutzung. Quellenangabe ist Pflicht"* — free reuse, **attribution mandatory**. Confirm the exact terms for this dataset and reproduce the required source line here |
| AS 554.510 (Kanton Zürich ordinance) | `document-intelligence/tests/fixtures/zh_as_554_510.pdf` | Kanton Zürich, official publication | Not protected: Art. 5 URG (SR 231.1) excludes official enactments from copyright. Basis already recorded at `document-intelligence/tests/test_marginalia.py:10` and `docs/adr/0041-geometric-pdf-marginalia.md:172` |
| RIS document catalogue (~50 rows of metadata) | `eval/documents.csv` | Rechtsinformationssystem des Bundes (RIS), Bundeskanzleramt Österreich | Open Government Data. The required attribution string is already recorded verbatim at `platform-control/src/platform_control/seeds/reference/compliance_policies.yaml:55` and should be reproduced in `eval/README.md` |
| LexFind acquisition evidence (JSON transcripts) | `docs/runbooks/evidence/**` | `www.lexfind.ch` (Schweizerische Staatsschreiberkonferenz / Sitrox / ZRI) | **No terms published.** Verified 2026-09-03 — see [brief §2.9](../README.md#29-lexfind-there-are-no-terms--established-empirically-2026-09-03). The underlying enactments are unprotected under Art. 5 URG |

## 4. Same-owner vendored content

`vendor/platform-contract.yaml` is a pinned copy of `clusters/prod/platform-contract.yaml` from
[`philipplukas/MacConfig`](https://github.com/philipplukas/MacConfig) — same copyright holder, so no
third-party obligation. That repository is itself unlicensed (`gh api`, 2026-09-03:
`"license": null`, `"private": true`) and should be settled alongside this one if the file is ever
published.

---

## Sources for each entry

Delete this section when adopting — it is the audit trail, not part of the notice.

- `circle-flags` — md5 comparison of `public/flags/{ch,at}.svg` against
  `node_modules/circle-flags/flags/`; licence from `node_modules/circle-flags/LICENSE.md` and
  `package.json` (`"license": "MIT"`, `"author": "HatScripts"`).
- `shadcn/ui` — `legal-search/frontend/components.json` (`"$schema": "https://ui.shadcn.com/schema.json"`);
  licence from `node_modules/shadcn/LICENSE.md` and `package.json` (`"license": "MIT"`, v4.1.1).
- Dependency rows — declared `license` fields in installed `node_modules/*/package.json` and in
  each `package-lock.json`; Python from installed `*.dist-info/METADATA`. Method and full tables in
  [dependency-licence-inventory.md](../dependency-licence-inventory.md).
- BFS — `country-overlays/ch/municipalities.yaml` header and
  `scripts/load_ch_gemeindeverzeichnis.py`.
- LexFind — `https://www.lexfind.ch/fe/assets/i18n/{de,fr,it}.json` and
  `https://www.lexfind.ch/robots.txt`, fetched 2026-09-03.
