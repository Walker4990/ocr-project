"""추출 결과, 품목, 검수 수정 이력."""
import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    Json,
    JsonObject,
    created_at_column,
    enum_column,
    updated_at_column,
    uuid_pk,
)
from app.models.document import Document


class ExtractionMethod(StrEnum):
    RULE = "rule"
    LLM = "llm"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[ExtractionMethod] = mapped_column(enum_column(ExtractionMethod))
    # 발행일, 문서번호, 공급자/공급받는자, 합계 등 헤더 필드. 필드별 bbox와 신뢰도도 이 안에 둔다
    header: Mapped[JsonObject] = mapped_column(Json)
    # 전체 신뢰도 0~1
    confidence: Mapped[float | None] = mapped_column(Float)
    # 검증기 결과: {"errors": [...], "warnings": [...]}
    validation: Mapped[JsonObject] = mapped_column(Json, default=dict)
    review_status: Mapped[ReviewStatus] = mapped_column(
        enum_column(ReviewStatus), default=ReviewStatus.PENDING, index=True
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    document: Mapped[Document] = relationship(back_populates="extractions")
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="extraction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LineItem.position",
    )
    edits: Mapped[list["ReviewEdit"]] = relationship(
        back_populates="extraction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ReviewEdit.created_at, ReviewEdit.id",
    )


class LineItem(Base):
    __tablename__ = "line_items"
    __table_args__ = (UniqueConstraint("extraction_id", "position"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extractions.id", ondelete="CASCADE"), index=True
    )
    # 표에서의 순번(1부터)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    spec: Mapped[str | None] = mapped_column(String(255))
    # 소수 수량(예: 2.5)이 있을 수 있어 Numeric이다
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    # 금액은 원 단위 정수
    unit_price: Mapped[int | None] = mapped_column(BigInteger)
    supply_amount: Mapped[int | None] = mapped_column(BigInteger)
    tax_amount: Mapped[int | None] = mapped_column(BigInteger)
    remark: Mapped[str | None] = mapped_column(String(255))
    # 행 전체의 [x_min, y_min, x_max, y_max]
    bbox: Mapped[list[int] | None] = mapped_column(Json)

    extraction: Mapped[Extraction] = relationship(back_populates="line_items")


class ReviewEdit(Base):
    __tablename__ = "review_edits"
    __table_args__ = (
        Index("ix_review_edits_extraction_id_created_at", "extraction_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extractions.id", ondelete="CASCADE")
    )
    # 품목을 지워도 이력은 남긴다
    line_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("line_items.id", ondelete="SET NULL")
    )
    # 예: "header.document_no", "items.2.quantity"
    field_path: Mapped[str] = mapped_column(String(255))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    # 인증이 없어 사용자 식별자 대신 자유 문자열이다
    editor: Mapped[str] = mapped_column(String(100), default="reviewer")
    created_at: Mapped[datetime] = created_at_column()

    extraction: Mapped[Extraction] = relationship(back_populates="edits")
