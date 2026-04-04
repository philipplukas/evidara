# ADR-0016: Cloud Run Services vs Jobs for Pull-Based Workers

Date: 2026-04-04
Status: Accepted
Deciders: Platform Team
Applies to: platform-control-worker, document-intelligence-consumer

## Context

The platform-control-worker and document-intelligence-consumer are pull-based
Pub/Sub consumers running as Cloud Run **Services**. Each runs an HTTP health
server in a daemon thread alongside the pull loop to satisfy Cloud Run's
container contract (startup/liveness probes).

Cloud Run **Jobs** are an alternative deployment model designed for background
tasks that don't need to serve HTTP traffic.

## Decision

**Keep pull-based workers as Cloud Run Services**, not Jobs.

## Rationale

### Why not Cloud Run Jobs?

| Factor | Services (current) | Jobs |
|--------|-------------------|------|
| **Lifecycle** | Long-running, always-on | Batch: run to completion, then stop |
| **Scaling** | Automatic (0→N based on traffic/CPU) | Fixed task count per execution |
| **Pub/Sub pull** | ✅ Persistent pull loop | ❌ Must complete and exit; no continuous pull |
| **Health checks** | ✅ HTTP probes for readiness | ❌ No health check support |
| **Cost** | Pay per vCPU-second while active | Pay per vCPU-second while running |
| **Restarts** | Automatic on failure | Must re-trigger execution |
| **Monitoring** | Rich metrics (latency, request count) | Limited to job execution metrics |

### Key reasons

1. **Pub/Sub pull semantics**: Workers maintain a persistent streaming pull
   connection. Jobs would need to be triggered externally (e.g., Cloud
   Scheduler) and would process a batch then exit, adding latency and
   complexity.

2. **Health observability**: The HTTP health server pattern gives us
   startup/liveness probes, which are critical for detecting stuck consumers
   (e.g., deadlocked pull loop, exhausted connections).

3. **Simplicity**: The current daemon-thread health server is ~15 lines of
   code. Switching to Jobs would require an external trigger mechanism (Cloud
   Scheduler, Pub/Sub push, or Eventarc), adding operational surface area.

### When Jobs would make sense

- **One-shot batch processing**: e.g., nightly data exports, migration scripts
- **Fan-out parallelism**: e.g., processing 1000 documents in parallel tasks
- **Cost optimization**: if workers sit idle for long periods and min-instances
  is > 0 (currently min-instances = 0, so cold start handles this)

## Consequences

- Continue using the daemon-thread health server pattern for pull workers
- Document the pattern in the runtime runbook for future service authors
- Re-evaluate if Pub/Sub push-based processing is adopted (push → Cloud Run
  Service with HTTP handler, no need for pull loop)
