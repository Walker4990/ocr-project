"""규칙 기반 헤더 추출기 단위 테스트. 토큰을 직접 만들어 레이아웃별 동작을 확인한다."""

import math
from datetime import date

import pytest

from app.extraction.rule_extractor import extract_header_fields
from app.ocr.engine import OcrPage, OcrToken

LABEL_H = 50.0


def tok(text: str, x: float, y: float, w: float = 100.0, h: float = LABEL_H, conf: float = 0.98):
    return OcrToken(text=text, bbox=(x, y, x + w, y + h), confidence=conf)


def page(*tokens: OcrToken) -> OcrPage:
    return OcrPage(width=1654, height=2339, tokens=tuple(tokens))


def skew(token: OcrToken, degrees: float, origin_x: float = 0.0) -> OcrToken:
    """글줄이 오른쪽으로 내려가게 기울이고, 실제 OCR처럼 바깥 사각형을 세로로 부풀린다."""
    x0, y0, x1, y1 = token.bbox
    tan = math.tan(math.radians(degrees))
    shift = tan * ((x0 + x1) / 2 - origin_x)
    swell = abs(tan) * (x1 - x0) / 2
    return OcrToken(token.text, (x0, y0 + shift - swell, x1, y1 + shift + swell), token.confidence)


def side_by_side() -> list[OcrToken]:
    """공급자는 왼쪽, 공급받는자는 오른쪽 열인 양식."""
    return [
        tok("공급자", 410, 320),
        tok("공급받는자", 1120, 320, w=150),
        tok("상호", 160, 390),
        tok("유한회사 가온", 290, 390, w=300),
        tok("상호", 900, 390),
        tok("주식회사 백제", 1030, 390, w=180),
        tok("등록번호", 135, 455, w=120),
        tok("495-54-06637", 290, 455, w=210),
        tok("등록번호", 870, 455, w=120),
        tok("366-66-79612", 1025, 455, w=210),
        tok("대표자", 150, 515),
        tok("허준영", 285, 515),
        tok("대표자", 885, 515),
        tok("김준혁", 1025, 515),
        tok("주소", 160, 575),
        tok("전라남도 서산시 서초대길 지하144", 290, 575, w=450),
        tok("(수빈김마을)", 292, 620, w=170),
        tok("주소", 895, 575),
        tok("세종특별자치도 금천구 영동대가", 1030, 575, w=410),
        tok("990-71(진호박김마을)", 1026, 618, w=300),
    ]


def stacked() -> list[OcrToken]:
    """공급자 블록 아래에 공급받는자 블록이 이어지는 양식."""
    return [
        tok("공급자", 775, 320),
        tok("상호", 160, 382),
        tok("(주) 모두네트웍스", 286, 382, w=240),
        tok("등록번호", 130, 442, w=130),
        tok("238-73-10335", 286, 450, w=215),
        tok("대표자", 145, 505),
        tok("박재호", 282, 505),
        tok("주소", 157, 570),
        tok("강원특별자치도 정선군 개포가713", 288, 573, w=450),
        tok("공급받는자", 750, 660, w=155),
        tok("상호", 158, 722),
        tok("(유)한강마루네트워크", 289, 725, w=290),
        tok("등록번호", 130, 786, w=130),
        tok("362-16-81178", 286, 789, w=215),
        tok("대표자", 145, 848),
        tok("김경자", 284, 848),
        tok("주소", 155, 906),
        tok("울산광역시 서초구 선릉로 783", 286, 909, w=400),
    ]


def test_라벨과_값이_한_토큰에_붙어_있어도_문서번호와_작성일을_읽는다() -> None:
    result = extract_header_fields(
        page(
            tok("문서번호:2026-9172", 120, 240, w=290), tok("작성일자:2026-04-29", 1056, 240, w=300)
        )
    )

    assert result.document_no is not None
    assert result.document_no.value == "2026-9172"
    assert result.issue_date is not None
    assert result.issue_date.value == date(2026, 4, 29)


def test_라벨과_값이_별도_토큰이면_오른쪽_값을_읽는다() -> None:
    result = extract_header_fields(
        page(tok("문서번호", 120, 240, w=150), tok("2026-0151", 300, 242, w=180))
    )

    assert result.document_no is not None
    assert result.document_no.value == "2026-0151"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("작성일자:2025-03-07", date(2025, 3, 7)),
        ("작성일자:2026년 07월 09일", date(2026, 7, 9)),
        ("작성일자:2026년04월 13일", date(2026, 4, 13)),
        ("작성일자:2026년 06월17일", date(2026, 6, 17)),
        ("작성일자:2026.04.29", date(2026, 4, 29)),
        ("작성일자:2O26-04-29", date(2026, 4, 29)),
    ],
)
def test_여러_날짜_표기를_ISO_날짜로_바꾼다(text: str, expected: date) -> None:
    result = extract_header_fields(page(tok(text, 1050, 240, w=380)))

    assert result.issue_date is not None
    assert result.issue_date.value == expected
    assert result.issue_date.raw_text == text.split(":", 1)[1]


@pytest.mark.parametrize(
    "text", ["작성일자:2026년 03월1구일", "작성일자:2026-13-40", "작성일자:미정"]
)
def test_날짜로_읽을_수_없으면_값을_만들지_않는다(text: str) -> None:
    result = extract_header_fields(page(tok(text, 1050, 240, w=380)))

    assert result.issue_date is None


def test_좌우_배치에서_열별로_공급자와_공급받는자를_가른다() -> None:
    result = extract_header_fields(page(*side_by_side()))

    assert result.supplier.name is not None and result.supplier.name.value == "유한회사 가온"
    assert result.buyer.name is not None and result.buyer.name.value == "주식회사 백제"
    assert result.supplier.business_number is not None
    assert result.supplier.business_number.value == "495-54-06637"
    assert result.buyer.business_number is not None
    assert result.buyer.business_number.value == "366-66-79612"
    assert result.supplier.representative is not None
    assert result.supplier.representative.value == "허준영"
    assert result.buyer.representative is not None
    assert result.buyer.representative.value == "김준혁"


def test_위아래_배치에서_가까운_위쪽_역할_라벨로_공급자와_공급받는자를_가른다() -> None:
    result = extract_header_fields(page(*stacked()))

    assert result.supplier.name is not None and result.supplier.name.value == "(주) 모두네트웍스"
    assert result.buyer.name is not None and result.buyer.name.value == "(유)한강마루네트워크"
    assert result.supplier.business_number is not None
    assert result.supplier.business_number.value == "238-73-10335"
    assert result.buyer.business_number is not None
    assert result.buyer.business_number.value == "362-16-81178"
    assert result.buyer.address is not None
    assert result.buyer.address.value == "울산광역시 서초구 선릉로 783"


def test_둘째_줄로_넘어간_주소를_이어_붙인다() -> None:
    result = extract_header_fields(page(*side_by_side()))

    assert result.supplier.address is not None
    assert result.supplier.address.value == "전라남도 서산시 서초대길 지하144 (수빈김마을)"
    assert result.buyer.address is not None
    assert result.buyer.address.value == "세종특별자치도 금천구 영동대가 990-71(진호박김마을)"


def test_주소_아래의_다른_열이나_먼_줄_토큰은_주소에_붙이지_않는다() -> None:
    tokens = [
        *side_by_side(),
        tok("No", 125, 730, w=55),
        tok("품목", 420, 730, w=65),
    ]

    result = extract_header_fields(page(*tokens))

    assert result.supplier.address is not None
    assert "No" not in result.supplier.address.value
    assert "품목" not in result.supplier.address.value


def test_금액은_라벨_아래_칸의_값을_읽고_열별로_짝짓는다() -> None:
    result = extract_header_fields(
        page(
            tok("공급가액", 288, 1278, w=120),
            tok("세액", 792, 1278, w=70),
            tok("합계금액", 1245, 1278, w=120),
            tok("853,300", 450, 1340, w=130),
            tok("85,330", 947, 1340, w=110),
            tok("938,630", 1407, 1340, w=128),
        )
    )

    assert result.supply_amount is not None and result.supply_amount.value == 853_300
    assert result.tax_amount is not None and result.tax_amount.value == 85_330
    assert result.total_amount is not None and result.total_amount.value == 938_630


def test_금액_표기의_쉼표_공백_원을_무시한다() -> None:
    result = extract_header_fields(
        page(
            tok("합계금액", 1245, 1278, w=120),
            tok("1, 234 원", 1407, 1340, w=128),
        )
    )

    assert result.total_amount is not None
    assert result.total_amount.value == 1234


def test_숫자가_아닌_금액은_값을_만들지_않는다() -> None:
    result = extract_header_fields(
        page(tok("합계금액", 1245, 1278, w=120), tok("육십만", 1407, 1340, w=128))
    )

    assert result.total_amount is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("495-54-06637", "495-54-06637"),
        ("495 54 06637", "495-54-06637"),
        ("4955406637", "495-54-06637"),
        ("495-54-O6637", "495-54-06637"),
    ],
)
def test_사업자등록번호를_하이픈_형식으로_맞춘다(text: str, expected: str) -> None:
    tokens = [tok("공급자", 410, 320), tok("등록번호", 135, 455, w=120), tok(text, 290, 455, w=210)]

    result = extract_header_fields(page(*tokens))

    assert result.supplier.business_number is not None
    assert result.supplier.business_number.value == expected


def test_사업자등록번호_형식이_아니면_값을_만들지_않는다() -> None:
    tokens = [tok("공급자", 410, 320), tok("등록번호", 135, 455, w=120), tok("49-5", 290, 455)]

    result = extract_header_fields(page(*tokens))

    assert result.supplier.business_number is None


@pytest.mark.parametrize("degrees", [-4.0, 2.0, 4.0, 8.0])
def test_기울어진_문서에서도_행과_열을_맞춰_읽는다(degrees: float) -> None:
    tokens = [
        skew(token, degrees)
        for token in [*side_by_side(), tok("문서번호:2026-9172", 120, 240, w=290)]
    ]

    result = extract_header_fields(page(*tokens))

    assert result.document_no is not None and result.document_no.value == "2026-9172"
    assert result.supplier.name is not None and result.supplier.name.value == "유한회사 가온"
    assert result.buyer.name is not None and result.buyer.name.value == "주식회사 백제"
    assert result.supplier.address is not None
    assert result.supplier.address.value == "전라남도 서산시 서초대길 지하144 (수빈김마을)"
    assert result.buyer.business_number is not None
    assert result.buyer.business_number.value == "366-66-79612"


def test_OCR이_글자를_조금_틀린_라벨도_알아본다() -> None:
    tokens = [
        tok("공급자", 410, 320),
        tok("등록번오", 135, 455, w=120),
        tok("495-54-06637", 290, 455, w=210),
    ]

    result = extract_header_fields(page(*tokens))

    assert result.supplier.business_number is not None
    assert result.supplier.business_number.value == "495-54-06637"


def test_신뢰도는_OCR_신뢰도를_따르고_0과_1_사이다() -> None:
    high = extract_header_fields(page(tok("문서번호:2026-9172", 120, 240, w=290, conf=0.99)))
    low = extract_header_fields(page(tok("문서번호:2026-9172", 120, 240, w=290, conf=0.5)))

    assert high.document_no is not None and low.document_no is not None
    assert 0.0 <= low.document_no.confidence < high.document_no.confidence <= 1.0


def test_라벨이_아닌_값_토큰의_평균_신뢰도를_쓴다() -> None:
    tokens = [
        tok("공급자", 410, 320),
        tok("주소", 160, 575),
        tok("서울시", 290, 575, w=150, conf=0.9),
        tok("(수빈마을)", 292, 625, w=170, conf=0.7),
    ]

    result = extract_header_fields(page(*tokens))

    assert result.supplier.address is not None
    assert result.supplier.address.confidence == pytest.approx(0.8, abs=0.05)


def test_값의_bbox는_값_토큰들을_감싼다() -> None:
    result = extract_header_fields(page(*side_by_side()))

    assert result.supplier.address is not None
    assert result.supplier.address.bbox == (290.0, 575.0, 740.0, 670.0)


def test_토큰이_없으면_모든_필드가_비어_있다() -> None:
    result = extract_header_fields(page())

    assert result.document_no is None
    assert result.issue_date is None
    assert result.supplier.name is None
    assert result.buyer.address is None
    assert result.total_amount is None


def test_역할_라벨이_없으면_당사자_필드는_비워_둔다() -> None:
    tokens = [t for t in side_by_side() if t.text not in {"공급자", "공급받는자"}]

    result = extract_header_fields(page(*tokens))

    assert result.supplier.name is None
    assert result.buyer.name is None


def test_결과는_JSON으로_직렬화된다() -> None:
    result = extract_header_fields(
        page(*side_by_side(), tok("작성일자:2026-04-29", 1056, 240, w=300))
    )

    dumped = result.model_dump(mode="json")

    assert dumped["issue_date"]["value"] == "2026-04-29"
    assert dumped["supplier"]["name"]["value"] == "유한회사 가온"


def test_줄_간격이_라벨_높이보다_좁아도_둘째_줄을_한_번만_붙인다() -> None:
    """저해상도 이미지: 라벨 높이(26)가 줄 간격(16)보다 커서 둘째 줄도 같은 줄로 잡히던 경우."""
    tokens = [
        tok("공급자", 156, 123, w=37, h=20),
        tok("주소", 59, 216, w=29, h=26),
        tok("전북특별자치도 예산군도산대가256", 110, 217, w=183, h=20),
        tok("(동현고조리)", 110, 233, w=65, h=21),
    ]

    result = extract_header_fields(page(*tokens))

    assert result.supplier.address is not None
    assert result.supplier.address.value == "전북특별자치도 예산군도산대가256 (동현고조리)"


def test_OCR이_라벨_글자를_틀리고_값이_붙은_토큰도_알아본다() -> None:
    result = extract_header_fields(page(tok("문사번호:2025-1223", 45, 89, w=110, h=14)))

    assert result.document_no is not None
    assert result.document_no.value == "2025-1223"


def test_하이픈이_긴_대시로_읽혀도_문서번호를_하이픈으로_맞춘다() -> None:
    result = extract_header_fields(page(tok("문서번호:2026–5413", 45, 89, w=110, h=14)))

    assert result.document_no is not None
    assert result.document_no.value == "2026-5413"
