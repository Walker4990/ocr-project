"""헤더 추출 결과 스키마. 규칙 추출기와 이후 LLM 추출기가 같은 형태로 돌려준다."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.ocr.engine import BBox


class Extracted[T](BaseModel):
    """추출한 값 하나. 검수 화면이 원문과 위치를 보여줄 수 있도록 함께 담는다."""

    model_config = ConfigDict(frozen=True)

    value: T
    # OCR이 읽은 그대로의 텍스트(정규화 전)
    raw_text: str
    # 값 토큰의 OCR 평균 신뢰도에 라벨 일치도를 곱한 점수. 확률이 아니라 순위용이다
    confidence: float = Field(ge=0.0, le=1.0)
    # 값 토큰들을 감싸는 상자. 원본 이미지 픽셀 좌표 (x_min, y_min, x_max, y_max)
    bbox: BBox


class PartyFields(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Extracted[str] | None = None
    business_number: Extracted[str] | None = None
    representative: Extracted[str] | None = None
    address: Extracted[str] | None = None


class HeaderFields(BaseModel):
    """읽지 못했거나 형식이 맞지 않은 필드는 None이다."""

    model_config = ConfigDict(frozen=True)

    document_no: Extracted[str] | None = None
    issue_date: Extracted[date] | None = None
    supplier: PartyFields = PartyFields()
    buyer: PartyFields = PartyFields()
    supply_amount: Extracted[int] | None = None
    tax_amount: Extracted[int] | None = None
    total_amount: Extracted[int] | None = None
