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


if __name__ == "__main__":
    unittest.main()
