"""Tesseract 어댑터(베이스라인). import만으로는 pytesseract를 로드하지 않는다."""
import logging
import os
import shutil
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, cast

import numpy as np
from numpy.typing import NDArray

from app.ocr.engine import OcrEngine, OcrPage, OcrToken, registry

logger = logging.getLogger(__name__)

ENGINE_NAME = "tesseract"
DEFAULT_LANG = "kor+eng"
TESSERACT_CMD_ENV_VAR = "TESSERACT_CMD"
# winget(UB-Mannheim) 기본 설치 위치. PATH에 없을 때만 쓴다
_WINDOWS_DEFAULT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# pytesseract.image_to_data(output_type=DICT)의 열 이름 -> 값 목록
TesseractData = Mapping[str, Sequence[Any]]

_WORD_LEVEL = 5


class TesseractRunner(Protocol):
    """Tesseract 호출 부분. 테스트에서는 가짜로 바꾼다."""

    def image_to_data(self, image: NDArray[np.uint8]) -> TesseractData: ...


class _PytesseractRunner:
    def __init__(self, lang: str) -> None:
        self._lang = lang

    def image_to_data(self, image: NDArray[np.uint8]) -> TesseractData:
        import pytesseract  # pyright: ignore[reportMissingTypeStubs]

        return cast(
            TesseractData,
            pytesseract.image_to_data(  # pyright: ignore[reportUnknownMemberType]
                image, lang=self._lang, output_type=pytesseract.Output.DICT
            ),
        )


def _resolve_cmd() -> str:
    configured = os.environ.get(TESSERACT_CMD_ENV_VAR)
    if configured:
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    if os.path.isfile(_WINDOWS_DEFAULT_CMD):
        return _WINDOWS_DEFAULT_CMD
    raise RuntimeError(
        "Tesseract 바이너리를 찾을 수 없다. 설치하고 PATH에 두거나 "
        f"{TESSERACT_CMD_ENV_VAR}에 경로를 지정한다 "
        "(Windows: winget install UB-Mannheim.TesseractOCR, "
        "Debian: apt install tesseract-ocr tesseract-ocr-kor)"
    )


def build_tesseract(lang: str = DEFAULT_LANG) -> TesseractRunner:
    """바이너리와 언어 데이터를 확인하고 러너를 만든다."""
    import pytesseract  # pyright: ignore[reportMissingTypeStubs]

    pytesseract.pytesseract.tesseract_cmd = (  # pyright: ignore[reportUnknownMemberType]
        _resolve_cmd()
    )
    languages = cast(list[str], pytesseract.get_languages())  # pyright: ignore[reportUnknownMemberType]
    installed = set(languages)
    missing = [code for code in lang.split("+") if code not in installed]
    if missing:
        raise RuntimeError(
            "Tesseract 언어 데이터가 없다: "
            f"{', '.join(missing)} (설치된 언어: {', '.join(sorted(installed))})"
        )
    return _PytesseractRunner(lang)


class TesseractEngine:
    name = ENGINE_NAME
    supports_gpu = False

    def __init__(self, runner: TesseractRunner) -> None:
        self._runner = runner

    def recognize(self, image: NDArray[np.uint8]) -> OcrPage:
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"RGB 이미지(높이 x 너비 x 3)여야 한다: shape={image.shape}")
        height, width = int(image.shape[0]), int(image.shape[1])

        started = time.perf_counter()
        data = self._runner.image_to_data(image)
        elapsed_ms = (time.perf_counter() - started) * 1000

        tokens = _tokens_from_data(data, width, height)
        logger.info(
            "Tesseract 인식 완료: %dx%d, 토큰 %d개, %.0fms", width, height, len(tokens), elapsed_ms
        )
        return OcrPage(width=width, height=height, tokens=tokens)


def _tokens_from_data(data: TesseractData, width: int, height: int) -> tuple[OcrToken, ...]:
    """단어를 같은 줄끼리 묶어 줄 단위 토큰으로 만든다(PaddleOCR 토큰 단위와 맞춘다)."""
    columns = (
        "level", "block_num", "par_num", "line_num",
        "left", "top", "width", "height", "conf", "text",
    )  # fmt: skip
    if len({len(data[column]) for column in columns}) > 1:
        raise ValueError("Tesseract 결과 열 길이가 서로 다르다")

    lines: dict[tuple[int, int, int], list[int]] = {}
    for i, level in enumerate(data["level"]):
        text = str(data["text"][i])
        confidence = float(data["conf"][i])
        if int(level) != _WORD_LEVEL or not text.strip() or confidence < 0:
            continue
        key = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
        lines.setdefault(key, []).append(i)

    tokens: list[OcrToken] = []
    for indices in lines.values():
        lefts = [float(data["left"][i]) for i in indices]
        tops = [float(data["top"][i]) for i in indices]
        rights = [lefts[n] + float(data["width"][i]) for n, i in enumerate(indices)]
        bottoms = [tops[n] + float(data["height"][i]) for n, i in enumerate(indices)]
        confidences = [float(data["conf"][i]) for i in indices]
        tokens.append(
            OcrToken(
                text=" ".join(str(data["text"][i]).strip() for i in indices),
                bbox=(
                    _clamp(min(lefts), 0.0, width),
                    _clamp(min(tops), 0.0, height),
                    _clamp(max(rights), 0.0, width),
                    _clamp(max(bottoms), 0.0, height),
                ),
                confidence=_clamp(sum(confidences) / len(confidences) / 100.0, 0.0, 1.0),
            )
        )
    return tuple(tokens)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _create_engine() -> OcrEngine:
    return TesseractEngine(runner=build_tesseract())


registry.register(ENGINE_NAME, _create_engine)
