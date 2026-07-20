# CH Gemeinde Zürich — ADR-0030 acceptance evidence (AS 554.510)

Date: 2026-07-20
Template: `ch/gemeinde_http_zh_stadt_hundevorschriften`
Provider: `gemeinde_http`
Verdict: **`pass`**, `skipped_gates: []`
Machine summary: [`…-acceptance.json`](2026-07-20-ch-gemeinde-zuerich-acceptance.json)
Harness-rendered bundle: [`…-acceptance-harness.md`](2026-07-20-ch-gemeinde-zuerich-acceptance-harness.md)

## What this evidence is for

ADR-0030 §5 requires an acceptance run before a provider's code key moves to
`live`. This is that run, and it is the first municipal source taken through the
platform loop rather than assembled by a script.

Until #743 the run was **impossible**: acceptance evidence required a live run,
a live run required the code key, and the code key required the evidence. It was
dispatched with `mode=acceptance` — the mode that exists to break that deadlock —
with **both ADR-0030 keys shut at dispatch** (`enabled: false`,
`readiness: awaiting_evidence`).

## Environment

Every image rebuilt from `main` at `be3d7a09`, on volumes removed immediately
beforehand in the same command chain, so the index contained no prior copy of
this document. Alembic at `20260720_0023`; publisher `nats`, artifact store `s3`.

```bash
bash scripts/dev-loop-stack.sh down && bash scripts/dev-loop-stack.sh up && \
bash scripts/ch-fedlex-compose-e2e.sh \
  --template gemeinde_http_zh_stadt_hundevorschriften \
  --mode acceptance \
  --expect-content-type application/pdf \
  --expect-language de \
  --expect-title 'Vollzugsvorschriften zum Hundegesetz' \
  --jurisdiction-id jur_ch_gemeinde_261 \
  --authority-id auth_stadt_zuerich_sk \
  --query Hundegesetz --max-resources 5
```

## Result

Run `run_01ky0g0ggh06w0229m19z7pw4a`, source `src_01ky0g0gchrqyfzxwd44c5vc74`,
version `sv_01ky0g0gcqr66a2hw2g9gcbdz7`, document
`doc_0bpbznskn0n6eksh5q3ec9namy`.

| Check | Value |
|---|---|
| `captured_count` / `content_type_match_count` (`application/pdf`) | 1 / 1 |
| `raw_artifact_count` | 1 |
| DI `accepted` → `processing` → `canonical_ready` | 1 / 1 / 1 |
| lifecycle `document.processed` | 1 |
| `search_hits` | **1** |
| `title_checked` / `title_ok` | 1 / 1 |
| `indexed_language_checked` / observed | 1 / `de` |
| **`skipped_gates`** | **`[]`** |

`skipped_gates: []` is the load-bearing line. The harness reports a gate that did
not run as *skipped* rather than folding it into the pass count (#744), and an
earlier attempt at this evidence carried two skipped gates — the title regex and
the indexed-language facet both self-skip for a template without a
`_de`/`_fr`/`_it` suffix. `--expect-language` and `--expect-title` (added in
#753 and here) arm them from the template's own declared data instead, so the
verdict now covers every gate rather than resting on a manual substitute.

## The quality gate that decided it

#650 found the layout-aware normaliser splicing right-margin Randtitel into body
text **in this exact document** — `"die Führung des *Organisation*
Hundeverzeichnisses"`. A pipeline that indexes a document while corrupting its
operative text is the demo-that-lies-convincingly ADR-0033 exists to prevent, so
this was checked directly rather than inferred from a green verdict.

The ordinance normalises into 9 sections, each carrying its Randtitel as the
heading with clean body text:

```
--- Organisation
    Art. 1 1 Die Aufsicht über das Hundewesen, die Führung des
    Hundeverzeichnisses, die Prüfung der Hundehaltungsvoraussetzungen …
```

`"die Führung des Hundeverzeichnisses"` is intact. **The splice is absent on the
real document.** An independent reviewer reproduced the raw defect with
`pdftotext -layout` on the live PDF and confirmed the indexed text is clean, and
separately confirmed the captured artifact's SHA-256 matches a direct download —
this was the live portal, not a fixture.

Art. 6 (`Zuständigkeiten`) carries the provision ADR-0033's acceptance question
turns on: *"Anordnungen hinsichtlich Örtlichkeiten, die von Hunden nicht oder nur
an der Leine betreten werden dürfen"*.

## What this evidence does NOT establish

Named explicitly, because the fidelity claim above covers one margin and it would
be easy to read it as a general one:

- **Bottom-margin footnotes were spliced into the body** at the time of this run
  — the same class of defect as #650, at a different margin. Filed as **#754**
  and fixed in #756; this bundle predates that fix.
- **The ordinance's own citation `554.510` is not indexed at all** — there is no
  legislative-identifier field on the documents mapping, so this law cannot be
  retrieved by its official number. Filed as **#755**.
- **Re-running against the same stack produces a duplicate document** rather than
  a new revision (**#757**). This run was on empty volumes precisely so
  `search_hits: 1` means one document.
- Completeness of articles, in-force/repeal status, and the provider's own
  metadata claims are not asserted by any gate.

## Scope

**Supports** moving `gemeinde_http` from `AWAITING_EVIDENCE` to `LIVE`: the
provider acquires a PDF-only municipal ordinance from the live portal, the
normaliser produces trustworthy article-level text, and the result is indexed and
searchable.

**Does not support** enabling the template. That is the operator's config key,
flipped from the admin panel with this evidence attached, and it is a separate
decision from whether the code works.

**Does not generalise.** One commune, one portal, one document. The BFS → host
registry is config (`communal_portals.yaml`), so adding a commune is a data edit —
but each new portal needs its own acceptance run. Coverage of ~2,110 Gemeinden
remains out of scope (#584).
