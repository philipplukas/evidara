# Licence drafts — provisional, unselected

> **Nothing in this directory is in effect. No licence has been chosen for this repository.**
>
> These files exist so that the choice can be made by *picking*, not by *writing*. They live under
> `docs/licensing/drafts/` and not at the repository root **on purpose** — a `LICENSE` at the root
> would look like a decision had been taken, and it has not been.

Read [the decision brief](../README.md) first. It has the provenance findings, the trade-offs, a
recommendation, and the five questions only the repo owner can answer.

## What is here

| File | For | Status |
|---|---|---|
| [`apache-2.0.LICENSE.txt`](apache-2.0.LICENSE.txt) | Option A. Copy to `/LICENSE` | Ready. Verbatim Apache-2.0 |
| [`NOTICE.txt`](NOTICE.txt) | Option A only. Copy to `/NOTICE` | Template — delete the guidance block |
| [`mit.LICENSE.txt`](mit.LICENSE.txt) | Option B. Copy to `/LICENSE` | Ready. Verbatim MIT |
| [`all-rights-reserved.LICENSE.txt`](all-rights-reserved.LICENSE.txt) | Option C. Copy to `/LICENSE` | Ready |
| [`bsl-1.1.PARAMETERS.txt`](bsl-1.1.PARAMETERS.txt) | Option D | **Parameters only — not a licence.** Three fields still need deciding |
| [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) | **All options.** Copy to `/THIRD-PARTY-NOTICES.md` | Ready except two `[TO CONFIRM]` items |
| [`manifest-license-fields.md`](manifest-license-fields.md) | All options | The exact edit for each of the 11 manifests + 4 API contracts |

## How each licence text was produced

Licence texts are not transcribed from memory. That is how a licence acquires a silent typo.

- **Apache-2.0** — the terms body (everything before `APPENDIX`) was taken verbatim from an
  installed copy in the tree (`node_modules/@swc/helpers/LICENSE`) and then **byte-compared, after
  whitespace normalisation, against a second independent copy** (`node_modules/rxjs/LICENSE.txt`).
  Both normalise to the same 9,129 characters. Only the appendix boilerplate — the part the
  licence explicitly instructs you to fill in — was written for this project.
- **MIT** — normalised body compared against `node_modules/circle-flags/LICENSE.md`; both are the
  same 1,020 characters. Only the copyright line differs.
- **BSL 1.1** — deliberately **not** reproduced. It is MariaDB's template and must be fetched from
  <https://mariadb.com/bsl11/>. Only the parameter block is drafted.
- **AGPL-3.0 / GPL-3.0 / MPL-2.0 / ELv2** — not drafted. If the owner heads that way, fetch the
  canonical text from the FSF, Mozilla or Elastic rather than accepting a copy from anywhere else.
  Each also has its own per-file header convention, which is a separate piece of work across
  ~2,100 files and eight code generators (see [brief §2.10](../README.md#210-generated-content-and-who-wrote-it)).

## The copyright line

Every draft says `Copyright (c) 2026 Philipp Guldimann` — the name on 1,093 of `main`'s
1,150 commits and the account that owns the GitHub repository. **Change it if the copyright should
sit with a company rather than a person.** That is a real decision with tax and assignment
consequences, and it is not one this brief can make; it also has to be made *before* publication,
because retro-assigning copyright after the fact is far more work than getting it right once.

## One thing to check before copying anything to the root

[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) is owed **whichever option is chosen**, and two
of its entries are still marked `[TO CONFIRM]`:

1. the exact BFS terms for `country-overlays/ch/municipalities.yaml`, and
2. whether the shadcn/ui components count as a "substantial portion" for MIT attribution purposes.

Neither blocks the choice. Both should be closed before anything is published.
