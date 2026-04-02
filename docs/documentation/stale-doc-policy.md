# Stale Documentation Policy

## Purpose

Define how Evidara identifies and handles stale documentation.

---

## What Counts as Stale

| Indicator | Applies to | Threshold |
|-----------|-----------|-----------|
| `Last verified` date is old | Runbooks | > 3 months |
| `Last reviewed` date is old | Runbooks | > 6 months |
| Links are broken | All docs | Any broken link |
| Required headings are missing | Component docs | Any missing heading |
| Describes features that don't exist | All docs | Any false claim |
| Contract examples fail validation | Contracts | Any validation failure |

---

## Detection

### Automated (continuous)

- Link checker catches broken links on every commit
- Component doc heading checker catches missing sections
- Schema validator catches stale example payloads
- AI PR review flags possible drift

### Manual (quarterly)

- Review all runbooks for `Last verified` date freshness
- Review component docs for accuracy against code
- Review testing docs for accuracy against actual tests
- Flag docs older than 6 months with no updates for review

---

## Handling Stale Docs

### Fix or Archive

When a stale doc is found:

1. **If the doc is still relevant:** update it to reflect current reality. Reset `Last reviewed` / `Last verified`.
2. **If the doc is no longer relevant:** archive it by moving it to a `docs/_archive/` directory with a note about why it was archived.
3. **Never silently delete** a doc — someone may be relying on it.

### Stale ≠ Wrong

A doc with an old review date is not necessarily wrong. It may be perfectly accurate but just needs verification. The `Last verified` date distinguishes "verified correct" from "probably still correct."

---

## Responsibilities

| Who | What |
|-----|------|
| PR author | Update docs affected by their change |
| PR reviewer | Check for missing doc updates (use the [review checklist](review-checklist.md)) |
| Team (quarterly) | Review runbook freshness, flag stale docs |

---

## What NOT to Do

- Do not create a "doc rotation" or formal doc ownership assignment — a 1–3 person team does not need this overhead
- Do not block PRs on doc freshness alone — flag and fix, don't gate
- Do not treat all old docs as stale — some docs (ADRs, architecture decisions) are intentionally static
