# ADR-0058: A terminal outcome is recorded where someone will see it

## Status

Proposed

## Date

2026-09-17

## Context

`#958` says the corpus states what is true or refuses, and names the defect it
turns on: nothing in the stack reliably distinguishes *absent* from *broken*.

This ADR was first drafted with a wrong root cause, and the correction is the
reason it is now much smaller. Both versions are recorded here because the
mistake is the most useful thing in it.

### What was observed, and what I first concluded

A `lexfind_api_zh_full` acceptance run captured 944 documents. `di-consumer` was
OOMKilled seven times in eighteen minutes against a 1 GiB limit (#1012; ceiling
raised in #1013). Afterwards 59 of 917 documents had no terminal status, no error
code, and every NATS consumer reported nothing outstanding:

```
di-artifact-bundle-available          Ack Pending 0   Unprocessed 0
legal-search-projection-bridge        Ack Pending 0   Unprocessed 0
platform-control-processing-status    Ack Pending 0   Unprocessed 0
```

I concluded the OOM had abandoned them and that the pipeline needed a way to
detect an interrupted document without asking the component that failed — a
broker-derived `unaccounted` state in platform-control's read model.

### What one command showed instead

```
$ nats stream subjects EVIDARA
evidara.document-processing-status-updated.dlq    40
evidara.document-processed.dlq                    48
```

There is **no** `artifact-bundle-available.dlq`. `di-consumer` dead-lettered
nothing, so the OOM abandoned nothing. Reading one of those messages:

```
status:        canonical_ready
run_id:        run_01m2q5fsqmarc3mxvfpsw1jjdt
occurred_at:   2026-09-17T08:03:01Z
```

DI processed the documents and emitted `canonical_ready`. The **projection
bridge** could not forward them, because the operator API key had been rotated
with a trailing newline and `httpx` refused the header (`Invalid header value
b'…\n'`). Retries exhausted, 88 events dead-lettered, and 59 documents were left
without a terminal status in the read model.

**Nothing was lost. Nothing could read it back.**

### So the gap is narrower than it looked

Three of the four layers from the first draft hold, and the load-bearing one is
the third — not a missing state machine:

1. `failed` is in the status enum
   (`contracts/events/document-processing-status-updated.schema.json:61`) and
   nothing emits it. The consumer's two terminal outcomes — `dead_lettered`
   (`nats_consumer.py:147-165`) and `rejected_permanent` — both `term()` the
   message and log an ERROR, emitting no event. Declared with no producer.
2. **The DLQ had no reader.** `scripts/replay-dlq.sh` is a GCP Pub/Sub script and
   ADR-0029 retired that runtime, so on Hetzner/NATS a dead-lettered event was
   unrecoverable in practice while its payload sat in the stream.
3. **Nobody looks at DLQ depth.** It is not on a screen, not in the CLI, not in
   the run read model. A non-zero DLQ *was* the signal, available the whole time.
4. Logs are not aggregated (#892), so the `Invalid header value` errors vanished
   on restart. `kubectl logs --previous` on the final crash returned three
   startup lines.

The detection problem I set out to solve was already solved by the broker. The
reporting problem was that its answer had no audience.

## Decision

**A terminal outcome is recorded where someone will see it.** Three narrow
changes, none of which adds a component or a dependency.

### 1. The consumer emits `failed` on both of its terminal paths

With a machine-readable `error_code` — `retry_budget_exhausted` for a
dead-letter, the rejection's own code for a permanent rejection.

The enum value, the event builder and the publisher all already exist, so this is
a few lines and no contract change. It is accurate whenever the worker is alive
enough to publish, which covers both paths it applies to. It does **not** cover a
kill, and must not be read as covering one.

### 2. The DLQ is readable and replayable

Built as `scripts/replay-nats-dlq.sh` (#1023). It enumerates `.dlq` subjects
read-only and republishes each payload to the subject minus the suffix.

It never drains the DLQ: if a republish fails, the only copy of the payload is
still there. Replay is safe to repeat because both event types key on
`document_id`, stable per version (#850), and both consumers upsert.

### 3. DLQ depth is surfaced where it is already being looked at

A non-zero DLQ means an event was abandoned. Today that fact lives only in
`nats stream subjects`. It belongs in the run read model and in
`workflow coverage watch`'s stall causes, beside `di_consumer_silent` and
`projection_stalled` — which is exactly where someone diagnosing this run would
have looked first.

This is reporting, not new state. It requires no timeout and no new coupling.

## What is explicitly rejected

### A broker-derived `unaccounted` state in platform-control

The first draft proposed computing `expected - terminal` and splitting the
remainder into `queued` / `in_flight` / `unaccounted` from JetStream's
`num_pending` and `num_ack_pending`.

Rejected. It would have added a read dependency from platform-control onto broker
internals in order to detect a condition the DLQ already recorded with full
fidelity — including the payload, which a derived count does not carry. The
evidence for this rejection is the incident itself: every input that read model
needed was available, and the reason nobody acted on it was that no surface
showed it. Decision 3 is the cheaper half of the same goal.

Revisit if a failure is ever found that leaves **no** DLQ entry and **no** log
line. That would be a real detection gap rather than a reporting one.

### A staleness timeout

A "stuck for more than N minutes" rule is a floor calibrated on one sample, and
2026-09-17 is a record of what that costs: a 10 KB content floor that withheld a
3,080-character municipal ordinance (#1016), an `Art.`-only density gate that
read 126 `§` markers as no legal text (#1017), an `Art. 1`-only first-article
gate that failed an 1874 treaty numbered `Art. I` to `Art. VI` (#1019).

### A per-document lease or heartbeat

JetStream's ack-pending already **is** the lease. A second one duplicates broker
state in application state where the two can disagree, and needs a renewal
interval and expiry — a timeout by another name.

Revisit only if DI becomes multi-consumer with work-stealing, where ack-pending
stops identifying which worker holds a document.

### Out of scope

- Repairing the 59 rows. That is a replay (#1023), not a design change.
- The partial-projection case. `doc_7wv3h5v3mtrsh5x2gbvm7bwypv` reached a
  terminal state carrying three of its six metadata rows and the placeholder
  title `Document <id>` while the provider had captured
  `Beschluss der Einwohnergemeindeversammlung betreffend Festsetzung der
  Hundesteuer`. Nothing here detects a record that is complete-looking and
  partial; that is #871's axis. Named so it is not assumed covered.
- #892 log aggregation. Independent, and it is what would have made this root
  cause readable rather than inferred.

## Consequences

### `failed` stops being decoration

The enum value gains its first producer. Additive under the compatibility policy,
but it is a value nobody has rendered, so the admin panel's status displays need
checking before decision 1 ships.

### A dead-lettered event stops being a silent loss

Decision 1 records that it happened, decision 2 recovers it, decision 3 makes
someone notice. Each is useless without the other two: an event nobody can
replay, a replay nobody knows to run, and a signal nobody sees are the same
failure in three places.

### This is reporting, not repair

None of the three makes an interrupted document complete. That is the right
order — #958's defect is that the system cannot tell absent from broken, and a
repair built on a state you cannot see is a reindex of the wrong keys.

### The cheapest instrument was already installed

Worth recording plainly, because the first draft of this ADR did not: the answer
came from `nats stream subjects`, a read-only command against a component we
already run. It was reached only after a three-part architecture had been designed
around its absence. Measure the system you have before extending it.
