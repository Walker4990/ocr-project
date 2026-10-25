"""모델 공통 기반: 선언 베이스, 제약 이름 규칙, 컬럼 타입 별칭."""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON as SqlJson
from sqlalchemy import DateTime, Enum, MetaData, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 제약 이름을 고정하면 마이그레이션에서 이름으로 지울 수 있다
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Postgres에서는 JSONB(인덱스·연산자 지원), 그 외(테스트용 SQLite)에서는 JSON
Json = SqlJson().with_variant(JSONB(), "postgresql")

JsonObject = dict[str, object]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def enum_column[E: StrEnum](enum_class: type[E]) -> Enum:
    """StrEnum을 값(소문자 문자열)으로 저장하는 VARCHAR 컬럼. DB 네이티브 enum은 쓰지 않는다."""

    def values(members: type[E]) -> list[str]:
        return [member.value for member in members]

    return Enum(enum_class, native_enum=False, length=20, values_callable=values)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def created_at_column(*, index: bool = False) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), index=index)


def updated_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
