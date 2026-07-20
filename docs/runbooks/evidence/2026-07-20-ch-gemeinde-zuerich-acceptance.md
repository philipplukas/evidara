# CH Gemeinde Zürich — ADR-0030 acceptance evidence (AS 554.510)

Date: 2026-07-20
Template: `ch/gemeinde_http_zh_stadt_hundevorschriften`
Provider: `gemeinde_http`
Environment: local compose (`compose-local`), every image built from `main` at
`8d3ff889`, fresh volumes, Alembic at `20260720_0023`
Machine summary: [`2026-07-20-ch-gemeinde-zuerich-acceptance.json`](2026-07-20-ch-gemeinde-zuerich-acceptance.json)

## Why this run exists

This is the first municipal source taken through the platform loop, and the
acceptance run ADR-0030 §5 requires before a provider's code key may move to
`live`. It is also the corpus ADR-0033's acceptance question is about — whether
a city can restrict where dogs go — so the document acquired here is the one the
whole thesis is measured on.

Until #743 this run was **impossible**: acceptance evidence required a live run,
a live run required the code key, and the code key required the evidence. It was
dispatched with `mode=acceptance`, which admits an `awaiting_evidence` provider
precisely so it can produce its own first evidence.

## Command

```bash
bash scripts/ch-fedlex-compose-e2e.sh \
  --template gemeinde_http_zh_stadt_hundevorschriften \
  --mode acceptance \
  --expect-content-type application/pdf \
  --jurisdiction-id jur_ch_gemeinde_261 \
  --authority-id auth_stadt_zuerich_sk \
  --query Hundegesetz \
  --max-resources 5
```

## Verdict: `pass`

Run `run_01ky04f3tmfrvxtcx69x8mmx40`, source `src_01ky04f3svshqmfgrwv9hgxgjg`,
version `sv_01ky04f3sv92f6q2j2bq5wsjqk`.

| Check | Value |
|---|---|
| `captured_count` | 1 |
| `content_type_match_count` (`application/pdf`) | 1 |
| `raw_artifact_count` | 1 |
| DI `accepted` / `processing` / `canonical_ready` | 1 / 1 / 1 |
| lifecycle `document.processed` | 1 |
| `search_hits` | 2 |

Both ADR-0030 keys were **shut** for this template at dispatch
(`enabled=false`, `readiness=awaiting_evidence`), as the mode intends. A pass
here is evidence for turning them; it does not turn them.

## Gates the harness did NOT verify

The harness reported these as skipped rather than passed (#744). They are listed
here because a `pass` is only justification for what actually ran:

- `title_ok` — the title regex is Fedlex-shaped and self-skips for this template
- `indexed_language_ok` — `expected_language()` derives from a `_de`/`_fr`/`_it`
  template suffix, which this template does not have

**Both were verified by hand against the live index instead**, and the result is
recorded here so the gap is closed rather than merely disclosed:

```
GET documents-000001/_search?q=document_id:doc_4wfmyd7td4a3m2gdhga407g8f5
  title:           "Vollzugsvorschriften zum Hundegesetz"   ← matches the portal
  language:        "de"                                      ← correct
```

## The quality gate that actually mattered: the Randtitel splice

#650 found the layout-aware PDF normaliser splicing right-margin Randtitel into
body text **in this exact document** — `"die Führung des *Organisation*
Hundeverzeichnisses"`. A pipeline that acquires and indexes a document while
corrupting its operative text is the "demo that lies convincingly" ADR-0033
exists to prevent, so this was checked directly rather than inferred from a
green verdict.

The document normalised into **9 sections**, each carrying its Randtitel as the
heading and clean body text:

```
--- Vollzugsvorschriften zum Hundegesetz
    vom 31. Mai 2017 … gestützt auf § 2 Hundegesetz vom 14. April 2008 …
--- Organisation
    Art. 1 1 Die Aufsicht über das Hundewesen, die Führung des
    Hundeverzeichnisses, die Prüfung der Hundehaltungsvoraussetzungen …
--- Abgabe an die Gemeinde und Kantonsbeitrag
--- Ermässigung Kursbesuch
--- Härtefall
--- Gebühren
--- Zuständigkeiten
--- Aufhebung bisherigen Rechts
--- Inkrafttreten
    Art. 8 Diese Vollzugsvorschriften treten am 1. September 2017 in Kraft.
```

`"die Führung des Hundeverzeichnisses"` is intact, with `Organisation`
correctly separated as the section heading. **The splice is absent on the real
document.**

Art. 6 (`Zuständigkeiten`) carries the provision ADR-0033's question turns on —
*"Anordnungen hinsichtlich Örtlichkeiten, die von Hunden nicht oder nur an der
Leine betreten werden dürfen"*.

## Searchability

`GET /v1/search?q=Hundegesetz` returns the document with a snippet drawn from
the acquired PDF, subtitled `Schweiz · Gesetz · Stadtkanzlei Stadt Zürich`.

An earlier run of the same loop returned `search_failed` because it was given
`--query Hundevorschriften`, a term that does not occur in the ordinance (the
title is *Vollzugs*vorschriften zum *Hundegesetz*). The harness was correct to
fail; the query was wrong, not the pipeline. Recorded because the failing bundle
exists and its verdict should not be mistaken for a pipeline defect.

## What this evidence does and does not support

**Supports:** moving `gemeinde_http` from `AWAITING_EVIDENCE` to `LIVE`. The
provider acquires a PDF-only municipal ordinance from the live portal, the
normaliser produces trustworthy article-level text, and the result is indexed and
searchable.

**Does not support:** enabling the template. That is the operator's config key,
flipped from the admin panel with this evidence attached, and it is a separate
decision from whether the code works.

**Does not generalise:** one commune, on one portal, with one document. The BFS
→ host registry is config (`communal_portals.yaml`), so adding a commune is a
data edit — but each new portal needs its own acceptance run. Coverage of ~2,110
Gemeinden remains out of scope (#584).
