# Licensing decision brief

**Status: nothing is chosen. This page prepares a decision; it does not take one.**

Audited 2026-09-03 against `origin/main` at `59721399`. Every claim below is cited to a
`file:line` in this repository or to a live fetch made during the audit, with the fetch date.

> **Not legal advice.** The author is not a lawyer, and neither is the repo owner. Everything here
> is an engineering-provenance finding: *what is in the tree, what it declares, and what that
> constrains*. Where a finding creates a real legal question it is flagged as a question, not
> answered. Before a public release, the dependency and data findings in §2 are worth twenty
> minutes of a Swiss IP lawyer's time.

## Contents

- §1 [The premise, verified](#1-the-premise-verified) — and the two places it is already wrong
- §2 [Provenance findings](#2-provenance-findings) — what constrains the choice
- §3 [The options](#3-the-options) — trade-offs for *this* project
- §4 [Recommendation](#4-recommendation) — clearly marked as one
- §5 [Questions only the owner can answer](#5-questions-only-the-owner-can-answer)
- §6 [Adoption checklist](#6-adoption-checklist) — what to do once a choice is made

Supporting material:

- [Dependency licence inventory](dependency-licence-inventory.md) — every direct dependency of
  every surface, with its declared licence and how that was established.
- [`drafts/`](drafts/README.md) — the files each option would need, written out and unselected.

---

## 1. The premise, verified

The research memo's blocker holds: **there is no repo-wide licence.**

| Check | Result |
|---|---|
| `LICENSE` / `LICENCE` / `COPYING` / `NOTICE` / `UNLICENSE`, at root or in any component | **None.** Zero tracked files match `(^\|/)(licen[sc]e\|copying\|notice\|unlicense)` across all 2,103 tracked files. |
| `license` in any `package.json` (5 of them) | **Absent in all five.** All five are `"private": true`. |
| `license` in any `pyproject.toml` (5 of them — the memo counted 3) | **Absent in all five**, including `infra/coordinator` and `tools/zed-evidara-mcp`, which the memo missed. No `License ::` classifiers either. |
| `README.md`, `SECURITY.md`, `docs/index.md` | Say nothing about licensing. |
| GitHub repo metadata (`gh api repos/philipplukas/evidara`) | `"license": null`, `"visibility": "private"`, `forks_count: 0`. Fetched 2026-09-03. |

Under default copyright that means all rights reserved: nothing here is open source, and nothing can
be published as such until a choice is made.

**But the repo is not actually silent — it already makes two contradictory licence statements,
and the memo caught neither.** This is the single most important finding for the owner, because it
means part of the decision has been taken by accident, in two directions at once.

### 1a. One manifest *does* declare a licence, and it says Apache-2.0

`tools/zed-evidara-extension/Cargo.toml:6`

```toml
license = "Apache-2.0"
```

The crate is `publish = false` (line 5), so it has never gone to crates.io and no third party has
received it under that grant. But it is a declared licence on a sub-package of an otherwise
all-rights-reserved repo, and it is the only manifest in the tree that carries one.

### 1b. Three OpenAPI contracts declare the opposite — and with an invalid identifier

| File | Declaration |
|---|---|
| `contracts/api/legal-search.openapi.yaml:22` | `license: {name: Proprietary, identifier: UNLICENSED}` |
| `contracts/api/document-intelligence.openapi.yaml:16` | same |
| `contracts/api/document-intelligence-runtime.openapi.yaml:13` | same |
| `contracts/api/platform-control.openapi.yaml` | **no `license` block at all** — it is generated from the FastAPI app (ADR-0034), and FastAPI emits none |

Two problems, both cheap to fix and neither fixable by this lane (that would mean *setting* a
licence field, which is out of scope here):

1. **They disagree with `Cargo.toml` and with each other.** Four contracts, three saying
   `Proprietary`, one saying nothing, one crate saying `Apache-2.0`.
2. **`identifier: UNLICENSED` is not valid.** OpenAPI 3.1 requires `info.license.identifier` to be
   an SPDX *expression*; `UNLICENSED` is an npm convention with no SPDX registration. The
   spec-conformant way to say "no licence granted" is to omit `identifier` and leave only `name`,
   or to use `LicenseRef-Proprietary`.

Whatever the owner chooses, these four files have to end up agreeing with the root `LICENSE`.
[`drafts/manifest-license-fields.md`](drafts/manifest-license-fields.md) has the exact edits for
each option.

---

## 2. Provenance findings

`CONTRIBUTING.md:5` asserts *"This is a **clean-room implementation**"* and points at
[`docs/architecture/clean-room-principles.md`](../architecture/clean-room-principles.md). That
document's scope is narrower than the phrase suggests: it forbids copying **from prior
repositories** (the owner's proprietary predecessors) and explicitly *allows* "public framework
documentation". It says nothing about third-party open-source code, which is what a publication
review actually turns on.

So the audit asked the question the clean-room doc does not: **is anything in this tree someone
else's, and does the repo carry what that person's licence requires?**

Findings, worst first.

### 2.1 Two vendored third-party assets, byte-identical to upstream, with no attribution

`legal-search/frontend/public/flags/ch.svg` and `.../at.svg` are md5-identical to
`circle-flags@2.8.2`:

```text
f45a7dbf12930ac8ef8e9db2123feda5  legal-search/frontend/public/flags/ch.svg
f45a7dbf12930ac8ef8e9db2123feda5  node_modules/circle-flags/flags/ch.svg

33d39054f5c40c9e8c404101ccbc2aa6  legal-search/frontend/public/flags/at.svg
33d39054f5c40c9e8c404101ccbc2aa6  node_modules/circle-flags/flags/at.svg
```

`circle-flags` is **MIT, Copyright (c) HatScripts** (`node_modules/circle-flags/LICENSE.md`). MIT
requires that "the above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software." The repo carries neither. `circle-flags` is also
already a declared dependency (`legal-search/frontend/package.json`), so these two files are a
copy of something the surface already installs.

**This is not blocking and it is not hard** — one `THIRD-PARTY-NOTICES` entry fixes it, and
[a draft is written](drafts/THIRD-PARTY-NOTICES.md). It matters because it is the pattern: the
repo has copied-in third-party material and no place to record it.

### 2.2 The `shadcn/ui` components are copied-in third-party source, by design

`legal-search/frontend/components.json` is a shadcn registry config
(`"$schema": "https://ui.shadcn.com/schema.json"`), and 24 files live under
`legal-search/frontend/src/components/ui/`. shadcn/ui's whole model is that the CLI *writes the
component source into your repo* — you own and edit the copy. Many of these have been heavily
modified since (`button.tsx` carries a bespoke `ConsequenceTier` confirm-dialog wrapper that is
not upstream), but their origin is upstream.

`shadcn@4.1.1` is **MIT, Copyright (c) 2023 shadcn** (`node_modules/shadcn/LICENSE.md`).

Whether 24 modified components are a "substantial portion" is a judgment call. The cheap and
defensible answer is the same as §2.1: name it in `THIRD-PARTY-NOTICES`. **This does not constrain
the licence choice** — MIT-origin code can be redistributed under Apache-2.0, MIT, or a
source-available licence, with attribution preserved.

### 2.3 Unreferenced third-party *logos* — a trademark question, not a copyright one

`legal-search/frontend/public/` still holds the `create-next-app` scaffold assets:
`next.svg` (the **Next.js wordmark**), `vercel.svg` (the **Vercel triangle**), plus
`file.svg`, `window.svg`, `globe.svg`. A grep across `legal-search/frontend/src` and `e2e`
returns **zero references** to any of them.

Publishing another company's wordmark inside a repo licensed under one's own terms is the one
provenance issue here that is a *trademark* problem rather than a copyright one, and no licence
choice fixes it. **The fix is deletion, not attribution** — they are dead files. Flagged as a
follow-up rather than done here, because this lane is docs-only and `legal-search/frontend` may be
in another lane's tree.

### 2.4 `vendor/` — same owner, and already documented

`vendor/` holds exactly one tracked file: `vendor/platform-contract.yaml` (54 lines), whose header
says *"MacConfig owns this file"*. `README.md` documents the provenance properly — it is a pinned
copy of `clusters/prod/platform-contract.yaml` from
[`philipplukas/MacConfig`](https://github.com/philipplukas/MacConfig), with a CI-enforced version pin.

`gh api repos/philipplukas/MacConfig` (2026-09-03) returns `"private": true`, `"license": null`.
**Same copyright holder, so no third-party obligation** — but it is a second unlicensed repo whose
terms would need settling alongside this one if the file is ever published.

### 2.5 No third-party copyright headers or SPDX tags anywhere

A scan of all 2,103 tracked files (binaries excluded) for `Copyright`, `(c) YYYY`, `©`,
`SPDX-License-Identifier`, and the MIT incipit "Permission is hereby granted, free of charge"
found:

- **zero** `SPDX-License-Identifier` tags,
- **zero** MIT/BSD/Apache licence bodies,
- nine `Copyright` hits, **all** substantive references to the EU DSM **Copyright Directive**
  (2019/790) or to Swiss `Art. 5 URG` — i.e. domain content, not licence headers.

**Honest limit of this method:** a header scan finds *attributed* copies. It cannot detect a
header-stripped copy or a close paraphrase. What it does establish is that nobody vendored a
labelled third-party file and forgot about it, and that the repo has no existing header convention
to be consistent with.

### 2.6 Dependencies: nothing copyleft blocks a permissive choice — with three caveats

Full tables in [dependency-licence-inventory.md](dependency-licence-inventory.md). Summary of
**direct** dependencies:

| Surface | Direct deps | Copyleft / source-available in the direct set |
|---|---|---|
| `platform-control` | 18 runtime + 7 dev | **`psycopg[binary]` — LGPL-3.0-only. Dev group only.** Everything else MIT / Apache-2.0 / BSD-3. |
| `document-intelligence` | 10 runtime + extras | None. MIT / Apache-2.0 / BSD. |
| `tools/evidara-cli` | 3 runtime + 2 dev | None. |
| `legal-search/api` | 12 runtime + 14 dev | None. |
| `legal-search/frontend` | 20 runtime + 17 dev | **`dompurify` — `(MPL-2.0 OR Apache-2.0)`, dual.** |
| `platform-control/admin` | 15 runtime + 16 dev | None in the direct set. |
| `marketing` | 6 runtime + 15 dev | None in the direct set. |

**No AGPL, GPL, SSPL, BUSL or Elastic License appears anywhere in any surface, at any depth.**
The two named risks in the research memo are both absent from the tree: **Soda Core (ELv2)** is not
a dependency, and none of the **Laws.Africa GPL** stack is either. They constrain what the repo may
*adopt* later, not what it may license today.

The three caveats:

1. **`psycopg[binary]` is LGPL-3.0-only**, in `platform-control`'s dev group
   (`platform-control/pyproject.toml`, `[dependency-groups] dev`), used to drive the Testcontainers
   Postgres integration layer. LGPL constrains *distribution of a linked binary*; a dev-group
   test dependency is not shipped. **It does not constrain the licence choice.** It would if it ever
   moved into the runtime set — worth a note next to the dependency.
2. **`dompurify` is dual-licensed `MPL-2.0 OR Apache-2.0`** and is a direct runtime dependency of
   `legal-search/frontend`. Because it is a disjunction, the project may simply **elect
   Apache-2.0** and the MPL's file-level copyleft never engages. That election should be *recorded*
   (in `NOTICE` or `THIRD-PARTY-NOTICES`), not left implicit.
3. **Transitively, weak/file-level copyleft is present in every JS surface** and is normal for the
   Next.js toolchain: `lightningcss` (MPL-2.0, 13 platform packages), `axe-core` (MPL-2.0, test
   only), `@img/sharp-libvips-*` (**LGPL-3.0-or-later** prebuilt native binaries, 10 platform
   packages, pulled by Next.js image optimisation), and `caniuse-lite` (**CC-BY-4.0** — a data
   file, so attribution is owed if it is redistributed). None of these are modified, none are
   statically linked into first-party code, and **none constrains the licence of this repo's own
   source.** They constrain what a shipped *container image or bundle* must carry with it — which
   is a release-engineering task, not a licence-choice input.

### 2.7 The repo already behaves as if it intends a permissive licence

Two decisions on `main` were made *on licence grounds*, before anyone wrote a licence:

- `docs/adr/0037-binary-artifacts-and-layout-aware-pdf.md:115` — *"`PyMuPDF`/`fitz` was rejected on
  licensing (AGPL)"*, in favour of `pdfplumber` (MIT).
- `docs/adr/0005-search-strategy.md:24` — OpenSearch chosen as *"the open-source fork of
  Elasticsearch with an Apache 2.0 license."*

That is a consistent revealed preference for permissive-compatible dependencies. It does not decide
anything, but it means a permissive choice would ratify how the repo is already being built, and a
copyleft choice would be a change of direction rather than a continuation.

### 2.8 Data and fixtures — the memo's picture was wrong, and the real answer is better

The memo said `docs/runbooks/evidence/` holds "captured PDFs of Swiss legislation". **It does not.**
That tree is 5.8 MB of **JSON API transcripts** — run states, readiness reports, captured-resource
manifests, search responses. Zero PDFs.

**The repository contains exactly one tracked PDF**, and its provenance is already documented in
the code that uses it:

`document-intelligence/tests/fixtures/zh_as_554_510.pdf` (217 KB) — the real Zurich ordinance AS
554.510. `document-intelligence/tests/test_marginalia.py:10` and
`docs/adr/0041-geometric-pdf-marginalia.md:172` both state the basis:
*"Swiss official texts carry no copyright (Art. 5 URG)."* Art. 5 of the Swiss Copyright Act (SR
231.1, *Nicht geschützte Werke*) excludes official enactments — laws, ordinances, treaties — from
protection. A cantonal *Verordnung* is squarely within that. The file's own metadata
(`/Creator: Adobe InDesign`, `/Producer: … QuoVadis Trustlink Switzerland`) is consistent with an
official Swiss publication. **This one is clean, and the repo already reasoned about it correctly.**

Two data items are *not* covered by that reasoning:

- **The Swiss commune registry.** `country-overlays/ch/municipalities.yaml` (10,702 lines, 2,110
  communes) records its source honestly — *"Source: BFS Amtliches Gemeindeverzeichnis der Schweiz
  (01.01.2026)"* — and is regenerated by `scripts/load_ch_gemeindeverzeichnis.py` from
  `agvchapp.bfs.admin.ch`. It is **redistributed here with no licence and no attribution string
  recorded anywhere.** BFS datasets are normally published on opendata.swiss under terms of the
  *"Freie Nutzung. Quellenangabe ist Pflicht"* family — free reuse, **attribution mandatory**. The
  repo already has the machinery to express exactly that (`attribution_required` /
  `attribution_text` on a compliance policy), and does not use it here. Cheap fix; should be done
  before the file is published.
- **The Austrian eval catalogue.** `eval/documents.csv` holds ~50 rows of RIS metadata (titles,
  ELI URIs, BGBl numbers). Austrian §7 UrhG excludes official works, and RIS is an explicit OGD
  programme whose attribution string the repo already carries verbatim at
  `platform-control/src/platform_control/seeds/reference/compliance_policies.yaml:55`. `eval/README.md`
  does not reproduce it. Minor.

### 2.9 LexFind: there are no terms — established empirically, 2026-09-03

This is the item the brief asked to be nailed down, and it now is.

What the repo knew before today: `platform-control/src/platform_control/services/lexfind_api_provider.py:97`
records that *"`robots.txt` declares no rules at all — nothing is disallowed"*, verified 2026-07-22.
That is a robots posture. **Nothing in the repo records LexFind's terms of use, because the repo
never checked.** Re-verified today, still true:

```text
$ curl https://www.lexfind.ch/robots.txt          # 200, 2026-09-03
# See http://www.robotstxt.org/robotstxt.html for documentation on how to use the robots.txt file
```

That is the entire file. One comment line, no directives.

`www.lexfind.ch` is an Angular SPA: `/fe/de/impressum`, `/fe/de/nutzungsbedingungen`,
`/fe/de/datenschutz` and `/fe/de` all return the **same 21,595-byte shell**, so a static fetch or a
naive crawler sees no legal text at all. The audit went to the source of truth instead — the app's
own translation bundle, `https://www.lexfind.ch/fe/assets/i18n/{de,fr,it}.json`, fetched
2026-09-03. The result:

- The complete set of `info_page` keys, **identical in de, fr and it**, is exactly three:
  `about`, `contact`, `disclaimer`. There is no fourth page.
- The strings `Nutzungsbedingungen`, `Impressum`, `Urheberrecht`, `Lizenz`, `Copyright`,
  `Datenschutz`, `AGB` are **absent from the entire bundle**, in every language. There is no English
  bundle.
- `info_page.about.text` says who runs it: *"Das Portal wird im Auftrag der Schweizerischen
  Staatsschreiberkonferenz von Sitrox betrieben. Für die juristische Arbeit zeichnet das Zentrum
  für Rechtsinformation – ZRI verantwortlich."*
- `info_page.disclaimer.text` is an **accuracy** disclaimer and nothing else: *"LexFind übernimmt
  keine Gewähr für die Richtigkeit der Angaben. Die Daten wurden den Erlasstexten der Kantone und
  des Bundes entnommen."* No grant, no restriction, no reservation of rights.

**Conclusion: LexFind publishes no terms of use, no copyright notice, no licence and no robots
restriction.** The finding is a genuine null, and it is now recorded with a method someone can
repeat.

What that does and does not settle:

- **The underlying texts are not the issue.** They are cantonal and federal enactments — Art. 5 URG
  excludes them from copyright, and LexFind's own disclaimer confirms it is reproducing them
  (*"den Erlasstexten der Kantone und des Bundes entnommen"*), not authoring them.
- **The open question is the compilation, not the contents.** Switzerland has **no sui generis
  database right** (unlike the EU), so a mere collection of unprotected texts attracts nothing. A
  collection can attract copyright under **Art. 4 URG** only where the *selection or arrangement*
  is an intellectual creation with individual character. Whether LexFind's systematic ordering
  crosses that bar is a question for a lawyer — but it is a narrow one, and the repo's own product
  principle already mitigates it: `lexfind_api_provider.py:22-25` states that a mirror is admissible
  *"only while we keep proving it equals the source"*, and `verify_mirror_fidelity` proves the
  bytes are the canton's own, not LexFind's rendering.
- **Silence is not a grant.** No terms means no permission was given *and none was refused*. If the
  LexFind provider is ever published as the first open-source LexFind client, the defensible move
  is a short courtesy note to `info@lexfind.ch` (the address the site itself publishes) rather than
  a licence assertion.

**Gap this exposes, and it belongs to the acquisition lane, not this one.** The cantonal
jurisdictions carry **no compliance policy at all**:

- `compliance_policies.yaml` defines four policies: `cp_ch_fedlex_open_data`, `cp_at_ris_ogd`,
  `cp_ch_court_decisions`, `cp_ch_municipal`. **There is no LexFind policy.**
- `jurisdictions.yaml:20-24` — `jur_ch_zh` (and every other canton) has **no
  `compliance_policy_id`**; only `jur_ch`, `jur_ch_federal` and the AT root carry one.
- `run_service.py:1725` — `if jurisdiction is None or jurisdiction.compliance_policy_id is None:
  return None`. There is **no parent fallback**.

So every LexFind acceptance bundle in `docs/runbooks/evidence/` was produced with **no rate policy,
no robots mode, and no attribution block** — not the wrong one, none. That is arguably the *safe*
failure (nothing false is asserted), but it means the platform's own compliance model has never
been applied to its current lead provider.

### 2.10 Generated content, and who "wrote" it

Two provenance considerations that are not about third parties.

**Machine-generated files carry no independent authorship** and should be regenerated rather than
relicensed. The tree's generated surfaces, by declared banner:

| Generated artefact | Generator |
|---|---|
| `contracts/api/platform-control.openapi.yaml` | `scripts/generate_platform_control_contract.py`, from the FastAPI app (ADR-0034) |
| `legal-search/frontend/src/lib/api/generated/**` (68 files) | orval v7.21.0 |
| `legal-search/api/src/lib/document-intelligence/generated/**` (9 files) | orval v7.21.0 |
| `platform-control/admin/src/lib/api/generated/**` | openapi-typescript |
| `scripts/opensearch/documents-index.mapping.json` | `npm run mapping:generate` |
| `country-overlays/ch/municipalities.yaml` | `scripts/load_ch_gemeindeverzeichnis.py` (see §2.8) |
| the `jur_ch_gemeinde_*` block of `seeds/reference/jurisdictions.yaml` | `scripts/generate_ch_municipality_seeds.py` |
| `document-intelligence/dbt/models/**` source contracts | `document_intelligence.bootstrap.render_source_contracts` |
| `legal-search/frontend/src/lib/subdivision-icons` | `npm run generate:icons` |

None of these needs a licence header. All of them will *inherit* whatever the root `LICENSE` says,
which is the correct outcome — but it is worth knowing that a licence header sprinkler script would
be fighting eight generators.

**Authorship is mixed, and it is not all human.** `git shortlog -sne HEAD`, over the 1,150 commits
on `main` (the repo squash-merges, so `main` is the authoritative history):

| Author | Commits on `main` |
|---|---|
| Philipp Guldimann (two identities) | 1,093 |
| `Claude <noreply@anthropic.com>` | 51 |
| `Copilot` | 4 |
| `coderabbitai[bot]` | 2 |

About 5% of `main`'s commits carry a non-human author line — 13% if unmerged branches are counted
too (`--all` adds `copilot-swe-agent[bot]` and `github-actions[bot]`). There is **no CLA and no DCO** in the repo
(`.github/` holds `CODEOWNERS`, templates and workflows; no sign-off is required by
`CONTRIBUTING.md`). For a single-owner project this is fine — the owner directed all of it, and
`README.md` already frames the project as *"primarily a single-author project"*. It becomes a real
question only if outside contributions are accepted (see §5, Q3), and it is worth knowing that some
jurisdictions treat purely machine-generated output as uncopyrightable, which weakens — it does not
void — the enforceability of a copyleft licence over those specific hunks.

---

## 3. The options

Four families, judged against *this* repo: a private, single-author, seven-surface monorepo whose
most publishable artefact
([`WorkflowCommandEnvelope`](../adr/adr-0022-agentic-cli-workflow-control-surface.md))
contains no domain content at all, and whose commercial model is undecided.

### 3.1 Permissive — Apache-2.0 or MIT

The default for anything intended to be adopted.

**Apache-2.0 vs MIT is not a style question for this project.** Three differences matter here:

| | Apache-2.0 | MIT |
|---|---|---|
| **Express patent grant + termination** (§3) | Yes — contributors grant patent rights, and a user who sues for patent infringement loses their grant | None. Patent position is implied at best |
| **Trademark reservation** (§6) | Explicit — "Evidara" is not licensed with the code | Silent |
| **Attribution mechanism** | `NOTICE` file, propagated (§4d) | Copyright line in every copy |
| **Corporate adoption** | Approved by default at most legal departments | Also fine, but patent-review-sensitive buyers ask |
| **Length** | 202 lines | 21 lines |

For a **platform** — as against a utility library — the patent grant is the substantive argument.
This repo does non-obvious things: geometric marginalia partition (ADR-0041), the two-key
enablement lock (ADR-0030), coverage-as-a-denominator (ADR-0042/0048), `side_effect_level` on a
workflow envelope (ADR-0022). Apache-2.0 §3 gives adopters certainty that neither the project nor
its contributors will later assert a patent against them, and gives the project the defensive
termination clause in return. MIT gives neither side anything on patents. §6 also matters if
"Evidara" is ever a product name: MIT's silence means a fork could keep using the mark.

MIT's real advantages are brevity and the fact that it is the lingua franca of the npm ecosystem
this repo's frontends live in. For a single 155-line JSON Schema, that is a good trade. For a
platform, it is not.

**Cost of permissive:** a competitor may run the platform as a service and owes nothing back.

### 3.2 Weak copyleft — MPL-2.0 or LGPL-3.0

File-level (MPL) or library-level (LGPL) reciprocity. Modifications to *these* files come back;
everything built alongside stays private.

MPL-2.0 is the better-behaved of the two for a polyglot monorepo — the unit is the file, so a
consumer can combine it with proprietary code without contaminating anything, and `dompurify` and
`lightningcss` already sit in the tree on those terms without incident.

**But it fits the wrong shape of contribution here.** MPL's reciprocity captures *improvements to
the files you shipped*. The thing a competitor would take from this repo is not a patched
`artifact_guard.py`; it is the **architecture** — the loop, the lock, the refusal vocabulary — and
no copyleft licence reaches that. MPL buys real protection for a library and mostly ceremony for a
platform.

### 3.3 Strong copyleft — GPL-3.0 or AGPL-3.0

AGPL is the only licence in this list that closes the "run it as a service and give nothing back"
hole, which is precisely the hole a hosted legal-search platform has.

**Three concrete costs, and the third is the one that decides it:**

1. **It would contradict the repo's own decisions.** ADR-0037 rejected `PyMuPDF` *specifically
   because* it is AGPL (`0037-binary-artifacts-and-layout-aware-pdf.md:115`). Adopting AGPL after
   rejecting a dependency on AGPL grounds is a defensible change of mind, but it needs saying out
   loud, in an ADR.
2. **It shrinks the adoption surface to near zero** for the audience the memo identified. The
   Skills-over-MCP WG and the MCP Tasks extension will not take an AGPL schema proposal. Law firms'
   and legal-tech vendors' engineering orgs commonly have blanket AGPL bans.
3. **AGPL is a compatible-licence problem for a *platform*, not for a *library*.** AGPL §13
   triggers on network interaction with a modified version. `legal-search/api` and
   `platform-control` are network services *by design*. That is the point, and it is also the risk:
   an AGPL platform means a customer running a private fork with one changed constant owes source
   to their own users. For a product that sells to law firms, that is a sales conversation on every
   deal.

If the goal is "publish it and stop anyone monetising it", AGPL does the job. If the goal is "get
the vocabulary adopted", it defeats it.

### 3.4 Source-available — BSL 1.1 or Elastic License 2.0

Not open source (neither is OSI-approved), and both should be understood as *commercial*
instruments.

**BSL 1.1** is a parameterised template — the licensor fills in an **Additional Use Grant** (what
non-production or small-scale use is permitted), a **Change Date** (typically +4 years), and a
**Change License** (usually Apache-2.0), after which each release converts automatically. It is
what a company adopts when it wants source visibility and no hosted competitor, and it converts to
real open source on a timer. MariaDB, HashiCorp (2023), Sentry.

**ELv2** is simpler and blunter: you may do anything except (a) provide it to third parties as a
managed service, (b) circumvent licence keys, (c) remove licensing/attribution. No conversion date.
Elastic, and — as the memo flagged — **Soda Core as of v4**.

**Where this genuinely fits this repo:** if the platform is the commercial product, BSL over the
platform is the honest expression of that. The Change Date makes it a promise rather than a
withdrawal.

**Where it does not:** a source-available licence on `WorkflowCommandEnvelope` would be
self-defeating. Nobody adopts a schema they cannot use in production.

### 3.5 Dual licensing — the option the memo's own conclusion points at

Not a fifth licence but a **split**, and it is the only option that lets the two goals coexist.

The memo's strongest publishable candidate is `contracts/schemas/workflow-command-envelope.schema.json`
(155 lines, JSON Schema 2020-12, **zero domain content**) plus its reference implementation
`tools/evidara-cli/src/evidara_cli/envelope.py` (126 lines). Its stated value is *adoption* — a
proposal to a standards WG. Its value is destroyed by any licence that makes adoption expensive.

Meanwhile the platform — 2,000+ files, seven surfaces, the Swiss corpus machinery — has entirely
different economics and no adoption goal at all.

Two shapes, and they are not equally good:

| Shape | What it means | Verdict for this repo |
|---|---|---|
| **Per-directory split in one repo** | e.g. `contracts/` + `tools/` permissive, everything else proprietary or BSL, expressed as a root `LICENSE` plus a per-directory `LICENSE` | Cheap, no repo surgery. But mixed-licence monorepos are genuinely confusing, and `contracts/api/*.openapi.yaml` describes the *proprietary* services — the boundary is not where the directory boundary is |
| **Extract the publishable part to its own repo** | `workflow-command-envelope` gets its own repo under Apache-2.0; this repo keeps whatever the owner chooses | The memo's own recommendation 3. Clean, no ambiguity, and the extracted repo is ~280 lines |

A third variant — **the same code under two licences at once** (open-source + a paid commercial
exception, the MySQL/Qt model) — is the classic dual-licensing business model. It is viable here
*only* if the owner is willing to require a CLA from every outside contributor, because you cannot
sell a proprietary exception to code you do not wholly own. See §5, Q3.

---

## 4. Recommendation

> **This is a recommendation, not a decision.** It is the engineering-provenance-optimal answer;
> it is explicitly *not* informed by the owner's commercial intentions, which the author does not
> know. If §5's answers point elsewhere, §5 wins.

**Recommended: a two-part split.**

**(a) Extract `WorkflowCommandEnvelope` to its own repository under Apache-2.0.**

- `contracts/schemas/workflow-command-envelope.schema.json` + `envelope.py` + ADR-0022 as rationale.
- ~280 lines total, no domain content, nothing to strip but a `$id` and two example strings.
- Apache-2.0 rather than MIT, for the reasons in §3.1: it is a *specification with a reference
  implementation*, the audience is standards bodies and corporate adopters, and the patent grant is
  what makes `side_effect_level` safe for someone else to implement.
- Nothing in §2 blocks this: the two files have no third-party ancestry, no vendored assets, no
  copyleft dependency (`envelope.py` imports only the standard library and the schema is
  self-contained).
- This unblocks the memo's recommendation 3 without touching the platform's licence at all.

**(b) Leave the platform explicitly all-rights-reserved *for now*, and say so out loud.**

- Not because proprietary is right — because **"undecided" and "all rights reserved" are the same
  legal state, and only one of them is honest.** A root `LICENSE` reading "Copyright (c) 2026
  Philipp Guldimann. All rights reserved." plus one sentence in `README.md` costs nothing, reverses
  freely, and removes the ambiguity that currently makes every publication question unanswerable.
- It also lets the four contradictory declarations in §1a/§1b be reconciled *today*, on a decision
  that is not really a decision.
- The real platform choice — permissive, BSL, or nothing — can then be made when there is a
  commercial model to make it against, which is §5's Q1 and is not an engineering question.

**Explicitly not recommended:**

- **AGPL**, for the three reasons in §3.3 — and particularly because it would silently reverse
  ADR-0037's stated reasoning without an ADR.
- **A per-directory split inside this repo** (§3.5, shape 1). The boundary does not fall where the
  directories do, and a mixed-licence monorepo with no `LICENSE` today would be trading one
  ambiguity for a subtler one.
- **Publishing anything at all before §2.1 and §2.3 are cleared.** They are an afternoon: one
  `THIRD-PARTY-NOTICES` file and one `git rm` of five dead scaffold SVGs.

---

## 5. Questions only the owner can answer

The recommendation above is contingent on all five. Each changes the answer.

**Q1. Is the platform the product, or is the corpus?**
If Evidara sells *access to a corpus assembled by the platform*, the platform's licence barely
matters commercially and permissive is nearly free. If Evidara sells *the platform*, then §3.4's
BSL is the honest instrument and permissive gives it away. ADR-0033's framing — *"a thorough data
platform for law makes AI use cases easy, so the deliverable is the loop"* — reads like the second,
but that is a bet about engineering, not a statement about revenue. `docs/product/value-proposition-canvas.md:97`
records the revenue model as an open `[gap]`. **This question is upstream of every other one here.**

**Q2. Is there a competitor you are specifically defending against, and does it self-host?**
Copyleft only bites a competitor who *distributes*. If the threat model is an incumbent (Swisslex,
Weblaw, Noxtua — all named in `docs/product/value-proposition-canvas.md`) running a hosted service,
GPL does nothing and only AGPL reaches it. If the threat model is nobody in particular, copyleft is
pure adoption cost.

**Q3. Are outside contributions wanted?**
`README.md` currently says *"primarily a single-author project — issues and discussion are more
useful than large unsolicited pull requests."* If that stays true, no CLA/DCO is needed and §2.10's
mixed authorship never matters. If contributions become wanted — and especially if the
sell-an-exception model in §3.5 is ever attractive — a CLA becomes mandatory **before** the first
outside PR, not after, because you cannot retroactively acquire rights from a contributor who has
moved on.

**Q4. Should the corpus tooling and the platform share a licence?**
The acquisition providers (`lexfind_api_provider.py`, `gemeinde_http`, `ch_court_decisions`) are the
part with genuine standalone value — per the memo, publishing the LexFind provider would be the
**first open-source LexFind client anywhere**. They are also the part most entangled with the
platform's models and events. If they should be publishable separately, that is an extraction
project with an architectural cost, and it wants an ADR before it wants a licence.

**Q5. Is "Evidara" going to be a trademark?**
If yes, Apache-2.0 §6 (§3.1) becomes a positive reason to prefer it over MIT, and §2.3's dead
Next.js and Vercel logos should be deleted immediately rather than eventually — a repo that
publishes someone else's wordmark while asserting its own mark is in a poor position.

---

## 6. Adoption checklist

Once a choice is made, this is the whole job. [`drafts/`](drafts/README.md) has every file
pre-written.

1. Add the chosen `LICENSE` at the repo root — copy from
   [`drafts/`](drafts/README.md).
2. If Apache-2.0: add `NOTICE` at the root too
   ([`drafts/NOTICE.txt`](drafts/NOTICE.txt)) and keep it short. A NOTICE file propagates.
3. Add `THIRD-PARTY-NOTICES.md` ([draft](drafts/THIRD-PARTY-NOTICES.md)) — this is owed
   **regardless of which licence is chosen**, because of §2.1 and §2.2.
4. Set the `license` field in all five `package.json` and all five `pyproject.toml`, and reconcile
   `tools/zed-evidara-extension/Cargo.toml:6` — exact edits in
   [`drafts/manifest-license-fields.md`](drafts/manifest-license-fields.md).
5. Fix `info.license` in the three hand-authored OpenAPI specs (§1b), and — if
   `platform-control.openapi.yaml` should carry one — add it to
   `platform-control/src/platform_control/openapi.py` and **regenerate**, never by hand
   (ADR-0034; `scripts/check-platform-control.sh` fails the build on drift).
6. Delete the five unreferenced scaffold SVGs in `legal-search/frontend/public/` (§2.3).
7. Record the BFS attribution for `country-overlays/ch/municipalities.yaml` (§2.8) — the
   `attribution_required` / `attribution_text` machinery already exists.
8. Open an ADR recording the decision and its reasoning. If the choice is copyleft, the ADR must
   address ADR-0037's contrary reasoning (§3.3).
9. Update `CONTRIBUTING.md`: the clean-room paragraph should point at
   `THIRD-PARTY-NOTICES.md` for what the repo *does* legitimately carry from third parties, so the
   clean-room claim stops reading as "nothing here is anyone else's".
