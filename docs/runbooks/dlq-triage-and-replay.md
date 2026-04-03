# Dead-Letter Queue Triage and Replay Runbook

Owner: Platform team
Last reviewed: 2026-04-03
Last verified: Not yet verified
Applies to: dev, staging, prod

## Scope

This runbook covers inspecting, triaging, and replaying messages that have been
forwarded to dead-letter queues (DLQs) after exhausting their retry budget.

## Prerequisites

- `gcloud` authenticated for the target project
- Access to Cloud Logging for the relevant GCP project

## DLQ Naming Convention

Each DLQ follows the pattern `{subscription-name}-dlq`:

| Subscription | DLQ Topic | DLQ Subscription | Max Attempts |
|-------------|-----------|-----------------|:---:|
| document-intelligence-artifact-bundle-available | …-dlq | …-dlq-sub | 10 |
| platform-control-document-processing-status-updated | …-dlq | …-dlq-sub | 5 |
| legal-search-document-processed | …-dlq | …-dlq-sub | 5 |
| legal-search-document-withdrawn | …-dlq | …-dlq-sub | 5 |
| legal-search-index-update-requested | …-dlq | …-dlq-sub | 5 |

## Step 1: Check DLQ Depth

```bash
# List undelivered message count for all DLQ subscriptions
gcloud pubsub subscriptions list \
  --project=PROJECT_ID \
  --filter="name:dlq-sub" \
  --format="table(name, messageRetentionDuration, ackDeadlineSeconds)"
```

For a specific DLQ:

```bash
gcloud pubsub subscriptions describe \
  document-intelligence-artifact-bundle-available-dlq-sub \
  --project=PROJECT_ID \
  --format="json(pushConfig, ackDeadlineSeconds)"
```

## Step 2: Inspect Messages

Pull messages without acknowledging to inspect them:

```bash
gcloud pubsub subscriptions pull \
  document-intelligence-artifact-bundle-available-dlq-sub \
  --project=PROJECT_ID \
  --limit=5 \
  --auto-ack=false \
  --format=json
```

Key attributes to check:
- `googclient_deliveryattempt`: How many times delivery was attempted
- `message.data`: The original event payload (base64-encoded)
- `message.messageId`: Correlate with Cloud Logging

## Step 3: Classify the Failure

Check Cloud Logging for the original processing error:

```
resource.type="cloud_run_revision"
textPayload:"failed to process message MESSAGE_ID"
```

### Failure Categories

| Category | Symptoms | Action |
|----------|----------|--------|
| **Transient** | Timeout, connection refused, 503 | Fix infra, then replay |
| **Poison / permanent** | Schema error, missing fields, bad JSON | Fix event source, ack from DLQ |
| **Bug** | Unexpected exception in processing code | Fix code, deploy, then replay |

## Step 4: Replay Messages

After fixing the root cause, republish DLQ messages to the original topic:

```bash
# Pull from DLQ, republish to main topic, then ack from DLQ
gcloud pubsub subscriptions pull \
  document-intelligence-artifact-bundle-available-dlq-sub \
  --project=PROJECT_ID \
  --limit=10 \
  --format=json | \
jq -r '.[].message.data' | while read -r data; do
  gcloud pubsub topics publish artifact-bundle-available \
    --project=PROJECT_ID \
    --message="$(echo "$data" | base64 -d)"
done
```

> **Warning**: Only replay after fixing the root cause, otherwise messages will
> cycle back to DLQ. Verify the fix is deployed before replaying.

## Step 5: Purge DLQ After Investigation

If messages have been handled (replayed or deemed unrecoverable):

```bash
# Seek to now — effectively acks all existing messages
gcloud pubsub subscriptions seek \
  document-intelligence-artifact-bundle-available-dlq-sub \
  --project=PROJECT_ID \
  --time=now
```

## Escalation

Escalate if:
- DLQ messages accumulate for >24 hours without investigation
- The same message type repeatedly appears in DLQ after a fix
- More than 50 messages are dead-lettered in a single hour

## Related Resources

- [Terraform DLQ config](../../infra/terraform/gcp/runtime_stack/main.tf)
- [DI runtime consumer](../../document-intelligence/src/document_intelligence/jobs/runtime_consumer.py)
- [Release gates](./document-intelligence-release-gates.md)
