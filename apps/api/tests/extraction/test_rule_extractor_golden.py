"""골든셋 50장의 실제 OCR 토큰(픽스처)으로 규칙 추출기의 필드별 정확도를 회귀 검증한다.

OCR을 다시 돌리지 않으므로 빠르고 결정적이다. 픽스처는 `dump_ocr_tokens.py`로 다시 만든다.
정확도 하한은 측정값(2026-10-25, 650개 필드 중 624개 일치)보다 조금 낮게 잡았다. 실패 대부분은
OCR 자체의 오인식(양전구, 원드, 0↔이 등)이라 추출기로는 고칠 수 없다.
"""

import json
from collections import defaultdict
from datetime import date
from functools import cache
from pathlib import Path

import pytest
from doculens_samples.labels import GoldenLabel, read_label

from app.extraction.rule_extractor import extract_header_fields
from app.extraction.schemas import HeaderFields
from app.ocr.engine import OcrPage, OcrToken

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ocr_tokens"
GOLDEN_DIR = Path(__file__).resolve().parents[4] / "samples" / "golden"

PARTY_FIELDS = ("name", "business_number", "representative", "address")
# 필드별 최소 정확도(0~1). 주소는 줄바꿈과 오인식이 겹쳐 가장 낮다
MIN_ACCURACY: dict[str, float] = {
    "document_no": 0.95,
    "issue_date": 0.92,
    "supply_amount": 0.95,
    "tax_amount": 0.95,
    "total_amount": 0.95,
    "supplier.name": 0.92,
    "supplier.business_number": 0.95,
    "supplier.representative": 0.95,
    "supplier.address": 0.80,
    "buyer.name": 0.92,
    "buyer.business_number": 0.95,
    "buyer.representative": 0.95,
    "buyer.address": 0.84,
}
MIN_OVERALL_ACCURACY = 0.95


def load_page(stem: str) -> OcrPage:
    data = json.loads((FIXTURE_DIR / f"{stem}.json").read_text(encoding="utf-8"))
    tokens = tuple(
        OcrToken(item["text"], tuple(item["bbox"]), item["confidence"]) for item in data["tokens"]
    )
    return OcrPage(width=data["width"], height=data["height"], tokens=tokens)


def squash(text: str) -> str:
    """공백과 쉼표를 뺀다. OCR이 칸 안의 띄어쓰기를 안정적으로 재현하지 않기 때문이다."""
    return "".join(text.split()).replace(",", "")


def compare(label: GoldenLabel, result: HeaderFields) -> dict[str, bool]:
    invoice = label.invoice
    got_no = result.document_no.value if result.document_no else None
    got_date: date | None = result.issue_date.value if result.issue_date else None
    outcome = {
        "document_no": got_no is not None and squash(got_no) == squash(invoice.document_no),
        "issue_date": got_date == invoice.issue_date,
    }
    for name, want in (
        ("supply_amount", invoice.supply_amount),
        ("tax_amount", invoice.tax_amount),
        ("total_amount", invoice.total_amount),
    ):
        got = getattr(result, name)
        outcome[name] = got is not None and got.value == want
    for role in ("supplier", "buyer"):
        for field in PARTY_FIELDS:
            got = getattr(getattr(result, role), field)
            want = getattr(getattr(invoice, role), field)
            outcome[f"{role}.{field}"] = got is not None and squash(got.value) == squash(want)
    return outcome


@cache
def evaluate() -> dict[str, list[bool]]:
    per_field: dict[str, list[bool]] = defaultdict(list)
    for path in sorted(FIXTURE_DIR.glob("invoice_*.json")):
        label = read_label(GOLDEN_DIR / path.name)
        result = extract_header_fields(load_page(path.stem))
        for field, ok in compare(label, result).items():
            per_field[field].append(ok)
    return per_field


def test_픽스처가_골든셋_50장과_짝이_맞는다() -> None:
    fixtures = {path.name for path in FIXTURE_DIR.glob("invoice_*.json")}
    labels = {path.name for path in GOLDEN_DIR.glob("invoice_*.json")}

    assert len(labels) == 50
    assert fixtures == labels


@pytest.mark.parametrize("field", sorted(MIN_ACCURACY))
def test_필드별_정확도가_하한_이상이다(field: str) -> None:
    results = evaluate()[field]
    accuracy = sum(results) / len(results)

    assert accuracy >= MIN_ACCURACY[field], f"{field}: {sum(results)}/{len(results)}"


def test_전체_필드_정확도가_하한_이상이다() -> None:
    results = [ok for per_field in evaluate().values() for ok in per_field]

    assert sum(results) / len(results) >= MIN_OVERALL_ACCURACY


@pytest.mark.parametrize("stem", [f"invoice_{index:03d}" for index in range(5)])
def test_깨끗한_인쇄체_양식_5종은_모든_필드가_맞는다(stem: str) -> None:
    label = read_label(GOLDEN_DIR / f"{stem}.json")
    result = extract_header_fields(load_page(stem))

    wrong = [field for field, ok in compare(label, result).items() if not ok]

    # 000~004는 양식 5종 x clean 인쇄체다. 002는 OCR이 '윈드'를 '원드'로 읽은 상호 한 건이 틀린다
    assert wrong == (["buyer.name"] if stem == "invoice_002" else [])


@pytest.mark.parametrize("stem", [f"invoice_{index:03d}" for index in range(50)])
def test_모든_값의_신뢰도와_bbox가_유효하다(stem: str) -> None:
    page = load_page(stem)
    result = extract_header_fields(page)

    fields = [
        result.document_no,
        result.issue_date,
        result.supply_amount,
        result.tax_amount,
        result.total_amount,
        *(
            getattr(party, name)
            for party in (result.supplier, result.buyer)
            for name in PARTY_FIELDS
        ),
    ]
    for extracted in fields:
        if extracted is None:
            continue
        x_min, y_min, x_max, y_max = extracted.bbox
        assert 0.0 <= extracted.confidence <= 1.0
        assert 0 <= x_min <= x_max <= page.width
        assert 0 <= y_min <= y_max <= page.height
