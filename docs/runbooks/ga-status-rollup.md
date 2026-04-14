# GA status rollup

Owner: Platform / GA
Last reviewed: 2026-04-14
Last verified: 2026-04-14
Applies to: local GA lane synthesis, operator handoff, and `TAR-160` assembly

## Purpose

This runbook defines the local machine-readable GA rollup artifact used to reduce manual
cross-doc synthesis.

It is intentionally small:

- one local script
- one JSON rollup
- one place to see lane freshness, evidence anchors, blockers, and next actions

It does **not** replace the lane notes. It summarizes them.

Use it when you want a current local answer to:

- which GA lanes are still active
- which evidence is freshest
- what the open blocker is for each lane
- what the next operator move should be

## Command

From repo root:

```bash
python3 scripts/ga_status_rollup.py > /tmp/ga-status-rollup.json
```

Optional markdown view:

```bash
python3 scripts/ga_status_rollup.py --format markdown
```

Optional file output:

```bash
python3 scripts/ga_status_rollup.py --output /tmp/ga-status-rollup.json
```

## Output shape

The JSON artifact contains:

- `generated_at`
- `repository_root`
- `source_board`
- `summary`
- `lanes`

Each lane includes:

- `lane_id`
- `title`
- `linear`
- `status`
- `push_now`
- `exit_condition`
- `primary_doc`
- `primary_doc_last_verified`
- `freshness`
- `evidence_anchors`
- `blocker`
- `next_action`
- `inline_links`

## Freshness rules

Freshness is computed from the local file modification times of the primary lane doc plus the
configured evidence anchors for that lane.

Buckets:

- `fresh` — latest source changed within 2 days
- `aging` — latest source changed within 7 days
- `stale` — latest source older than 7 days
- `unknown` — no configured local source file exists

This is intentionally local-first. It tells the release owner whether the current checkout
contains a recently updated lane packet, not whether Linear or GitHub has already been updated.

## Lane mapping

The rollup currently covers:

- `TAR-214` — release evidence refresh
- `TAR-70` — gate policy hardening
- `TAR-238` — runner reliability
- `TAR-239` — five-country acceptance A
- `TAR-240` — five-country acceptance B
- `TAR-241` — relevance baseline
- `TAR-160` — GA umbrella / final sign-off

The GA board remains the top-level source for:

- lane status
- `push now?`
- exit condition

Lane docs remain the source for:

- blocker wording
- next-action wording
- evidence anchors

## Known limits

- The blocker and next-action text is still heuristic-plus-config, not a full issue tracker sync.
- The rollup reads the repo checkout only; it does not call GitHub, Linear, or Cloud Run.
- It is meant to reduce manual synthesis, not replace operator judgment.

## Recommended use

Use this rollup before:

- posting a `TAR-160` umbrella update
- deciding the next GA lane to push
- handing off work to another operator or agent

Good pattern:

1. run the rollup
2. inspect the `summary.overall_next_action`
3. inspect the single lane you plan to push
4. follow the primary lane doc for execution details

## Related docs

- [GA operator board](ga-operator-board.md)
- [Friction and acceleration map](friction-and-acceleration-map.md)
- [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md)
