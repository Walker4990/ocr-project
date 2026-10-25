# api와 worker가 같은 이미지를 쓰고 command만 다르다
FROM python:3.12-slim

# paddle/opencv가 요구하는 공유 라이브러리
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

RUN useradd --create-home --uid 1000 app
WORKDIR /app

# 의존성 레이어를 먼저 만들어 코드만 바뀔 때 캐시를 재사용한다
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN mkdir -p /app/data/uploads /app/logs /home/app/.paddlex \
    && chown -R app:app /app/data /app/logs /home/app

USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
