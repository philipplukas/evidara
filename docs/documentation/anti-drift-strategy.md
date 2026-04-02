# Anti-Drift Strategy

## Purpose

Define how Evidara prevents, detects, and recovers from documentation drift — the gap between what the code does and what the docs say it does.

## Core truth

Documentation will drift. The goal is not perfection — it is **fast detection and low-cost correction**.

---

## Three Layers of Defense

### Layer 1: Deterministic Checks (Automated, Blocking)

These run in pre-commit hooks and CI. They fail the build if violated.

| Check | What it catches |
|-------|----------------|
| Markdown lint | Formatting issues, broken syntax |
| OpenAPI validation | Invalid API specs |
| JSON Schema validation | Malformed schemas |
| Component doc headings | Missing required sections in component docs |
| Runbook metadata | Missing ownership and review dates |
| Doc link checker | Broken internal links |

**These are the floor.** They catch structural problems automatically.

### Layer 2: AI-Assisted Review (Automated, Advisory)

An AI reviews PRs using the [AI PR Review Prompt](ai-pr-review-prompt.md) and suggests missing doc or contract updates.

| What it catches | Example |
|----------------|---------|
| Code changed but docs not updated | Schema field added, no doc update |
| Contract changed but examples stale | Event schema changed, example payload not updated |
| Component behavior changed | New API endpoint, component doc not updated |
| Testing expectations changed | CI config changed, testing docs not updated |

**These are suggestions.** They flag likely gaps, but a human decides.

### Layer 3: Periodic Review (Manual, Scheduled)

A lightweight quarterly review of documentation freshness.

- Review `Last reviewed` and `Last verified` dates in runbooks
- Check that component docs reflect current state
- Verify that testing docs match actual test suites
- Update or archive docs that no longer apply

**This is the safety net.** It catches what automation misses.

---

## What Makes Docs Drift

| Cause | Mitigation |
|-------|-----------|
| Code changes without doc updates | AI review + PR checklist |
| Docs describe future state as current | Review checklist explicitly asks |
| Contract changes without example updates | CI validates examples against schemas |
| Runbooks go stale | `Last verified` date + quarterly review |
| New components added without docs | Component doc heading check fails on incomplete docs |
| Broken links accumulate | Automated link checker |

---

## Recovery

When drift is found:

1. Fix the doc, not the check
2. If the doc is wrong, update it to match current reality
3. If current reality is wrong, file an issue — do not "fix" the doc to describe a desired future state
4. Add a regression check if the drift category was not covered

---

## What NOT to Do

- Do not build a heavy doc review process — keep it lightweight
- Do not require docs before code in every case — sometimes code moves first, and that is fine as long as docs follow within the same PR or the next
- Do not treat doc drift as a crisis — treat it as routine maintenance
