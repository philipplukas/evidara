from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from platform_control.config import get_settings
from platform_control.database import reset_database_caches
from platform_control.models.base import Base


@pytest_asyncio.fixture
async def session_maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    previous_env = {
        "PLATFORM_CONTROL_DATABASE_URL": os.environ.get("PLATFORM_CONTROL_DATABASE_URL"),
        "PLATFORM_CONTROL_FIRECRAWL_WEBHOOK_SECRET": os.environ.get(
            "PLATFORM_CONTROL_FIRECRAWL_WEBHOOK_SECRET"
        ),
        "PLATFORM_CONTROL_RAW_ARTIFACT_LOCAL_DIR": os.environ.get(
            "PLATFORM_CONTROL_RAW_ARTIFACT_LOCAL_DIR"
        ),
    }

    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        raw_dir = Path(tmpdir) / "artifacts"
        os.environ["PLATFORM_CONTROL_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
        os.environ["PLATFORM_CONTROL_FIRECRAWL_WEBHOOK_SECRET"] = "test-secret"
        os.environ["PLATFORM_CONTROL_RAW_ARTIFACT_LOCAL_DIR"] = str(raw_dir)
        get_settings.cache_clear()
        reset_database_caches()

        engine = create_async_engine(os.environ["PLATFORM_CONTROL_DATABASE_URL"])
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        yield async_sessionmaker(engine, expire_on_commit=False)

        await engine.dispose()

    for key, value in previous_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    get_settings.cache_clear()
    reset_database_caches()


@pytest_asyncio.fixture
async def session(session_maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_maker() as active_session:
        yield active_session
