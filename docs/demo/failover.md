# Demo failover plan (recording + manual fallbacks)

Owner: Demo engineer
Last reviewed: 2026-04-28
Status: **Skeleton.** Capture the recording and confirm the laptop playback path before T-1.

## Why this exists

A live demo against prod has tail-risk. The two failure modes that cost the most credibility are (a) prod hangs / errors mid-demo, and (b) network on the venue laptop is flaky. This plan documents a recorded fallback so the show goes on either way.

The demo flow itself is in [`script.md`](script.md). Everything below is the safety net.

## Available infrastructure (already in repo)

The Playwright suite supports recorded runs out of the box. From [`docs/runbooks/interaction-flow-validation.md:128–130`](../runbooks/interaction-flow-validation.md):

- Traces — `PLAYWRIGHT_TRACE=on`
- Videos — `PLAYWRIGHT_VIDEO=on`
- Canonical journey webm — emitted to `legal-search/frontend/screenshot-pack/cross-surface-journey.webm` when `SCREENSHOT_PACK_VIDEO_MODE=enabled`

The wrapper [`scripts/run-interaction-flow-local.sh`](../../scripts/run-interaction-flow-local.sh) sets all three when invoked with `--record`.

## What we will record

A run of [`legal-search/frontend/e2e/demo-queries.spec.ts`](https://github.com/philipplukas/evidara/blob/main/legal-search/frontend/e2e/demo-queries.spec.ts) against prod, executing the **same flow** as the live demo:

1. Hero query (`Art. 754 OR Verantwortlichkeit`)
2. Click into the top result
3. Walk the header / metadata / language badge
4. Switch to the `details` tab
5. (Optional) Apply one filter

The recording is **not** the smoke test — it is the smoke test running with video enabled. Two artefacts, one source of truth.

## Capture steps (run at T-2 days at the earliest)

```bash
cd legal-search/frontend

# 1. Verify the demo-queries spec is green against prod first.
PLAYWRIGHT_USE_REAL_BACKEND=true \
  NEXT_PUBLIC_API_URL=https://<prod-legal-search-api> \
  PLAYWRIGHT_EXTERNAL_BASE_URL=https://<prod-legal-search-frontend> \
  npx playwright test e2e/demo-queries.spec.ts

# 2. Record the canonical journey.
PLAYWRIGHT_USE_REAL_BACKEND=true \
  NEXT_PUBLIC_API_URL=https://<prod-legal-search-api> \
  PLAYWRIGHT_EXTERNAL_BASE_URL=https://<prod-legal-search-frontend> \
  PLAYWRIGHT_TRACE=on \
  PLAYWRIGHT_VIDEO=on \
  SCREENSHOT_PACK_VIDEO_MODE=enabled \
  npx playwright test e2e/demo-queries.spec.ts
```

The artefacts land under `legal-search/frontend/screenshot-pack/` and `legal-search/frontend/test-results/`. Copy:

- `legal-search/frontend/screenshot-pack/cross-surface-journey.webm` (or whatever the demo-queries spec writes — verify after capture)
- the corresponding `trace.zip` (for post-demo debugging if anything was off)

…to a known location on the **presentation laptop** (proposed: `~/Demos/evidara/<date>/`).

> The webm is operator-generated content for one demo. **Do not commit it** to the repo. Captures stay on the presenter's laptop and in shared cloud storage if the team wants to keep a record.

## Playback path

Verify on the presentation laptop **before** the demo:

1. Drag the webm into Quick Look (macOS) or VLC. It must play full-screen at the actual resolution of the projector.
2. Test the audio mute (the recording is silent — ensure the laptop does not unmute and play system sounds).
3. Verify keyboard shortcut to scrub: macOS Quick Look supports arrow keys; VLC supports `→`.
4. If the recording is > 60 seconds, mark a chapter at the deep-dive moment so the presenter can scrub there mid-stream.

## Failover triggers

The presenter watches for these and switches to the recording **without announcing it**:

| Trigger | Threshold | Switch |
|---|---|---|
| Search results spinner | > 5 seconds | Switch |
| Detail panel blank after click | > 3 seconds | Switch |
| 5xx error toast | Any | Switch |
| Browser network indicator | Sustained loading after click | Watch; switch on second occurrence |

The script in [`script.md`](script.md) "If X flakes, switch to Y" branches mirror these.

## What NOT to record / show

- Admin shell with operator session leaks (keep the cross-surface jump short; close the admin tab before any operator data appears)
- DevTools console (close it; an unrelated CORS warning would distract)
- Network tab with auth tokens (close it)
- Any of the 12 corpus docs that did not pass the [detail-view audit](detail-view-audit.md) — pick the one document that did

## Pre-T-1 checklist

- [ ] Recording captured on the same prod URL the demo will hit
- [ ] Recording plays full-screen on presentation laptop
- [ ] Backup queries from [`script.md`](script.md) verified individually (each one returns its expected top-1 doc)
- [ ] Presenter has run through the failover triggers once mentally
- [ ] If the venue has no internet, the recording is local on the laptop (not streamed)

## What this plan does NOT cover

- Actually rebuilding the prod environment if it is hard-down on demo day. That is an SRE / incident question, not a demo-failover question. If prod is hard-down for > 1 hour at T-30 minutes, cancel and reschedule rather than demoing the recording standalone.
- Handling a hostile question during the demo. That is a presenter-prep concern, out of scope here.
