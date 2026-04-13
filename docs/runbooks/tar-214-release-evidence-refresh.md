# TAR-214 - release evidence refresh

Owner: Platform lead
Last reviewed: 2026-04-13
Last verified: 2026-04-13
Applies to: **TAR-214** (release evidence refresh), **TAR-69** (phase 5 go / no-go), **TAR-77** (branch protection proof), **TAR-64** (dev smoke x2), **TAR-85** (remote MVP acceptance)

Use this checklist when you need to turn the merged implementation stack into a current release packet. The repo code is already landed; the remaining work is evidence refresh and synthesis.

## Current state

- The implementation stack is merged.
- `TAR-64` and `TAR-85` already have recent evidence, but the release packet needs the latest links re-attached in the current story.
- `TAR-77` is the stale piece because branch protection changed on 2026-04-13.
- `TAR-69` still needs a final summary comment that ties the refreshed evidence together.

## Exact next actions

1. Re-verify `TAR-77`.

- Capture the current GitHub `main` branch-protection screenshot.
- Capture one green `Release Readiness` run URL from the current `main`.
- If `release-readiness` and `scraping-qa` are no longer universally required, note that as policy drift in `TAR-77` and link it back to `TAR-70`.

1. Refresh `TAR-64`.

- Run two dev smokes on separate occasions or separate `main` SHAs.
- For each run, capture the UTC timestamp, run URL, final exit code, and Gate D `run_id` / `document_id` narrative.
- Attach the evidence to `TAR-64`, then link the refreshed runs from `TAR-69`.

1. Refresh `TAR-85`.

- Run `evidara workflow mvp-acceptance` against `dev` Cloud Run unless you operate staging.
- Capture stdout or `--json` output.
- Make sure the output includes `evidence_pack_version`.
- Attach the refreshed acceptance output to `TAR-85`, then link it from `TAR-69`.

1. Close the loop on `TAR-69`.

- Add a summary comment that links the refreshed `TAR-64`, `TAR-77`, and `TAR-85` evidence.
- Update the phase-5 go / no-go memo gate table with the current run URLs and artifact pointers.
- If the recommendation changes, record the date and owner in `TAR-69`.

## Evidence map

| Evidence item | What to attach | Where it lands |
|---|---|---|
| `TAR-77` | Branch-protection screenshot and one green strict `Release Readiness` run URL | `TAR-77`, then summary comment on `TAR-69` |
| `TAR-64` | Two dev smoke runs with Gate D details | `TAR-64`, then `TAR-69` |
| `TAR-85` | Remote MVP acceptance stdout or JSON with `evidence_pack_version` | `TAR-85`, then `TAR-69` |
| `TAR-69` | Single synthesis comment linking all refreshed evidence | `TAR-69` and the phase-5 memo |

## Risks

- Branch-protection drift can make older screenshots misleading even when checks are green.
- `TAR-64` and `TAR-85` can look valid in isolation but still be stale in the release packet if they are not re-linked.
- The release path stays fragile until the `TAR-69` summary comment and memo table are updated together.

## Related docs

- [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md)
- [Phase 5 evidence checklist](phase-5-evidence-checklist.md)
- [M5 evidence checklist](m5-evidence-checklist.md)
- [Linear M5 / Phase 5 handoff pack](linear-milestone5-handoff-pack.md)
