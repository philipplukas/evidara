# Austrian RIS temporal validity

Status: implemented (#663). Companion to
[ch-fedlex-sparql-temporal-architecture.md](ch-fedlex-sparql-temporal-architecture.md),
which covers the CH federal equivalent (#661).

## Where the window comes from

The OGD-RIS REST API (`https://data.bka.gv.at/ris/api/v2.6/`) publishes the
validity window on every consolidated federal norm, inside the
application-specific metadata block:

```text
Data.Metadaten.Bundesrecht.BrKons.Inkrafttretensdatum      → in_force_from
Data.Metadaten.Bundesrecht.BrKons.Ausserkrafttretensdatum  → in_force_until
```

Both are already ISO-8601 in the JSON listing. `Inkrafttretensdatum` was present
on **540/540** norms sampled live (2026-07-19); `Ausserkrafttretensdatum` is
**omitted while the norm is still in force**, which is a meaningful absence and
is never filled in.

`Ausserkrafttretensdatum` is **inclusive** — the last day the version was in
force — and therefore matches `in_force_until` and is passed through unconverted.
Measured live 2026-09-03 against B-VG (Gesetzesnummer 10000138): Art. 11 ends
2024-04-30 and its successor begins 2024-05-01, Art. 15 ends 2024-02-26 and its
successor begins 2024-02-27 — one day apart, where an exclusive end-date would
make them equal. RIS's own point-in-time query agrees: `Fassung.FassungVom=2024-04-30`
returns the version whose end date IS 2024-04-30, not its successor. Sources
disagree with each other on this (LexFind's equivalent field is exclusive), so see
[boundary-contracts.md](boundary-contracts.md) "The in-force boundary" for the
convention and the per-provider table.

The same two values also appear in the per-document RIS XML as
`<absatz ct="ikra">` / `<absatz ct="akra">` — but there they are **DD.MM.YYYY**
(`24.04.1998`). Acquisition is therefore the better source, and the XML
normalizer reformats to ISO when it is the only source available.

## The population chain

Before #663 the window was written to
`metadata.extracted_metadata.in_force_from` / **`in_force_to`** and died there.
Three independent faults, each fatal alone:

1. **Wrong path** — the search projection coalesces
   `document.metadata.in_force_from` / `.in_force_until`, and never reads
   `metadata.extracted_metadata.*`.
2. **Wrong key** — `in_force_to` is not the contract vocabulary, which is
   `in_force_until`.
3. **Wrong format** — the value was left in RIS's DD.MM.YYYY form, which the
   ISO-8601 downstream chain (`resolveInForceState()`) cannot read. Fixing only
   the path and key would still have produced nothing usable.

The connected chain now is:

```text
RIS OGD listing (Inkrafttretensdatum / Ausserkrafttretensdatum, ISO)
  → ProviderResource.metadata.in_force_from / .in_force_until
  → RawArtifact.artifact_metadata.provider_metadata
  → bundle manifest extraction_hints
       in_force_from_hint / in_force_until_hint
  → DI document.metadata.in_force_from / .in_force_until   [field_provenance: manifest]
  → search projection in_force_from / in_force_until
  → resolveInForceState() answers instead of `unknown`
```

The RIS document XML supplies the same fields as a fallback with
`field_provenance` source `structured`; the acquisition hint wins when both
exist. **Hints are omitted, never defaulted.** The in-force model is four-valued
precisely so it can answer `unknown`; handing it a guessed date is the confident
fabrication ADR-0033 exists to prevent.

## Act-level status: RIS does NOT reproduce the Fedlex trap

PR #661 found that 3 Fedlex works whose `jolux:inForceStatus` says *No longer in
force* have an **open-ended newest consolidation** — so consolidation dates
alone report repealed law as currently in force. The obvious question for #663
was whether RIS has the same shape. Measured live rather than assumed:

**RIS does have an act-level relation signal**, distinct from the window:
`BrKons.NovellenBeziehung`, corroborated by `Kundmachungsorgan`. Across 540
sampled norms it takes exactly three states:

| `NovellenBeziehung` | Meaning | Count (n=300 sample) |
|---|---|---|
| *(absent)* | no amending act recorded | 149 |
| `aufgehoben durch` | repealed by | 82 |
| `zuletzt geändert durch` | last amended by | 69 |

**But the trap does not reproduce.** Three independent measurements:

| Test | Result |
|---|---|
| 300 norms, default ordering: repeal signal **and** open-ended window | **0** |
| 240 norms, two differently-drawn populations (recently-changed; sorted desc) | **0** |
| Act-level (the exact Fedlex shape): 27 acts, 11 repeal-signalled, newest version open-ended | **0** |

Per-act closure was total: repealed acts had **0** open-ended versions out of 4,
8, 32, 22, 16, 22, 4 and 22 versions respectively.

### Why the shapes differ

Fedlex models an *abstract work* with dated consolidations hanging off it, and
the newest consolidation of a repealed work may simply never receive a
`dateEndApplicability` — the repeal lives only on the work. RIS `BrKons` instead
publishes each norm **as a version that owns its own window**, and repeal closes
`Ausserkrafttretensdatum` on every version of the act. The window is therefore
self-sufficient in RIS in a way it is not in Fedlex.

### What we do with the signal

`NovellenBeziehung` is captured onto resource metadata as `amendment_relation`
(`repealed_by` / `last_amended_by`), with an unrecognised value reported as
`None` rather than bent onto a plausible guess — the same rule #661 applies to
unknown Fedlex enforcement-status codes. It is recorded as **corroboration, not
as an override**: unlike CH status `3`, it is not permitted to flip the in-force
verdict, because there is no measured case where it disagrees with the window,
and inventing an override would mean asserting something the data does not say.

### What this means for Austrian temporal confidence

This is a *good* finding, not a gap. Austrian federal temporal validity rests on
a single self-consistent signal that is universally populated
(`Inkrafttretensdatum` on 540/540) and reliably closed on repeal. Austria needs
no second act-level query to avoid reporting repealed law as current — the CH
corpus does. If a future sample ever turns up a repeal signal on an open-ended
window, that is the trigger to promote `amendment_relation` from corroboration
to override; the field is already captured so the evidence will be there.
