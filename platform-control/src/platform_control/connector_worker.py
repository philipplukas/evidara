from __future__ import annotations

import argparse
import asyncio
import logging

from platform_control.config import get_settings
from platform_control.database import get_session_maker
from platform_control.services.firecrawl_provider import FirecrawlProvider
from platform_control.services.run_service import RunService

LOGGER = logging.getLogger("platform_control.connector_worker")


async def _run_once(limit: int) -> int:
    settings = get_settings()
    provider = FirecrawlProvider(settings)
    session_maker = get_session_maker()
    async with session_maker() as session:
        service = RunService(session, provider, run_dispatch_backend="worker")
        return await service.dispatch_pending_runs(limit=limit)


async def _run_loop(limit: int, interval_seconds: float) -> None:
    while True:
        dispatched = await _run_once(limit=limit)
        LOGGER.info("connector worker dispatched %s run(s)", dispatched)
        await asyncio.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="platform-control-connector-worker",
        description="Dispatch pending platform-control runs to connector providers.",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.once:
        dispatched = asyncio.run(_run_once(limit=args.limit))
        LOGGER.info("connector worker dispatched %s run(s)", dispatched)
        return

    asyncio.run(_run_loop(limit=args.limit, interval_seconds=args.interval_seconds))


if __name__ == "__main__":
    main()
