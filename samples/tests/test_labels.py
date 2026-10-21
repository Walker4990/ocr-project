"""정답 라벨 JSON 테스트."""
import json
from pathlib import Path

import pytest
from doculens_samples.labels import GoldenLabel, read_label, write_label
from doculens_samples.schema import Invoice
from pydantic import ValidationError


@pytest.fixture
def label(invoice: Invoice) -> GoldenLabel:
    return GoldenLabel(
        image="invoice_000.png", template_id="classic", difficulty="clean", seed=0, invoice=invoice
    )


def test_roundtrip(label: GoldenLabel, tmp_path: Path) -> None:
    path = tmp_path / "invoice_000.json"
    write_label(label, path)
    assert read_label(path) == label


def test_json_structure(label: GoldenLabel, tmp_path: Path) -> None:
    path = tmp_path / "label.json"
    write_label(label, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["image"] == "invoice_000.png"
    assert data["difficulty"] == "clean"
    assert data["invoice"]["document_no"] == "2026-0001"
    assert data["invoice"]["issue_date"] == "2026-03-14"
    assert data["invoice"]["supplier"]["business_number"] == "123-45-67891"
    assert data["invoice"]["items"][0]["name"] == "A4 복사용지 80g"
    assert data["invoice"]["total_amount"] == 82610


def test_json_is_utf8_without_bom_and_keeps_korean(label: GoldenLabel, tmp_path: Path) -> None:
    path = tmp_path / "label.json"
    write_label(label, path)
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "복사용지".encode() in raw


def test_rejects_inconsistent_totals(invoice: Invoice) -> None:
    broken = invoice.model_dump() | {"total_amount": 1}
    with pytest.raises(ValidationError, match="total"):
        Invoice.model_validate(broken)


def test_rejects_inconsistent_item_amount(invoice: Invoice) -> None:
    data = invoice.model_dump()
    data["items"][0]["amount"] += 1
    with pytest.raises(ValidationError, match="amount"):
        Invoice.model_validate(data)


def test_rejects_unknown_difficulty(invoice: Invoice) -> None:
    with pytest.raises(ValidationError):
        GoldenLabel(
            image="a.png", template_id="classic", difficulty="blurry", seed=0, invoice=invoice  # pyright: ignore[reportArgumentType]
        )
