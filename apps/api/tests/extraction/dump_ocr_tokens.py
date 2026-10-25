"""골든셋 이미지를 PaddleOCR로 읽어 토큰을 JSON 픽스처로 저장한다(재생성용 스크립트, 테스트 아님).

OCR 모델이 바뀌어 픽스처를 새로 만들 때만 쓴다(장당 약 5초, 50장 약 4분).
실행(apps/api에서): uv run python tests/extraction/dump_ocr_tokens.py
"""

import json
from pathlib import Path

from app.ocr import engines as engines  # import하면 OCR 엔진이 레지스트리에 등록된다
from app.ocr.engine import registry
from app.ocr.preprocessing import decode_image

ROOT = Path(__file__).resolve().parents[4]
GOLDEN_DIR = ROOT / "samples" / "golden"
OUT_DIR = Path(__file__).resolve().parent / "fixtures" / "ocr_tokens"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = registry.create("paddleocr")
    for image_path in sorted(GOLDEN_DIR.glob("invoice_*.*g")):
        page = engine.recognize(decode_image(image_path.read_bytes()))
        data = {
            "width": page.width,
            "height": page.height,
            "tokens": [
                {
                    "text": token.text,
                    "bbox": [round(v, 1) for v in token.bbox],
                    "confidence": round(token.confidence, 4),
                }
                for token in page.tokens
            ],
        }
        out_path = OUT_DIR / f"{image_path.stem}.json"
        out_path.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(image_path.stem, len(page.tokens), flush=True)


if __name__ == "__main__":
    main()
