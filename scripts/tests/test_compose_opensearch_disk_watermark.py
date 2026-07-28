"""Guard the local/CI OpenSearch against disk-watermark index-creation blocks.

OpenSearch's DiskThresholdMonitor puts a *cluster-wide* create-index block on a node
that breaches the high disk watermark (90% full by default). On the single-node
throwaway cluster this repo's compose stack runs, that protection buys nothing —
disk-based shard allocation exists to relocate shards, and there is no second node to
relocate to — while the failure it produces is actively misleading:

    403 {"type":"index_create_block_exception",
         "reason":"blocked by: [FORBIDDEN/10/cluster create-index blocked (api)]"}

That reads as a permissions or auth fault, not as "the host disk is nearly full".

It broke the nightly `E2E CH Fedlex Loop` for six consecutive nights from 2026-07-22
(last green 2026-07-21): the runner disk sat at 91.5% full, `legal-search-seed` 403'd
through all 8 of its retries, and `docker compose up --wait` failed before the
acceptance loop ever ran — so the canary for ADR-0033's acceptance loop reported red
for a reason that had nothing to do with the loop.

The narrow invariant: the compose OpenSearch service must keep disk-based allocation
thresholds switched off, so a full-ish disk degrades honestly instead of presenting as
a 403.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

SETTING = "cluster.routing.allocation.disk.threshold_enabled"


def _opensearch_environment() -> list[str]:
    document = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    service = document["services"]["opensearch"]
    environment = service["environment"]
    # Compose accepts both the list form (`- KEY=value`) and the mapping form.
    if isinstance(environment, dict):
        return [f"{key}={value}" for key, value in environment.items()]
    return list(environment)


class OpenSearchDiskWatermarkTests(unittest.TestCase):
    def test_disk_allocation_thresholds_are_disabled(self) -> None:
        entries = _opensearch_environment()
        matching = [entry for entry in entries if entry.split("=", 1)[0].strip() == SETTING]

        self.assertEqual(
            len(matching),
            1,
            f"docker-compose.yml opensearch must set {SETTING} exactly once; got {matching!r}",
        )
        self.assertEqual(
            matching[0].split("=", 1)[1].strip().strip("\"'"),
            "false",
            f"{SETTING} must be false — a single-node dev cluster that breaches the high "
            "disk watermark blocks index creation cluster-wide and reports it as a 403",
        )


if __name__ == "__main__":
    unittest.main()
