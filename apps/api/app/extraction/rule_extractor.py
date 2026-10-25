"""규칙 기반 헤더 필드 추출기. OCR 토큰의 라벨(키워드)과 위치 관계로 거래명세서 헤더를 읽는다.

흐름: 토큰 텍스트에서 라벨(문서번호, 상호, 등록번호 ...)을 찾고, 라벨 오른쪽(또는 금액은 아래)의
값 토큰을 모아 정규식으로 형식을 확인·정규화한다. 공급자/공급받는자는 각 필드 라벨의 위쪽에서
가장 가까운 역할 라벨(공급자, 공급받는자)로 가른다. 좌우 배치와 위아래 배치 양식을 모두 다룬다.

글줄이 기울어 있어도 같은 줄을 알아보도록, 토큰 중심들의 기울기를 먼저 추정해 좌표를 펴서 쓴다.
(이미지를 돌리는 것이 아니라 좌표만 계산한다. 결과 bbox는 원본 좌표 그대로다.)

한계: 라벨 문자열을 못 읽거나 역할 라벨이 없으면 해당 필드는 None이다. 선 없는 양식·페이지 전체가
기울어진 사진 같은 입력은 측정으로만 확인했다(HANDOFF의 간이 측정 참고).
"""

import math
import re
import statistics
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.extraction.schemas import Extracted, HeaderFields, PartyFields
from app.ocr.engine import BBox, OcrPage, OcrToken


class _Key(StrEnum):
    DOCUMENT_NO = "document_no"
    ISSUE_DATE = "issue_date"
    SUPPLIER_ROLE = "supplier_role"
    BUYER_ROLE = "buyer_role"
    NAME = "name"
    BUSINESS_NUMBER = "business_number"
    REPRESENTATIVE = "representative"
    ADDRESS = "address"
    SUPPLY_AMOUNT = "supply_amount"
    TAX_AMOUNT = "tax_amount"
    TOTAL_AMOUNT = "total_amount"


# 공백을 뺀 라벨 표기. 같은 키 안에서는 긴 표기가 먼저 맞도록 아래에서 정렬한다
_ALIASES: dict[_Key, tuple[str, ...]] = {
    _Key.DOCUMENT_NO: ("문서번호", "거래번호"),
    _Key.ISSUE_DATE: ("작성일자", "작성일", "발행일자", "발행일", "거래일자"),
    _Key.SUPPLIER_ROLE: ("공급자",),
    _Key.BUYER_ROLE: ("공급받는자",),
    _Key.NAME: ("상호명", "상호"),
    _Key.BUSINESS_NUMBER: ("사업자등록번호", "사업자번호", "등록번호"),
    _Key.REPRESENTATIVE: ("대표자명", "대표자", "성명"),
    _Key.ADDRESS: ("사업장주소", "주소"),
    _Key.SUPPLY_AMOUNT: ("공급가액",),
    _Key.TAX_AMOUNT: ("세액",),
    _Key.TOTAL_AMOUNT: ("합계금액", "합계"),
}
_ALIAS_LIST: tuple[tuple[str, _Key], ...] = tuple(
    sorted(
        ((alias, key) for key, aliases in _ALIASES.items() for alias in aliases),
        key=lambda pair: -len(pair[0]),
    )
)
_ROLE_KEYS = frozenset({_Key.SUPPLIER_ROLE, _Key.BUYER_ROLE})
_PARTY_KEYS = (_Key.NAME, _Key.BUSINESS_NUMBER, _Key.REPRESENTATIVE, _Key.ADDRESS)
_AMOUNT_KEYS = frozenset({_Key.SUPPLY_AMOUNT, _Key.TAX_AMOUNT, _Key.TOTAL_AMOUNT})

_FUZZY_LABEL_SCORE = 0.9
# 한 글자만 틀린 라벨을 받아들이는 최소 길이.
# 두 글자 라벨(상호, 주소, 세액)은 값과 헷갈려 정확히 일치할 때만 본다
_FUZZY_MIN_LENGTH = 3
_FUZZY_PREFIX_MIN_LENGTH = 4

# OCR이 숫자 자리에서 자주 바꿔 읽는 글자. 숫자만 기대하는 값(날짜, 번호, 금액)에만 적용한다.
# 하이픈 대신 읽히는 긴 대시도 하이픈으로 돌린다
_DASHES = {"–": "-", "—": "-", "‐": "-", "‑": "-", "−": "-"}
_DIGIT_FIXES = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", **_DASHES})
_DASH_FIXES = str.maketrans(_DASHES)
# 일 뒤에 숫자나 다른 한글이 붙으면 OCR이 글자를 깨뜨린 것이므로(03월1구일) 잘린 값으로 읽지 않는다
_DATE_PATTERN = re.compile(
    r"(?<!\d)(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})(?:\s*일|(?![\d가-힣]))"
)
_BUSINESS_NUMBER_PATTERN = re.compile(r"(\d{3})\D?(\d{2})\D?(\d{5})")
_LABEL_VALUE_SEPARATORS = " :：\t"

# 같은 줄로 보는 세로 오차(라벨 높이의 배수)
_ROW_TOLERANCE = 0.6
# 라벨과 값, 값 조각끼리 이어 붙이는 가로 간격 상한(라벨 높이의 배수)
_MAX_GAP = 4.0
# 이어지는 둘째 줄: 첫 줄 아래로 이 범위(첫 줄 높이의 배수) 안에 있어야 한다
_CONTINUATION_MIN = 0.5
_CONTINUATION_MAX = 1.8
# 금액 값은 라벨 아래 이 범위(라벨 높이의 배수) 안에서 찾는다
_BELOW_MAX = 2.5

# 기울기 추정: 멀리 떨어진 토큰 쌍이 이루는 각도의 최빈값
_SKEW_MIN_DX = 150.0
_SKEW_MAX_DEGREES = 10.0
_SKEW_BIN_DEGREES = 0.25
_SKEW_MIN_SUPPORT = 3


@dataclass(frozen=True)
class _LabelHit:
    key: _Key
    # 라벨 뒤에 같은 토큰으로 붙어 있는 값("문서번호:2026-1")의 원문. 없으면 빈 문자열이다
    inline_value: str
    score: float


@dataclass(frozen=True)
class _Placed:
    """기울기를 편 좌표로 옮긴 토큰."""

    token: OcrToken
    x0: float
    x1: float
    cy: float
    h: float
    hit: _LabelHit | None

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass(frozen=True)
class _Found:
    raw_text: str
    tokens: tuple[OcrToken, ...]
    label_score: float


def extract_header_fields(page: OcrPage) -> HeaderFields:
    placed = _place(page.tokens)
    labels = sorted((p for p in placed if p.hit is not None), key=lambda p: (p.cy, p.x0))

    supplier, buyer = _extract_parties(placed, labels)
    return HeaderFields(
        document_no=_first_parsed(_Key.DOCUMENT_NO, placed, labels, _parse_document_no),
        issue_date=_first_parsed(_Key.ISSUE_DATE, placed, labels, _parse_date),
        supplier=supplier,
        buyer=buyer,
        supply_amount=_first_parsed(_Key.SUPPLY_AMOUNT, placed, labels, _parse_amount),
        tax_amount=_first_parsed(_Key.TAX_AMOUNT, placed, labels, _parse_amount),
        total_amount=_first_parsed(_Key.TOTAL_AMOUNT, placed, labels, _parse_amount),
    )


# --- 라벨 인식 ---


def _squash(text: str) -> str:
    return "".join(text.split())


def _match_label(text: str) -> _LabelHit | None:
    """토큰이 라벨이거나 라벨로 시작하면 어떤 라벨인지, 뒤에 붙은 값과 함께 돌려준다."""
    squashed = _squash(text)
    for alias, key in _ALIAS_LIST:
        if squashed.startswith(alias):
            return _LabelHit(key, _raw_after_prefix(text, len(alias)), 1.0)
    for alias, key in _ALIAS_LIST:
        if len(alias) < _FUZZY_MIN_LENGTH:
            continue
        # 값이 붙은 토큰("문사번호:2025-1")은 라벨이 길 때만 앞부분으로 비교한다(짧으면 값과 헷갈림)
        if len(squashed) > len(alias) and len(alias) < _FUZZY_PREFIX_MIN_LENGTH:
            continue
        if _differs_by_one(squashed[: len(alias)], alias):
            return _LabelHit(key, _raw_after_prefix(text, len(alias)), _FUZZY_LABEL_SCORE)
    return None


def _differs_by_one(text: str, alias: str) -> bool:
    return len(text) == len(alias) and sum(a != b for a, b in zip(text, alias, strict=True)) == 1


def _raw_after_prefix(text: str, consumed_chars: int) -> str:
    """공백을 뺀 앞쪽 `consumed_chars`글자를 지나고 남은 원문에서 구분자(콜론, 공백)를 뗀다."""
    seen = 0
    for index, char in enumerate(text):
        if char.isspace():
            continue
        seen += 1
        if seen == consumed_chars:
            return text[index + 1 :].strip(_LABEL_VALUE_SEPARATORS)
    return ""


# --- 기울기 보정과 배치 ---


def _estimate_skew(tokens: tuple[OcrToken, ...]) -> float:
    """같은 글줄에서 멀리 떨어진 토큰 쌍의 각도 최빈값(라디안, 오른쪽으로 내려가면 양수)."""
    centers = sorted(
        ((t.bbox[0] + t.bbox[2]) / 2, (t.bbox[1] + t.bbox[3]) / 2, t.bbox[3] - t.bbox[1])
        for t in tokens
    )
    limit = math.tan(math.radians(_SKEW_MAX_DEGREES))
    bins: Counter[int] = Counter()
    for i, (x_a, y_a, h_a) in enumerate(centers):
        for x_b, y_b, h_b in centers[i + 1 :]:
            dx = x_b - x_a
            if dx < _SKEW_MIN_DX or max(h_a, h_b) > 1.5 * min(h_a, h_b):
                continue
            if abs(y_b - y_a) / dx <= limit:
                angle = math.degrees(math.atan2(y_b - y_a, dx))
                bins[round(angle / _SKEW_BIN_DEGREES)] += 1
    if not bins:
        return 0.0
    # 이웃 칸까지 합쳐 센다. 같은 글줄의 각도가 두 칸에 걸쳐 흩어져도 최빈값이 흔들리지 않게 한다
    best_bin, support = max(
        ((b, bins[b - 1] + bins[b] + bins[b + 1]) for b in bins),
        key=lambda pair: (pair[1], -abs(pair[0])),
    )
    if support < _SKEW_MIN_SUPPORT:
        return 0.0
    return math.radians(best_bin * _SKEW_BIN_DEGREES)


def _place(tokens: tuple[OcrToken, ...]) -> list[_Placed]:
    if not tokens:
        return []
    theta = _estimate_skew(tokens)
    cos, sin, tan = math.cos(theta), math.sin(theta), math.tan(theta)

    def flat_x(x: float, y: float) -> float:
        return x * cos + y * sin

    placed: list[_Placed] = []
    for token in tokens:
        x_min, y_min, x_max, y_max = token.bbox
        cy_raw = (y_min + y_max) / 2
        height = y_max - y_min
        # 기울어진 글자의 바깥 사각형은 폭에 비례해 세로로 부풀어 있다
        flat_height = max(height - (x_max - x_min) * abs(tan), 0.4 * height)
        cx_raw = (x_min + x_max) / 2
        placed.append(
            _Placed(
                token=token,
                x0=flat_x(x_min, cy_raw),
                x1=flat_x(x_max, cy_raw),
                cy=cy_raw * cos - cx_raw * sin,
                h=flat_height,
                hit=_match_label(token.text),
            )
        )
    return placed


# --- 값 찾기 ---


def _same_row(a: _Placed, b: _Placed) -> bool:
    return abs(a.cy - b.cy) <= _ROW_TOLERANCE * a.h


def _contiguous_run(candidates: list[_Placed], start_edge: float, unit: float) -> list[_Placed]:
    """왼쪽부터 가로 간격이 `unit*_MAX_GAP` 이내로 이어지고 라벨을 만나기 전까지의 토큰들."""
    run: list[_Placed] = []
    edge = start_edge
    for item in sorted(candidates, key=lambda p: p.x0):
        if item.hit is not None or item.x0 - edge > _MAX_GAP * unit:
            break
        run.append(item)
        edge = item.x1
    return run


def _right_of(label: _Placed, placed: list[_Placed]) -> list[_Placed]:
    candidates = [
        p
        for p in placed
        if p is not label and _same_row(label, p) and p.x0 >= label.x1 - 0.5 * label.h
    ]
    if not candidates:
        return []
    # 저해상도처럼 줄 간격이 라벨 높이보다 좁으면 둘째 줄까지 같은 줄로 잡힌다.
    # 라벨 줄에 가장 가까운 토큰을 기준으로 다시 거른다
    anchor = min(candidates, key=lambda p: abs(p.cy - label.cy))
    unit = min(label.h, anchor.h)
    row = [p for p in candidates if abs(p.cy - anchor.cy) <= _ROW_TOLERANCE * unit]
    return _contiguous_run(row, label.x1, label.h)


def _below(label: _Placed, placed: list[_Placed]) -> list[_Placed]:
    """금액 라벨 아래 칸의 값. 같은 줄의 다음 금액 라벨 앞까지를 이 라벨의 칸으로 본다."""
    limit = min(
        (
            p.x0
            for p in placed
            if p.hit is not None
            and p.hit.key in _AMOUNT_KEYS
            and _same_row(label, p)
            and p.x0 > label.x0
        ),
        default=math.inf,
    )
    candidates = [
        p
        for p in placed
        if p.hit is None
        and _CONTINUATION_MIN * label.h < p.cy - label.cy <= _BELOW_MAX * label.h
        and label.x0 - 0.5 * label.h <= p.cx < limit
    ]
    if not candidates:
        return []
    nearest = min(candidates, key=lambda p: p.cy)
    row = [p for p in candidates if _same_row(nearest, p)]
    return _contiguous_run(row, min(p.x0 for p in row), label.h)


def _continuation(first_line: list[_Placed], placed: list[_Placed], unit: float) -> list[_Placed]:
    """첫 줄 바로 아래에 왼쪽을 맞춰 이어지는 둘째 줄(주소가 칸 너비에서 줄바꿈된 경우).

    `unit`은 글자 높이 기준이다. 넓은 값 토큰은 기울면 상자가 부풀어 좁은 라벨의 높이를 쓴다.
    """
    anchor = first_line[0]
    below = [
        p
        for p in placed
        if p.hit is None
        and _CONTINUATION_MIN * unit < p.cy - anchor.cy <= _CONTINUATION_MAX * unit
        and abs(p.x0 - anchor.x0) <= 1.5 * unit
    ]
    if not below:
        return []
    start = min(below, key=lambda p: abs(p.x0 - anchor.x0))
    row = [
        p
        for p in placed
        if p.hit is None
        and abs(p.cy - start.cy) <= _ROW_TOLERANCE * unit
        and p.x0 >= start.x0 - 1.0
    ]
    return _contiguous_run(row, start.x0, unit)


def _find_value(
    label: _Placed, placed: list[_Placed], *, allow_below: bool, wrap: bool
) -> _Found | None:
    assert label.hit is not None
    if label.hit.inline_value:
        return _Found(label.hit.inline_value, (label.token,), label.hit.score)
    parts = _right_of(label, placed)
    if parts and wrap:
        parts = parts + _continuation(parts, placed, label.h)
    if not parts and allow_below:
        parts = _below(label, placed)
    if not parts:
        return None
    return _Found(
        " ".join(p.token.text for p in parts), tuple(p.token for p in parts), label.hit.score
    )


def _to_extracted[T](found: _Found, value: T) -> Extracted[T]:
    confidence = statistics.fmean(t.confidence for t in found.tokens) * found.label_score
    return Extracted[T](
        value=value,
        raw_text=found.raw_text,
        confidence=min(max(confidence, 0.0), 1.0),
        bbox=_union_bbox(found.tokens),
    )


def _union_bbox(tokens: tuple[OcrToken, ...]) -> BBox:
    return (
        min(t.bbox[0] for t in tokens),
        min(t.bbox[1] for t in tokens),
        max(t.bbox[2] for t in tokens),
        max(t.bbox[3] for t in tokens),
    )


def _first_parsed[T](
    key: _Key,
    placed: list[_Placed],
    labels: list[_Placed],
    parse: Callable[[str], T | None],
) -> Extracted[T] | None:
    """`key` 라벨들을 위에서 아래로 훑어 처음으로 형식에 맞는 값을 돌려준다."""
    for label in labels:
        if label.hit is None or label.hit.key != key:
            continue
        found = _find_value(
            label,
            placed,
            allow_below=key in _AMOUNT_KEYS,
            wrap=key == _Key.ADDRESS,
        )
        if found is None:
            continue
        value = parse(found.raw_text)
        if value is not None:
            return _to_extracted(found, value)
    return None


# --- 값 정규화 ---


def _parse_document_no(raw: str) -> str | None:
    squashed = _squash(raw).translate(_DASH_FIXES)
    return squashed if any(char.isdigit() for char in squashed) else None


def _parse_date(raw: str) -> date | None:
    match = _DATE_PATTERN.search(raw.translate(_DIGIT_FIXES))
    if match is None:
        return None
    year, month, day = (int(group) for group in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_amount(raw: str) -> int | None:
    digits = re.sub(r"[,\s원₩]", "", raw.translate(_DIGIT_FIXES))
    return int(digits) if digits.isdigit() and digits.isascii() else None


def _parse_business_number(raw: str) -> str | None:
    match = _BUSINESS_NUMBER_PATTERN.search(raw.translate(_DIGIT_FIXES))
    return "-".join(match.groups()) if match else None


def _parse_text(raw: str) -> str | None:
    text = raw.strip()
    return text or None


# --- 공급자/공급받는자 ---


def _owner_role(label: _Placed, roles: list[_Placed]) -> _Placed | None:
    """필드 라벨 위쪽에서 가장 가까운 줄의 역할 라벨. 같은 줄에 둘이면 가로로 가까운 쪽이다."""
    above = [r for r in roles if r.cy < label.cy - 0.3 * label.h]
    if not above:
        return None
    nearest_cy = max(r.cy for r in above)
    same_line = [r for r in above if nearest_cy - r.cy <= 0.8 * r.h]
    return min(same_line, key=lambda r: abs(r.cx - label.cx))


def _extract_parties(
    placed: list[_Placed], labels: list[_Placed]
) -> tuple[PartyFields, PartyFields]:
    roles = [p for p in labels if p.hit is not None and p.hit.key in _ROLE_KEYS]
    owned: dict[_Key, list[_Placed]] = {_Key.SUPPLIER_ROLE: [], _Key.BUYER_ROLE: []}
    for label in labels:
        if label.hit is None or label.hit.key not in _PARTY_KEYS:
            continue
        role = _owner_role(label, roles)
        if role is not None and role.hit is not None:
            owned[role.hit.key].append(label)

    return (
        _build_party(placed, owned[_Key.SUPPLIER_ROLE]),
        _build_party(placed, owned[_Key.BUYER_ROLE]),
    )


def _build_party(placed: list[_Placed], labels: list[_Placed]) -> PartyFields:
    return PartyFields(
        name=_first_parsed(_Key.NAME, placed, labels, _parse_text),
        business_number=_first_parsed(_Key.BUSINESS_NUMBER, placed, labels, _parse_business_number),
        representative=_first_parsed(_Key.REPRESENTATIVE, placed, labels, _parse_text),
        address=_first_parsed(_Key.ADDRESS, placed, labels, _parse_text),
    )
