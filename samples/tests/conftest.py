from datetime import date

import pytest
from doculens_samples.schema import Invoice, LineItem, Party


@pytest.fixture
def invoice() -> Invoice:
    items = [
        LineItem(name="A4 복사용지 80g", spec="500매", quantity=10, unit_price=5500, amount=55000),
        LineItem(name="볼펜 0.5mm 흑색", spec="12자루", quantity=3, unit_price=4200, amount=12600),
        LineItem(name="스테이플러 심", spec="10곽", quantity=5, unit_price=1500, amount=7500),
    ]
    return Invoice(
        document_no="2026-0001",
        issue_date=date(2026, 3, 14),
        supplier=Party(
            name="(주)가나다상사",
            business_number="123-45-67891",
            representative="김하늘",
            address="서울특별시 강남구 테헤란로 123",
        ),
        buyer=Party(
            name="라마바유통",
            business_number="987-65-43212",
            representative="이도윤",
            address="경기도 성남시 분당구 판교로 45",
        ),
        items=items,
        supply_amount=75100,
        tax_amount=7510,
        total_amount=82610,
    )
