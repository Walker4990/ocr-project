"""FastAPI 진입점. 엔드포인트는 이후 태스크에서 라우터로 추가한다."""
from fastapi import FastAPI

from app.ocr import engines as engines  # import하면 OCR 엔진이 레지스트리에 등록된다

app = FastAPI(title="DocuLens API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
