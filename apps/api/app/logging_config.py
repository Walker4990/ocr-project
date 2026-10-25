"""structlog 설정. requestId는 contextvars로 바인딩해 모든 로그에 붙는다.

로그에 문서 본문과 개인정보를 남기지 않는다. 쿼리스트링과 본문은 기록하지 않는다.
"""
import logging
import sys

import structlog
from structlog.typing import Processor


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    renderer: Processor = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if json_output
        else structlog.dev.ConsoleRenderer()
    )
    log_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        # capture_logs 같은 테스트 도구가 설정을 바꿀 수 있도록 캐시하지 않는다
        cache_logger_on_first_use=False,
    )
