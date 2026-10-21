"""가짜 거래명세서 데이터 생성 테스트."""
import pytest
from doculens_samples.data import MAX_ITEMS, generate_invoice, is_valid_business_number

SEEDS = range(50)


def test_same_seed_gives_same_invoice() -> None:
    assert generate_invoice(7) == generate_invoice(7)


def test_different_seeds_give_different_invoices() -> None:
    assert generate_invoice(1) != generate_invoice(2)


@pytest.mark.parametrize("seed", SEEDS)
def test_amounts_are_consistent(seed: int) -> None:
    invoice = generate_invoice(seed)
    for item in invoice.items:
        assert item.amount == item.quantity * item.unit_price
    assert invoice.supply_amount == sum(item.amount for item in invoice.items)
    assert invoice.tax_amount == invoice.supply_amount // 10
    assert invoice.total_amount == invoice.supply_amount + invoice.tax_amount


@pytest.mark.parametrize("seed", SEEDS)
def test_business_numbers_pass_checksum(seed: int) -> None:
    invoice = generate_invoice(seed)
    assert is_valid_business_number(invoice.supplier.business_number)
    assert is_valid_business_number(invoice.buyer.business_number)


def test_checksum_rejects_wrong_number() -> None:
    assert is_valid_business_number("220-81-62517")  # 공개된 검증용 예시 번호
    assert not is_valid_business_number("220-81-62518")
    assert not is_valid_business_number("not-a-number")


@pytest.mark.parametrize("seed", SEEDS)
def test_item_count_fits_template(seed: int) -> None:
    assert 1 <= len(generate_invoice(seed).items) <= MAX_ITEMS


def test_supplier_and_buyer_differ() -> None:
    for seed in SEEDS:
        invoice = generate_invoice(seed)
        assert invoice.supplier.business_number != invoice.buyer.business_number
