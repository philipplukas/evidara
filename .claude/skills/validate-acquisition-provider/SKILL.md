---
name: validate-acquisition-provider
description: Decide whether an acquisition provider's captures can be trusted — before citing them as coverage or acceptance evidence. Use when writing or reviewing a new provider, when a run reports success but you have not looked at the bytes, when a capture gate refuses something, or when asked "did this source actually work?". Covers the two acquisition gates and what neither of them answers, the exact refusal slugs, the abstention that turns a binary-manifestation gate into an unconditional pass, and the harness gates that self-skip while still reporting a pass.
---

# Validate an acquisition provider before trusting it

The failure this prevents: **a `200` that carries no law**, captured, counted, and
reported as coverage. That is the confident fabrication ADR-0033 exists to stop,
one layer earlier than the ADR was looking — at acquisition, not at reasoning.

It has happened twice, in ways that need *different* checks:

- **#631** — a ZH-Lex SPA served `200 text/html` for a statute URL, carrying the
  application shell. Well-formed HTML, real visible text, indexes fine.
- **#716** — `OpenAttachment?…` returned `200` with a **142-byte JavaScript
  redirect stub** where a PDF was expected.

`platform-control/src/acquisition_core/artifact_guard.py:1-42` states the split
explicitly, and says why neither module may grow the other's check.

## 1. Three gates, and the question each answers

| Module | Question | Refuses |
|---|---|---|
| `acquisition_core/artifact_guard.py` → `check_capture()` | "Are these the bytes I asked for?" | #716's stub |
| `acquisition_core/content_gate.py` → `assess_legal_text_density()` | "Does this text look like law?" | #631's nav shell |
| `document_intelligence/normalize/quarantine.py` → `assess_quarantine()` | "Did the *extracted text* turn out to be law?" | the empty and the not-law PDF (§3) |

The first two are acquisition-side and neither subsumes the other; for a binary
manifestation the first has to pass before the second is even meaningful. The
third runs one hop downstream, after normalisation, because judging PDF text
needs extraction. **A provider is validated when all three have an answer for it
— including "abstained", recorded.**

### `check_capture` — refusal slugs, in evaluation order

`artifact_guard.py:108-165`. The ordering is deliberate so the recorded reason
names the actual defect, not a downstream symptom — a 142-byte HTML stub declared
as a PDF must report `html_where_binary_expected`, never `below_size_floor`.

| slug | meaning |
|---|---|
| `empty_body` | zero bytes |
| `content_type_mismatch` | `declared_content_type` ≠ `expected_content_type` |
| `html_where_binary_expected` | payload opens as HTML where a binary format was expected — #716 exactly |
| `format_signature_missing` | no magic number in the first 1024 bytes (`_SNIFF_WINDOW`) |
| `below_size_floor` | shorter than `min_bytes` |

Magic numbers it knows (`_MAGIC_BY_FORMAT`, `:50-53`): `application/pdf` →
`%PDF-`, `application/zip` → `PK\x03\x04` / `PK\x05\x06`. **A format with no
registered signature returns `True`** (`has_format_magic`, `:94-105`) — the
function answers "does the evidence contradict the claim", and for a text format
there is nothing to contradict. Do not read a pass here as a format check that ran.

### `assess_legal_text_density` — and its abstention

`content_gate.py:91-148`. Counts legal-text markers
(`art.|artikel|§|abs.|ziff.|comma|lett.|lit.`, `:35-38`) in the *visible* text and
requires `DEFAULT_MIN_LEGAL_MARKERS = 3` (`:51`). Script/style-to-text ratio is
reported as corroboration but is deliberately **not** fail-closed.

**The trap.** `_ASSESSABLE_CONTENT_TYPES` is
`{text/html, application/xhtml+xml, application/xml, text/xml}` (`:56-58`). On
anything else — `application/pdf` above all — the gate returns
`is_legal_text=True, marker_count=0` and abstains (`:109-120`). That is the
correct behaviour and it means **a PDF provider that calls only this gate has no
content check at all, while its evidence bundle shows a green marker gate.**

`lexfind_api_provider.py:1371-1385` is the pattern to copy: it calls the abstaining
gate anyway, with an empty body, and records
`"legal_text_assessment": "abstained_binary_manifestation"` alongside
`"capture_guard": "passed"` — so the gap is *visible in the evidence* rather than
implied by silence.

## 2. Measure which gates your provider actually has

Do not trust a table — including this one. Re-measure:

```bash
grep -rn "check_capture\|assess_legal_text_density\|PortalHttpProviderBase" \
  platform-control/src/platform_control/services/*provider*.py
```

Measured on `main` at the time of writing, and the reason this skill exists:

- `check_capture` has **exactly one** call site in `src` —
  `lexfind_api_provider.py:1352-1357`.
- `assess_legal_text_density` has **exactly one** wiring for HTML providers —
  `portal_http_provider_base.py:120`, inherited by `CantonHttpProvider`,
  `BundeslandHttpProvider`, `RegioneHttpProvider`. Its skip reason is
  `no_legal_text_markers` (`:125`).
- `gemeinde_http_provider.py` inherits neither (its docstring at `:16` explains
  why it is not a `PortalHttpProviderBase` subclass). Its only content check is
  `content_type not in _CARRIABLE_CONTENT_TYPES` → `unsupported_manifestation_content_type`
  (`:370`, `:378`), and it captures `application/pdf` (`_BINARY_CONTENT_TYPES`, `:151`).
- `ris_ogd`, `fedlex_sparql`, `eur_lex_sparql`, `ch_court_decisions`,
  `legifrance`, `firecrawl`, `deterministic_http` call neither.

A provider with no gate is not "known good". It is unmeasured.

## 3. What the acquisition gates cannot answer — and who does

**A structurally valid PDF whose text is not law** — a cover sheet, an error
page, a consent interstitial — passes both acquisition gates.
`artifact_guard.py:35-43` says so in its own docstring and explains why the fix
does not belong there: judging PDF text needs extraction, extraction lives in
document-intelligence (ADR-0041), and a second PDF stack in platform-control is
the parallel-copy pattern that produced #675 and #713.

That is #731's last two assertions — a marker floor and a character floor over
*extracted* text — and they are answered downstream.

### The third gate: `document_intelligence/normalize/quarantine.py`

Merged as `0995ae5b` (#841). `assess_quarantine()` runs after normalisation, in
the same cheapest-and-most-specific-first order as `check_capture`, and returns a
reason from a **closed** taxonomy (`QUARANTINE_REASONS`, `:125-133`):

| reason | when |
|---|---|
| `no_text_layer` | `metadata["pdf_no_text_layer"] is True` — the scanned PDF. Exit is OCR, which is not implemented |
| `no_sections_extracted` | the handler ran and produced no blocks or no text — a defect in our logic |
| `below_content_floor` | fewer than `min_extracted_chars`, **or** fewer than `min_legal_markers` |

`normalize/pdf.py` still sets `pdf_no_text_layer` and *continues*, emitting an
empty IR that every structural check accepts; `assess_quarantine` is the line
that now stops it. Quarantine is terminal — no document, no sections, no
`document.processed` event.

**The floors, and why the numbers are not the acquisition ones:**

- `DEFAULT_MIN_EXTRACTED_CHARS = 200` (`:194`) — calibrated on the *shortest*
  real law, not the comfortable case: the smallest genuine document measured is
  871 characters, giving ~4x headroom, while an image-only PDF has 0.
- `DEFAULT_MIN_LEGAL_MARKERS = 1` (`:186`) — **not** `content_gate`'s 3, and the
  divergence is measured. A floor of 3 puts two real in-force municipal dog-tax
  ordinances *exactly on* it with zero headroom, and their third marker is the
  word `Artikel` inside LexFind's own change-table boilerplate — furniture, not
  legal structure. Strip the change table and both fall to 2 and are withheld.
  That is the municipal rung of ADR-0033's own dog question being deleted from
  the corpus by its own guard.

The rule that generalises: **a DI floor above acquisition's would withhold a
document acquisition already accepted as law.** The DI gate must never be
stricter than the upstream one.

Per-source narrowing goes through the bundle manifest's `di_overrides`
(`quarantine_min_extracted_chars`, `quarantine_min_legal_markers`, `:198-199`) —
ADR-0047: floors are per-source config, not global constants.

### The drift test is the mechanism, not the comment

Two modules in two languages now hold opinions about what law looks like, and the
thing keeping them honest is executable:
`document-intelligence/tests/test_quarantine.py::MarkerVocabularyDriftTests`
**reads `platform-control/src/acquisition_core/content_gate.py` at test time** and
fails on divergence. It pins three relations, and they are the ones to preserve:

- `test_every_upstream_marker_is_also_a_di_marker` — `LEGAL_MARKER_PATTERN`
  (`quarantine.py:144-149`) is a documented *superset*; its shared half must stay
  character-identical, alternative by alternative. The DI-only half adds the FR/IT
  equivalents of `Abs.` (`alinéa`, `cpv.`, `capoverso`, `let.`) a cantonal corpus
  needs. Deliberately excluded: bare `al.` and `ch.`, which match inside ordinary
  prose.
- `test_this_gate_is_never_stricter_than_acquisition` — pins the direction above.
- `test_di_exempts_exactly_the_content_types_content_gate_can_assess` —
  `UPSTREAM_ASSESSED_CONTENT_TYPES` (`:157`) must equal
  `_ASSESSABLE_CONTENT_TYPES`, so the two gates **partition** the modality space
  instead of overlapping or leaving a hole. `_assessed_upstream()` (`:343`) is why
  DI does not re-judge HTML: that would be a second opinion, not a gate.

If you change either vocabulary, this test is the thing that will tell you — and
it is the reason to change them in one place rather than two.

## 4. Setting the floor honestly

`min_bytes` is per source, and the number needs a measurement behind it, not a
guess. The one in the repo has one:
`platform-control/src/platform_control/schemas/source.py:211-214` —
`min_pdf_bytes: int = Field(default=2000, ge=0)`, because the smallest real
cantonal act measured in #716 was **84 740 bytes** (ZH Hundegesetz, 33 pages), so
2 000 sits far below a short ordinance while a 142-byte stub cannot pass.

Choosing a floor is a judgement call with one rule: **the floor must exclude the
stub you actually measured and admit the shortest real document you actually
measured.** If you have measured neither, you do not yet have a floor — say so
rather than picking a round number.

## 5. Prove it end to end, and read the skipped gates

The compose harness (see the `coverage-acceptance-loop` skill for the full loop)
is corpus-parameterised, and three of its gates **self-skip while still reporting
a pass** when you omit their flag:

```bash
bash scripts/ch-fedlex-compose-e2e.sh \
  --overlay <id> --template <template_id> --mode <mode> \
  --expect-content-type application/pdf \
  --expect-language de --expect-title '<regex>' \
  --query '<search term>' --out-dir <path>
```

- Without `--expect-content-type` a PDF corpus reports verdict `provider_failed`
  while working correctly (#744) — the default is `text/html`
  (`ch-fedlex-compose-e2e.sh:66`).
- Without `--expect-language` the indexed-language gate derives from the Fedlex
  `_de`/`_fr`/`_it` template-suffix convention and skips for any other corpus (#735).
- Without `--expect-title` the title gate falls back to a per-template lookup
  ending in a `.+` catch-all — it reports `title_ok=1` having asserted nothing (#744).

The harness records what it did not check in `checks.skipped_gates` in
`summary.json` (`:578-593`). **Read it before quoting the run.** A pass justifies
only the gates that actually ran; a skipped gate is unverified, not
verified-and-green.

`scripts/ch-fedlex-compose-e2e.sh` has no `--copy-evidence` and no `--url-pattern`
(its own comment at `:64-65` says so). Those flags live on
`scripts/ch-fedlex-fast-loop.sh` and `scripts/ch-bger-fast-loop.sh`.

## 6. Where a human decides, not you

**Pointing a crawler at a public-sector host is not routine, and no green gate
makes it routine.**

For LexFind specifically, what the repo actually establishes
(`lexfind_api_provider.py:31-38`, `:96-98`): the mirrored file is md5-identical to the
canton's own (`461c614535cb7b5aa33175904f7d3229`, both sides); `robots.txt`
declares no rules at all; requests were made one at a time, several seconds
apart, with an identifying User-Agent (`_USER_AGENT`, `:167`). What it does **not**
establish: that anyone confirmed terms of use or rate expectations with the
Schweizerische Staatsschreiberkonferenz. `source_blueprints.yaml:580-589` states
this for the full-corpus template — *"a real load on a public-sector API whose
terms we have not confirmed, so it is a deliberate operator act, not a nightly
default."*

Stop and ask before: raising `max_resources` or `max_documents` against a live
public host, enabling an enumeration strategy that sweeps a whole corpus, or
scheduling any of it. Those are operator decisions.

## Boundaries

- **Never weaken a gate to make a run pass.** Fix what it caught. #675 was first
  "fixed" by changing the aggregations to match a drifted index; the same reflex
  applied here would be lowering `min_bytes` under a stub.
- **Never record a skip without a reason.** `lexfind_api_provider.py:1358-1369` —
  an unexplained skip and a successful capture are equally useless to an
  operator reading the evidence to tell a broken source from an empty one.
- **A LIVE code key is not a corpus claim.** `lexfind_api_provider.py:691-692`
  says it directly: the readiness key says the *code* works; whether a corpus is
  accepted is the operator's config key, and every dog-axis template in
  `source_blueprints.yaml` still ships `enabled: false`. Do not read "3 cantons
  onboarded" as "3 cantons held" (`source_blueprints.yaml:470-497`).
- **A vocabulary lives in one place.** `artifact_guard.py:23-26` — the marker
  vocabulary and threshold belong to `content_gate` and nowhere else; two
  opinions about what law looks like is how they drift apart.

## Reference

- `platform-control/src/acquisition_core/artifact_guard.py` — byte-level gate, refusal slugs, and its own scope statement
- `platform-control/src/acquisition_core/content_gate.py` — marker gate, abstention set, refusal text
- `platform-control/src/platform_control/services/lexfind_api_provider.py` — the only provider calling both; the pattern for recording an abstention
- `platform-control/src/platform_control/services/portal_http_provider_base.py:120` — the shared HTML wiring
- `document-intelligence/src/document_intelligence/normalize/quarantine.py` and `tests/test_quarantine.py` — the third gate and the drift test that keeps it aligned with `content_gate`
- [ADR-0047](../../../docs/adr/0047-quarantine-unhandled-document-classes.md) — the closed quarantine taxonomy §3 implements (the ADR file still reads `Status: Proposed`; the code landed first)
- [ADR-0041](../../../docs/adr/0041-geometric-pdf-marginalia.md) — why PDF text judgement lives in document-intelligence
- `.claude/skills/coverage-acceptance-loop/SKILL.md` — the loop this validation sits inside
