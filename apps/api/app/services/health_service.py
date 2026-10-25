"""헬스 체크 결과를 모아 전체 상태를 판단한다."""
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

import structlog

from app.health import CheckResult, HealthChecker

logger = structlog.get_logger("doculens.health")


@dataclass(frozen=True)
class HealthReport:
    checks: dict[str, CheckResult]

    @property
    def healthy(self) -> bool:
        return "down" not in self.checks.values()


class HealthService:
    def __init__(self, checkers: Sequence[HealthChecker]) -> None:
        self._checkers = list(checkers)

    async def report(self) -> HealthReport:
        results = await asyncio.gather(*(self._run(checker) for checker in self._checkers))
        return HealthReport(checks=dict(results))

    @staticmethod
    async def _run(checker: HealthChecker) -> tuple[str, CheckResult]:
        try:
            return checker.name, await checker.check()
        except Exception as exc:  # 체커 하나의 실패가 헬스 응답 전체를 막지 않도록 down으로 바꾼다
            logger.error("health_check_failed", check=checker.name, errorType=type(exc).__name__)
            return checker.name, "down"
