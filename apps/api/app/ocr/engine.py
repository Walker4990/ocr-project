"""OCR 엔진 추상화. 엔진 구현(PaddleOCR 등)은 이 Protocol만 만족하면 서로 바꿔 쓸 수 있다."""
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

ENGINE_ENV_VAR = "OCR_ENGINE"
DEFAULT_ENGINE_NAME = "paddleocr"

# (x_min, y_min, x_max, y_max), 원본 이미지 픽셀 좌표
BBox = tuple[float, float, float, float]


class UnknownOcrEngineError(ValueError):
    """등록되지 않은 엔진 이름을 요청했다."""


@dataclass(frozen=True)
class OcrToken:
    text: str
    bbox: BBox
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence는 0~1이어야 한다: {self.confidence}")
        x_min, y_min, x_max, y_max = self.bbox
        if x_min > x_max or y_min > y_max:
            raise ValueError(f"bbox의 최소 좌표가 최대 좌표보다 크다: {self.bbox}")


@dataclass(frozen=True)
class OcrPage:
    width: int
    height: int
    tokens: tuple[OcrToken, ...]

    @property
    def text(self) -> str:
        return "\n".join(token.text for token in self.tokens)


@runtime_checkable
class OcrEngine(Protocol):
    name: str
    supports_gpu: bool

    def recognize(self, image: NDArray[np.uint8]) -> OcrPage:
        """RGB 이미지(높이 x 너비 x 3) 한 장을 인식해 토큰 목록을 돌려준다."""
        ...


EngineFactory = Callable[[], OcrEngine]


class EngineRegistry:
    """엔진 이름 -> 생성 함수. 무거운 모델은 `create`를 부를 때 처음 만든다."""

    def __init__(self) -> None:
        self._factories: dict[str, EngineFactory] = {}

    def register(self, name: str, factory: EngineFactory) -> None:
        if name in self._factories:
            raise ValueError(f"이미 등록된 OCR 엔진이다: {name}")
        self._factories[name] = factory

    def names(self) -> list[str]:
        return sorted(self._factories)

    def create(
        self, name: str | None = None, environ: Mapping[str, str] | None = None
    ) -> OcrEngine:
        """이름 인자, 환경변수 OCR_ENGINE, 기본 엔진 순으로 정해 만든다."""
        env = os.environ if environ is None else environ
        chosen = name or env.get(ENGINE_ENV_VAR) or DEFAULT_ENGINE_NAME
        factory = self._factories.get(chosen)
        if factory is None:
            raise UnknownOcrEngineError(
                f"알 수 없는 OCR 엔진: {chosen} (등록된 엔진: {', '.join(self.names()) or '없음'})"
            )
        return factory()


# 엔진 모듈이 import될 때 여기에 자신을 등록한다
registry = EngineRegistry()
