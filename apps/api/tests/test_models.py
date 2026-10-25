"""태스크 7: SQLAlchemy 모델 CRUD, 제약, 마이그레이션 일치 테스트. SQLite 메모리 DB로 돈다."""
import hashlib
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.models import (
    Base,
    Document,
    DocumentStatus,
    Extraction,
    ExtractionMethod,
    LineItem,
    OcrResult,
    ReviewEdit,
    ReviewStatus,
)

API_ROOT = Path(__file__).resolve().parent.parent


def make_engine(url: str = "sqlite://") -> Engine:
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: object, _record: object) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

    return engine


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def make_document(name: str = "invoice.png") -> Document:
    return Document(
        original_filename=name,
        storage_path=f"uploads/{name}",
        content_hash=hashlib.sha256(name.encode()).hexdigest(),
        mime_type="image/png",
        size_bytes=1234,
    )


def make_extraction(document: Document) -> Extraction:
    return Extraction(
        document=document,
        method=ExtractionMethod.RULE,
        header={"document_no": "2025-0001", "supplier": {"name": "가나다상사"}},
        confidence=0.93,
        validation={"errors": [], "warnings": ["합계 불일치"]},
    )


def test_문서는_기본_상태와_시각이_채워지고_저장된다(session: Session) -> None:
    session.add(make_document())
    session.commit()

    saved = session.scalars(select(Document)).one()

    assert saved.id is not None
    assert saved.status is DocumentStatus.UPLOADED
    assert saved.page_count == 1
    assert saved.created_at is not None
    assert saved.updated_at is not None
    assert saved.error_message is None


def test_문서_상태를_바꾸면_수정_시각이_갱신된다(session: Session) -> None:
    document = make_document()
    session.add(document)
    session.commit()
    before = document.updated_at

    document.status = DocumentStatus.PROCESSING
    session.commit()
    session.refresh(document)

    assert document.status is DocumentStatus.PROCESSING
    assert document.updated_at >= before


def test_같은_해시의_문서를_두_번_올릴_수_있다(session: Session) -> None:
    first, second = make_document("a.png"), make_document("b.png")
    second.content_hash = first.content_hash
    session.add_all([first, second])

    session.commit()

    assert len(session.scalars(select(Document)).all()) == 2


def test_OCR_결과는_토큰_JSON을_그대로_돌려준다(session: Session) -> None:
    document = make_document()
    tokens = [{"text": "거래명세서", "bbox": [10, 20, 110, 60], "confidence": 0.99}]
    document.ocr_results.append(
        OcrResult(
            page_number=1,
            engine="paddleocr",
            elapsed_ms=4300,
            width=2339,
            height=1654,
            tokens=tokens,
        )
    )
    session.add(document)
    session.commit()
    session.expire_all()

    saved = session.scalars(select(OcrResult)).one()

    assert saved.tokens == tokens
    assert saved.document.original_filename == "invoice.png"


def test_문서_페이지_엔진_조합은_유일하다(session: Session) -> None:
    document = make_document()
    for _ in range(2):
        document.ocr_results.append(
            OcrResult(page_number=1, engine="paddleocr", elapsed_ms=1, width=1, height=1, tokens=[])
        )
    session.add(document)

    with pytest.raises(IntegrityError):
        session.commit()


def test_추출_결과는_기본_리뷰_상태가_대기이고_JSON을_보존한다(session: Session) -> None:
    document = make_document()
    extraction = make_extraction(document)
    session.add(extraction)
    session.commit()
    session.expire_all()

    saved = session.scalars(select(Extraction)).one()

    assert saved.review_status is ReviewStatus.PENDING
    assert saved.method is ExtractionMethod.RULE
    assert saved.header["supplier"] == {"name": "가나다상사"}
    assert saved.validation["warnings"] == ["합계 불일치"]
    assert saved.confidence == pytest.approx(0.93)


def test_품목은_순번_순서로_돌려주고_소수_수량과_큰_금액을_담는다(session: Session) -> None:
    extraction = make_extraction(make_document())
    extraction.line_items.extend(
        [
            LineItem(
                position=2, name="B", quantity=Decimal("1"), unit_price=100, supply_amount=100
            ),
            LineItem(
                position=1,
                name="A",
                spec="6.5oz",
                quantity=Decimal("2.5"),
                unit_price=5_000_000_000,
                supply_amount=12_500_000_000,
                tax_amount=1_250_000_000,
                remark="긴급",
                bbox=[1, 2, 3, 4],
            ),
        ]
    )
    session.add(extraction)
    session.commit()
    session.expire_all()

    items = session.scalars(select(Extraction)).one().line_items

    assert [item.name for item in items] == ["A", "B"]
    assert items[0].quantity == Decimal("2.5")
    assert items[0].supply_amount == 12_500_000_000
    assert items[0].bbox == [1, 2, 3, 4]
    assert items[1].tax_amount is None


def test_추출_안에서_품목_순번은_유일하다(session: Session) -> None:
    extraction = make_extraction(make_document())
    for _ in range(2):
        extraction.line_items.append(LineItem(position=1, name="A", quantity=Decimal("1")))
    session.add(extraction)

    with pytest.raises(IntegrityError):
        session.commit()


def test_수정_이력은_이전_값과_이후_값을_저장한다(session: Session) -> None:
    extraction = make_extraction(make_document())
    extraction.edits.append(
        ReviewEdit(
            field_path="header.document_no",
            old_value="2025-0001",
            new_value="2025-0002",
            editor="reviewer",
        )
    )
    session.add(extraction)
    session.commit()

    edit = session.scalars(select(ReviewEdit)).one()

    assert (edit.old_value, edit.new_value) == ("2025-0001", "2025-0002")
    assert edit.line_item_id is None
    assert edit.created_at is not None


def test_문서를_지우면_하위_데이터가_함께_지워진다(session: Session) -> None:
    document = make_document()
    document.ocr_results.append(
        OcrResult(page_number=1, engine="paddleocr", elapsed_ms=1, width=1, height=1, tokens=[])
    )
    extraction = make_extraction(document)
    extraction.line_items.append(LineItem(position=1, name="A", quantity=Decimal("1")))
    extraction.edits.append(
        ReviewEdit(field_path="header.document_no", old_value="x", new_value="y")
    )
    session.add(extraction)
    session.commit()

    session.delete(document)
    session.commit()

    for model in (Document, OcrResult, Extraction, LineItem, ReviewEdit):
        assert session.scalars(select(model)).all() == []


def test_품목을_지워도_수정_이력은_남는다(session: Session) -> None:
    extraction = make_extraction(make_document())
    item = LineItem(position=1, name="A", quantity=Decimal("1"))
    extraction.line_items.append(item)
    session.add(extraction)
    session.commit()
    extraction.edits.append(
        ReviewEdit(field_path="items.0.name", old_value="A", new_value="B", line_item_id=item.id)
    )
    session.commit()

    session.delete(item)
    session.commit()

    edit = session.scalars(select(ReviewEdit)).one()
    assert edit.line_item_id is None


def test_조회에_쓰는_컬럼에_인덱스가_있다(session: Session) -> None:
    inspector = inspect(session.get_bind())

    def indexed(table: str) -> set[str]:
        return {
            column
            for index in inspector.get_indexes(table)
            for column in index["column_names"]
            if column is not None
        }

    assert {"status", "created_at", "content_hash"} <= indexed("documents")
    assert "document_id" in indexed("ocr_results")
    assert {"document_id", "review_status"} <= indexed("extractions")
    assert "extraction_id" in indexed("line_items")
    assert {"extraction_id", "created_at"} <= indexed("review_edits")


def alembic_config(url: str) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_마이그레이션을_올리면_모델과_스키마_차이가_없다(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"

    command.upgrade(alembic_config(url), "head")

    engine = make_engine(url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()
    assert diff == []


def test_마이그레이션을_내리면_테이블이_모두_사라진다(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'down.db'}"
    config = alembic_config(url)
    command.upgrade(config, "head")

    command.downgrade(config, "base")

    engine = make_engine(url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
