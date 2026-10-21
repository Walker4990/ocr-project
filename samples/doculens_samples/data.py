"""가짜 거래명세서 데이터 생성. 실제 개인정보는 쓰지 않고, 모든 값은 seed로 재현된다."""
import random
import re
from datetime import date, timedelta

from faker import Faker

from doculens_samples.schema import Invoice, LineItem, Party

MAX_ITEMS = 10  # 품목이 가장 적게 들어가는 양식(합계 상단 + 세로 배치)의 수용량 11행 이하
_WEIGHTS = (1, 3, 7, 1, 3, 7, 1, 3, 5)
_BUSINESS_NUMBER_PATTERN = re.compile(r"^\d{3}-\d{2}-\d{5}$")

# (품목명, 규격, 단가 하한, 단가 상한)
_CATALOG: list[tuple[str, str, int, int]] = [
    ("A4 복사용지 80g", "500매", 4500, 6500),
    ("볼펜 0.5mm 흑색", "12자루", 3000, 5000),
    ("스테이플러 심", "10곽", 1000, 2000),
    ("프린터 토너 카트리지", "1EA", 45000, 120000),
    ("포스트잇 76x76", "12패드", 3500, 6000),
    ("무선 마우스", "1EA", 9000, 25000),
    ("USB 3.0 허브", "4포트", 8000, 18000),
    ("LED 형광등 20W", "1EA", 2500, 6000),
    ("멀티탭 3m", "6구", 7000, 15000),
    ("클리어 파일", "20매", 2000, 4500),
    ("화이트보드 마커", "10본", 6000, 12000),
    ("종이컵 6.5oz", "1000개", 5000, 9000),
    ("물티슈 캡형", "100매", 1200, 2500),
    ("택배 박스 3호", "50장", 15000, 28000),
    ("OPP 테이프 48mm", "50롤", 18000, 32000),
    ("산업용 장갑", "10켤레", 5000, 11000),
    ("안전화 270mm", "1켤레", 28000, 55000),
    ("스프레이 페인트", "12통", 14000, 30000),
    ("배터리 AA", "20개", 6000, 12000),
    ("노트북 거치대", "1EA", 12000, 30000),
]


def _check_digit(first_nine: str) -> int:
    digits = [int(c) for c in first_nine]
    total = sum(d * w for d, w in zip(digits, _WEIGHTS, strict=True)) + digits[8] * 5 // 10
    return (10 - total % 10) % 10


def is_valid_business_number(value: str) -> bool:
    """사업자등록번호(NNN-NN-NNNNN)의 형식과 검증 숫자를 확인한다."""
    if not _BUSINESS_NUMBER_PATTERN.match(value):
        return False
    digits = value.replace("-", "")
    return _check_digit(digits[:9]) == int(digits[9])


def _business_number(rng: random.Random) -> str:
    head = f"{rng.randint(101, 899):03d}{rng.randint(1, 88):02d}{rng.randint(0, 9999):04d}"
    return f"{head[:3]}-{head[3:5]}-{head[5:]}{_check_digit(head)}"


def _party(rng: random.Random, fake: Faker, taken: set[str]) -> Party:
    number = _business_number(rng)
    while number in taken:
        number = _business_number(rng)
    taken.add(number)
    return Party(
        name=str(fake.company()),
        business_number=number,
        representative=str(fake.name()),
        address=str(fake.address()).replace("\n", " "),
    )


def _line_item(rng: random.Random, entry: tuple[str, str, int, int]) -> LineItem:
    name, spec, low, high = entry
    unit_price = rng.randint(low // 100, high // 100) * 100
    quantity = rng.randint(1, 50)
    return LineItem(
        name=name, spec=spec, quantity=quantity, unit_price=unit_price, amount=quantity * unit_price
    )


def generate_invoice(seed: int) -> Invoice:
    rng = random.Random(seed)
    fake = Faker("ko_KR")
    fake.seed_instance(seed)

    taken: set[str] = set()
    supplier = _party(rng, fake, taken)
    buyer = _party(rng, fake, taken)

    entries = rng.sample(_CATALOG, k=rng.randint(1, MAX_ITEMS))
    items = [_line_item(rng, entry) for entry in entries]

    supply = sum(item.amount for item in items)
    tax = supply // 10
    issued = date(2025, 1, 1) + timedelta(days=rng.randint(0, 600))
    return Invoice(
        document_no=f"{issued.year}-{rng.randint(1, 9999):04d}",
        issue_date=issued,
        supplier=supplier,
        buyer=buyer,
        items=items,
        supply_amount=supply,
        tax_amount=tax,
        total_amount=supply + tax,
    )
