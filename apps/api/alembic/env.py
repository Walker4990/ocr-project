"""Alembic 실행 환경. DB 주소는 `sqlalchemy.url` 옵션(테스트용)이 없으면 DATABASE_URL에서 읽는다."""
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.config import Settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    # 기존 로거(structlog 등)를 끄지 않는다
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def resolve_database_url() -> str:
    url = config.get_main_option("sqlalchemy.url") or Settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL 환경변수가 필요하다 (.env.example 참고)")
    return url


def run_migrations_offline() -> None:
    """DB에 연결하지 않고 SQL만 출력한다."""
    context.configure(
        url=resolve_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(resolve_database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
