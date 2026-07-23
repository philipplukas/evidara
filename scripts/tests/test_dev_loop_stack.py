"""`dev-loop-stack.sh` must default to the working values, not compose's inert ones.

Two settings in `docker-compose.local.yml` default to values that make the loop
silently do nothing: `PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND=noop` (artifact
events are never published, so document-intelligence idles and a run appears to
hang at `canonical_ready=0`) and `PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND=local`
(the consumer reads from MinIO). Every component reports healthy throughout,
which is what makes it expensive — it cost a debugging cycle on 2026-07-20.

The script exists so nobody has to remember those flags. These tests exist so a
later "simplification" cannot quietly hand the defaults back to compose, or
reintroduce the partial-rebuild trap by letting `up` take a service name.

Static assertions only: the script drives Docker, so behaviour is verified by
running `dev-loop-stack.sh verify` against a live stack, not from the unit tier.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "dev-loop-stack.sh"


class DevLoopStackDefaultsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = SCRIPT.read_text(encoding="utf-8")

    def test_script_exists_and_is_executable(self) -> None:
        self.assertTrue(SCRIPT.exists(), f"{SCRIPT} is missing")
        self.assertTrue(SCRIPT.stat().st_mode & 0o111, f"{SCRIPT} is not executable")

    def test_event_publisher_defaults_to_nats_not_noop(self) -> None:
        match = re.search(
            r"PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND=\"\$\{PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND:-(\w+)\}\"",
            self.source,
        )
        self.assertIsNotNone(match, "script no longer sets an event-publisher default")
        assert match is not None
        self.assertEqual(
            match.group(1),
            "nats",
            "The event publisher default must not fall back to compose's `noop`: with "
            "noop, acquisition succeeds, no artifact event is published, and the run "
            "hangs at canonical_ready=0 with nothing logged anywhere.",
        )

    def test_artifact_store_defaults_to_s3_not_local(self) -> None:
        match = re.search(
            r"PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND=\"\$\{PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND:-(\w+)\}\"",
            self.source,
        )
        self.assertIsNotNone(match, "script no longer sets an artifact-store default")
        assert match is not None
        self.assertEqual(
            match.group(1),
            "s3",
            "document-intelligence reads artifacts from MinIO (DI_S3_ENDPOINT_URL), so a "
            "`local` store leaves it unable to fetch what platform-control wrote.",
        )

    def test_the_env_is_exported_so_every_compose_call_sees_it(self) -> None:
        # Setting without exporting would configure the script's own shell but not
        # the `docker compose` child process — the failure would look identical to
        # not setting it at all.
        for var in (
            "PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND",
            "PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND",
        ):
            self.assertRegex(
                self.source,
                rf"export {var}=",
                f"{var} must be exported, not merely assigned",
            )

    def test_up_rebuilds_everything_rather_than_named_services(self) -> None:
        # `platform-control-init` is a separate image from `platform-control-api`
        # and is what runs `alembic upgrade head`. Rebuilding a named subset is
        # precisely how migrations end up running from a stale image while
        # reporting success. `up` therefore takes no service argument.
        up_block = self.source.split("  up)", 1)
        self.assertEqual(len(up_block), 2, "no `up)` case found in the script")
        body = up_block[1].split(";;", 1)[0]
        self.assertIn("compose build", body)
        self.assertNotRegex(
            body,
            # Same line only: `\s` would span the newline onto the next statement.
            r"compose build[ \t]+\S",
            "`up` must run a bare `compose build` — naming services reintroduces the "
            "stale-platform-control-init trap.",
        )

    def test_verify_checks_the_invariants_that_fail_silently(self) -> None:
        # A `verify` that only pinged health endpoints would pass on both traps:
        # every container reports healthy in each of them.
        self.assertIn("alembic_version", self.source, "verify must check the migration head")
        self.assertIn(
            "expected_alembic_head",
            self.source,
            "verify must derive the expected head from the repo, not trust the init "
            "container's exit code",
        )
        self.assertIn(
            "PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND",
            self.source.split("verify()", 1)[1],
            "verify must read the publisher backend out of the running container",
        )

    def test_verify_catches_a_missing_or_drifted_connector_worker(self) -> None:
        # A third silent trap, same shape as the other two. RunService
        # ._should_dispatch_via_worker() forces worker dispatch for
        # _ASYNC_PROVIDER_NAMES whatever RUN_DISPATCH_BACKEND says, so with no
        # worker container an AT RIS run sits PENDING with refused=false and no
        # failure_reason — indistinguishable from a broken provider.
        body = self.source.split("verify()", 1)[1]
        self.assertIn(
            "evidara-platform-control-worker-1",
            body,
            "verify must check that the connector worker is actually running",
        )
        self.assertIn(
            "worker_publisher",
            body,
            "presence is not enough: a worker on noop/local completes the run and "
            "publishes nothing DI can read, which is the 2026-04-14 AT RIS break",
        )


class DevLoopStackComposeTests(unittest.TestCase):
    """The worker must exist as a service, with the API's event-path env.

    It used to be a commented-out block in docker-compose.yml that set only
    DATABASE_URL and RUN_DISPATCH_BACKEND. Uncommenting it produced a worker on
    the default local/noop backends — acquisition succeeded and document
    -intelligence received nothing.
    """

    PARITY_VARS = (
        "PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND",
        "PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND",
        "PLATFORM_CONTROL_NATS_SERVERS",
        "PLATFORM_CONTROL_S3_ENDPOINT_URL",
        "PLATFORM_CONTROL_RAW_ARTIFACT_BUCKET",
    )

    def setUp(self) -> None:
        path = SCRIPT.parent.parent / "docker-compose.local.yml"
        self.raw = path.read_text(encoding="utf-8")
        # safe_load resolves the `<<` merge key, so this compares the environment
        # each service actually receives rather than how it was written.
        self.services = yaml.safe_load(self.raw)["services"]

    def test_worker_service_is_defined(self) -> None:
        self.assertIn(
            "platform-control-worker",
            self.services,
            "async-provider runs (ris_ogd) cannot dispatch without this service",
        )

    def test_worker_and_api_resolve_identical_event_path_env(self) -> None:
        api = self.services["platform-control-api"]["environment"]
        worker = self.services["platform-control-worker"]["environment"]
        for var in self.PARITY_VARS:
            self.assertIn(var, worker, f"worker is missing {var}")
            self.assertEqual(
                worker[var],
                api.get(var),
                f"{var} differs between platform-control-api and "
                "platform-control-worker. The worker owns acquisition dispatch, so a "
                "worker on local/noop writes bundles document-intelligence cannot "
                "read while the run still reports completed.",
            )

    def test_worker_is_worker_backed_and_api_is_not(self) -> None:
        var = "PLATFORM_CONTROL_RUN_DISPATCH_BACKEND"
        self.assertEqual(self.services["platform-control-worker"]["environment"][var], "worker")
        self.assertEqual(self.services["platform-control-api"]["environment"][var], "inline")

    def test_parity_is_inherited_from_a_shared_anchor(self) -> None:
        # Equality above could also be satisfied by two copy-pasted blocks, which
        # is the arrangement that drifted on dev. Require the anchor itself.
        self.assertIn("x-platform-control-env: &platform-control-env", self.raw)
        self.assertEqual(
            self.raw.count("<<: *platform-control-env"),
            2,
            "both platform-control-api and platform-control-worker must inherit the "
            "shared environment anchor rather than repeat it",
        )

    def test_worker_shares_the_apps_profile(self) -> None:
        # A worker behind its own profile is a worker nobody starts.
        self.assertEqual(
            self.services["platform-control-worker"].get("profiles"),
            self.services["platform-control-api"].get("profiles"),
        )


if __name__ == "__main__":
    unittest.main()
