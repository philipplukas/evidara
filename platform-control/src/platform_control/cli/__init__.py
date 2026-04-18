"""``pc`` — platform-control operator CLI.

Subcommands dispatched from :func:`main`. The CLI is intentionally dep-free
(pure argparse) and is the entrypoint for offline iteration against an existing
platform-control database — starting with ``pc plan`` which inspects a
``SourceVersion`` and prints what ``start_run`` would execute, without any
network IO.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence

from platform_control.cli import fetch as fetch_cmd
from platform_control.cli import ingest as ingest_cmd
from platform_control.cli import plan as plan_cmd
from platform_control.cli import retention as retention_cmd


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pc",
        description="platform-control operator CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser(
        "plan",
        help="Print the acquisition plan for a SourceVersion without touching the network.",
    )
    plan_parser.add_argument(
        "source_version_id",
        help="SourceVersion identifier (e.g. sv_ab12cd34).",
    )
    plan_parser.add_argument(
        "--check-robots",
        action="store_true",
        help=(
            "Fetch robots.txt for each seed host and report allowed/disallowed "
            "verdicts under the policy's user-agent. Network-touching; off by default."
        ),
    )
    plan_parser.set_defaults(runner=plan_cmd.run_from_args)

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Replay a recorded Firecrawl webhook payload into the ingest pipeline.",
    )
    ingest_parser.add_argument(
        "--from-fixture",
        required=True,
        help="Path to a JSON file holding one Firecrawl payload or an array of payloads.",
    )
    ingest_parser.set_defaults(runner=ingest_cmd.run_from_args)

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Record a live provider run as a cassette for later shadow replay.",
    )
    fetch_parser.add_argument(
        "source_version_id",
        nargs="?",
        default=None,
        help=(
            "SourceVersion to record (must be execution_mode=live). Omit when "
            "using --from-webhook-log."
        ),
    )
    fetch_parser.add_argument(
        "--record",
        dest="cassette_dir",
        default=None,
        help="Cassette directory (defaults to Settings.cassette_dir).",
    )
    fetch_parser.add_argument(
        "--from-webhook-log",
        dest="from_webhook_log",
        default=None,
        help=(
            "Bundle a directory of recorded Firecrawl webhook payloads into a "
            "single JSON fixture that 'pc ingest --from-fixture' can replay. "
            "Points at the directory populated by "
            "PLATFORM_CONTROL_FIRECRAWL_WEBHOOK_RECORD_DIR."
        ),
    )
    fetch_parser.add_argument(
        "--out",
        dest="out",
        default=None,
        help=("Output path for --from-webhook-log (defaults to <src_dir>.bundle.json)."),
    )
    fetch_parser.set_defaults(runner=fetch_cmd.run_from_args)

    retention_parser = subparsers.add_parser(
        "retention",
        help="Retention-related operator commands.",
    )
    retention_subparsers = retention_parser.add_subparsers(dest="retention_command", required=True)
    sweep_parser = retention_subparsers.add_parser(
        "sweep",
        help="Purge artifacts older than their jurisdiction's retention_days.",
    )
    sweep_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be purged without touching the database.",
    )
    sweep_parser.set_defaults(runner=retention_cmd.run_from_args)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    namespace = parser.parse_args(argv)
    runner: Callable[[argparse.Namespace], int] = namespace.runner
    return asyncio.run(_dispatch(runner, namespace))


async def _dispatch(
    runner: Callable[[argparse.Namespace], int],
    namespace: argparse.Namespace,
) -> int:
    result = runner(namespace)
    if asyncio.iscoroutine(result):
        result = await result
    return int(result or 0)


if __name__ == "__main__":  # pragma: no cover - script entry
    sys.exit(main())
