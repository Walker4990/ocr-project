"""PaddleOCR(PP-OCRv5 한국어) 어댑터. import만으로는 모델을 로드하지 않는다."""
import logging
import os
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, cast

import numpy as np
from numpy.typing import NDArray

from app.ocr.engine import OcrEngine, OcrPage, OcrToken, registry

logger = logging.getLogger(__name__)

ENGINE_NAME = "paddleocr"
USE_GPU_ENV_VAR = "OCR_USE_GPU"
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off", ""}


class PaddlePredictor(Protocol):
    """PaddleOCR 인스턴스 중 어댑터가 쓰는 부분. 테스트에서 가짜로 바꿀 수 있다."""

    def predict(self, image: NDArray[np.uint8]) -> Sequence[Mapping[str, Any]]: ...


def resolve_use_gpu(environ: Mapping[str, str] | None = None) -> bool:
    """환경변수 OCR_USE_GPU로 GPU 사용 여부를 정한다. 기본은 CPU."""
    env = os.environ if environ is None else environ
    raw = env.get(USE_GPU_ENV_VAR, "").strip().lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    raise ValueError(f"{USE_GPU_ENV_VAR}는 1/0, true/false 중 하나여야 한다: {raw!r}")


def build_paddleocr(use_gpu: bool) -> PaddlePredictor:
    """PP-OCRv5 한국어 모델을 로드한다. 첫 호출에는 모델 다운로드와 로딩이 일어난다."""
    # 무거워서 실제로 만들 때만 import한다. 타입 스텁이 없다
    from paddleocr import PaddleOCR  # pyright: ignore[reportMissingTypeStubs]

    ocr = PaddleOCR(
        lang="korean",
        ocr_version="PP-OCRv5",
        # CPU에서 서버급 검출 모델은 A4 스캔 한 장에 약 190초, 모바일은 약 21초(인식 결과 동일).
        # 모델 이름을 하나만 바꾸면 나머지가 중국어 모델로 돌아가므로 인식 모델도 함께 지정한다
        text_detection_model_name="PP-OCRv5_server_det" if use_gpu else "PP-OCRv5_mobile_det",
        text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
        text_det_limit_type="max",
        text_det_limit_side_len=1600,
        device="gpu" if use_gpu else "cpu",
        # oneDNN(기본값)이 인식 단계를 크게 줄인다. paddlepaddle 3.3은 이 경로에서
        # NotImplementedError가 나서 pyproject에서 3.2.2로 고정했다. 올리기 전에 확인할 것
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    return cast(PaddlePredictor, ocr)


class PaddleOcrEngine:
    name = ENGINE_NAME

    def __init__(self, predictor: PaddlePredictor, use_gpu: bool) -> None:
        self._predictor = predictor
        self.supports_gpu = use_gpu

    def recognize(self, image: NDArray[np.uint8]) -> OcrPage:
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"RGB 이미지(높이 x 너비 x 3)여야 한다: shape={image.shape}")
        height, width = int(image.shape[0]), int(image.shape[1])

        # PaddleOCR는 OpenCV 관례(BGR)로 받는다
        bgr = np.ascontiguousarray(image[..., ::-1])
        started = time.perf_counter()
        results = self._predictor.predict(bgr)
        elapsed_ms = (time.perf_counter() - started) * 1000

        tokens = tuple(
            token for result in results for token in _tokens_from_result(result, width, height)
        )
        logger.info(
            "PaddleOCR 인식 완료: %dx%d, 토큰 %d개, %.0fms", width, height, len(tokens), elapsed_ms
        )
        return OcrPage(width=width, height=height, tokens=tokens)


def _tokens_from_result(
    result: Mapping[str, Any], width: int, height: int
) -> list[OcrToken]:
    polys = cast(Sequence[Any], result["rec_polys"])
    texts = cast(Sequence[str], result["rec_texts"])
    scores = cast(Sequence[float], result["rec_scores"])
    if not len(polys) == len(texts) == len(scores):
        raise ValueError(
            f"PaddleOCR 결과 길이가 서로 다르다: polys={len(polys)}, "
            f"texts={len(texts)}, scores={len(scores)}"
        )

    tokens: list[OcrToken] = []
    for poly, text, score in zip(polys, texts, scores, strict=True):
        if not text.strip():
            continue
        points = np.asarray(poly, dtype=np.float64).reshape(-1, 2)
        x_min, y_min = points.min(axis=0)
        x_max, y_max = points.max(axis=0)
        tokens.append(
            OcrToken(
                text=text,
                bbox=(
                    _clamp(float(x_min), 0.0, width),
                    _clamp(float(y_min), 0.0, height),
                    _clamp(float(x_max), 0.0, width),
                    _clamp(float(y_max), 0.0, height),
                ),
                confidence=_clamp(float(score), 0.0, 1.0),
            )
        )
    return tokens


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _create_engine() -> OcrEngine:
    use_gpu = resolve_use_gpu()
    return PaddleOcrEngine(predictor=build_paddleocr(use_gpu), use_gpu=use_gpu)


registry.register(ENGINE_NAME, _create_engine)
