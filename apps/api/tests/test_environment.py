"""개발 환경 스모크 테스트: 고정한 Python 버전과 핵심 의존성이 설치되어 있는지 확인한다."""
import importlib
import sys

import pytest


def test_python_version_is_3_12() -> None:
    assert sys.version_info[:2] == (3, 12)


@pytest.mark.parametrize(
    "module",
    ["fastapi", "sqlalchemy", "alembic", "pydantic", "arq", "redis"],
)
def test_core_dependency_is_importable(module: str) -> None:
    importlib.import_module(module)