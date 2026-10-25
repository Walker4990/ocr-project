"""전처리가 실제 OCR 인식을 해치지 않는지 보는 간이 확인(모델 필요, slow)."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.ocr.engines.paddleocr_adapter import PaddleOcrEngine, build_paddleocr
from app.ocr.preprocessing import decode_image, deskew

GOLDEN_DIR = Path(__file__).resolve().parents[4] / "samples" / "golden"


def _normalize(text: str) -> str:
    return text.replace(" ", "").replace(",", "")


def _label_values(invoice: dict[str, Any]) -> list[str]:
    """라벨에서 OCR 텍스트에 그대로 들어 있어야 할 문자열을 모은다."""
    values = [str(invoice["document_no"]), str(invoice["issue_date"])]
    for side in ("supplier", "buyer"):
        party: dict[str, Any] = invoice[side]
        values += [str(party[key]) for key in ("name", "business_number", "representative")]
    for key in ("supply_amount", "tax_amount", "total_amount"):
        values.append(str(invoice[key]))
    return values


@pytest.mark.slow
@pytest.mark.parametrize("image_name", ["invoice_005", "invoice_006"])
def test_기울기_보정이_기울어진_골든셋의_필드_인식을_해치지_않는다(image_name: str) -> None:
    label: dict[str, Any] = json.loads(
        (GOLDEN_DIR / f"{image_name}.json").read_text(encoding="utf-8")
    )
    assert label["difficulty"] == "skewed"
    image = decode_image((GOLDEN_DIR / str(label["image"])).read_bytes())
    values = _label_values(label["invoice"])
    engine = PaddleOcrEngine(predictor=build_paddleocr(use_gpu=False), use_gpu=False)

    def hits(text: str) -> int:
        normalized = _normalize(text)
        return sum(_normalize(value) in normalized for value in values)

    raw_hits = hits(engine.recognize(image).text)
    fixed_hits = hits(engine.recognize(deskew(image)).text)

    assert fixed_hits >= raw_hits
