"""헬스 체커. 외부 연결 하나당 체커 하나이며 HealthService에 주입한다."""
import asyncio
from typing import Literal, Protocol

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import NullPool, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

CheckResult = Literal["ok", "down", "skipped"]

logger = structlog.get_logger("doculens.health")


class HealthChecker(Protocol):
    name: str

    async def check(self) -> CheckResult: ...


class RedisChecker:
    name = "redis"

    def __init__(self, url: str | None, timeout_seconds: float = 2.0) -> None:
        self._url = url
        self._timeout = timeout_seconds

    async def check(self) -> CheckResult:
        if not self._url:
            return "skipped"
        client = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            self._url, socket_connect_timeout=self._timeout
        )
        try:
            await asyncio.wait_for(client.ping(), self._timeout)  # pyright: ignore[reportUnknownMemberType]
            return "ok"
        except (RedisError, OSError, TimeoutError) as exc:
            logger.warning("redis_check_failed", errorType=type(exc).__name__)
            return "down"
        finally:
            await client.aclose()


class DatabaseChecker:
    """`SELECT 1`로 확인한다. 드라이버가 없는 환경이면 skipped로 본다."""

    name = "database"

    def __init__(self, url: str | None, timeout_seconds: float = 2.0) -> None:
        self._url = url
        self._timeout = timeout_seconds

    async def check(self) -> CheckResult:
        if not self._url:
            return "skipped"
        try:
            await asyncio.wait_for(asyncio.to_thread(self._select_one, self._url), self._timeout)
            return "ok"
        except ModuleNotFoundError as exc:
            logger.warning("database_driver_missing", module=exc.name)
            return "skipped"
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            logger.warning("database_check_failed", errorType=type(exc).__name__)
            return "down"

    @staticmethod
    def _select_one(url: str) -> None:
        engine = create_engine(url, poolclass=NullPool)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        finally:
            engine.dispose()
