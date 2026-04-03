from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time

from platform_control.config import get_settings
from platform_control.database import get_session_maker
from platform_control.services.firecrawl_provider import FirecrawlProvider
from platform_control.services.run_service import RunService

LOGGER = logging.getLogger("platform_control.connector_worker")


class _StructuredFormatter(logging.Formatter):
    """Emit structured JSON log lines for Cloud Logging compatibility."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "service": "platform-control-worker",
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_StructuredFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


class _GracefulShutdown:
    """Handle SIGTERM/SIGINT for graceful shutdown in Cloud Run."""

    def __init__(self) -> None:
        self.should_exit = False
        signal.signal(signal.SIGTERM, self._handler)
        signal.signal(signal.SIGINT, self._handler)

    def _handler(self, signum: int, _frame: object) -> None:
        LOGGER.info(
            "Received signal %s, shutting down gracefully",
            signal.Signals(signum).name,
        )
        self.should_exit = True


async def _run_once(limit: int) -> int:
    settings = get_settings()
    provider = FirecrawlProvider(settings)
    session_maker = get_session_maker()
    async with session_maker() as session:
        service = RunService(session, provider, run_dispatch_backend="worker")
        return await service.dispatch_pending_runs(limit=limit)


async def _run_loop(limit: int, interval_seconds: float) -> None:
    shutdown = _GracefulShutdown()
    cycle = 0

    LOGGER.info(
        "Worker starting poll loop (limit=%d, interval=%.1fs)",
        limit,
        interval_seconds,
    )

    while not shutdown.should_exit:
        cycle += 1
        start = time.monotonic()
        try:
            dispatched = await _run_once(limit=limit)
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            LOGGER.info(
                "Poll cycle %d: dispatched %d run(s) in %.2fms",
                cycle,
                dispatched,
                elapsed_ms,
                extra={"extra_fields": {
                    "event": "worker_poll_cycle",
                    "cycle": cycle,
                    "dispatched": dispatched,
                    "elapsed_ms": elapsed_ms,
                }},
            )
        except Exception:
            LOGGER.exception(
                "Poll cycle %d: unhandled error",
                cycle,
                extra={"extra_fields": {
                    "event": "worker_poll_error",
                    "cycle": cycle,
                }},
            )

        # Wait with early exit on shutdown signal
        for _ in range(int(interval_seconds * 10)):
            if shutdown.should_exit:
                break
            await asyncio.sleep(0.1)

    LOGGER.info("Worker shut down after %d cycles", cycle)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="platform-control-connector-worker",
        description="Dispatch pending platform-control runs to connector providers.",
    )
    parser.add_argument("--once", action="store_true", help="Run a single poll and exit")
    parser.add_argument("--limit", type=int, default=10, help="Max runs to dispatch per cycle")
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=5.0,
        help="Seconds between poll cycles",
    )
    args = parser.parse_args()

    _setup_logging()

    if args.once:
        dispatched = asyncio.run(_run_once(limit=args.limit))
        LOGGER.info(
            "Single-shot: dispatched %d run(s)",
            dispatched,
            extra={"extra_fields": {
                "event": "worker_single_shot",
                "dispatched": dispatched,
            }},
        )
        return

    asyncio.run(_run_loop(limit=args.limit, interval_seconds=args.interval_seconds))


if __name__ == "__main__":
    main()
