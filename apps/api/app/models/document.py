"""업로드 문서와 OCR 결과."""
import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    Json,
    created_at_column,
    enum_column,
    updated_at_column,
    uuid_pk,
)

if TYPE_CHECKING:
    from app.models.extraction import Extraction


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    REVIEWED = "reviewed"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    original_filename: Mapped[str] = mapped_column(String(255))
    # 저장소 기준 상대 경로. 절대 경로는 저장하지 않는다
    storage_path: Mapped[str] = mapped_column(String(512))
    # 파일 내용 SHA-256(16진수). 같은 파일 재업로드를 허용하므로 유일 제약은 걸지 않는다
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[DocumentStatus] = mapped_column(
        enum_column(DocumentStatus), default=DocumentStatus.UPLOADED, index=True
    )
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    # status가 failed일 때의 사용자용 사유. 내부 예외 메시지는 담지 않는다
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column(index=True)
    updated_at: Mapped[datetime] = updated_at_column()

    ocr_results: Mapped[list["OcrResult"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    extractions: Mapped[list["Extraction"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class OcrResult(Base):
    __tablename__ = "ocr_results"
    __table_args__ = (UniqueConstraint("document_id", "page_number", "engine"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int] = mapped_column(Integer)
    engine: Mapped[str] = mapped_column(String(50))
    elapsed_ms: Mapped[int] = mapped_column(Integer)
    # 처리한 이미지 크기. bbox 좌표계의 기준이다
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    # [{"text": str, "bbox": [x_min, y_min, x_max, y_max], "confidence": float}, ...]
    tokens: Mapped[list[dict[str, object]]] = mapped_column(Json)
    created_at: Mapped[datetime] = created_at_column()

    document: Mapped[Document] = relationship(back_populates="ocr_results")
