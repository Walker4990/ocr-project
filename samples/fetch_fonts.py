"""골든셋 렌더링에 쓰는 OFL 라이선스 한글 폰트(나눔 시리즈)를 samples/fonts/에 내려받는다."""
import urllib.request
from pathlib import Path

BASE_URL = "https://github.com/google/fonts/raw/main/ofl"
FONTS = {
    "NanumGothic-Regular.ttf": "nanumgothic",
    "NanumGothic-Bold.ttf": "nanumgothic",
    "NanumMyeongjo-Regular.ttf": "nanummyeongjo",
    "NanumGothicCoding-Regular.ttf": "nanumgothiccoding",
}
FONT_DIR = Path(__file__).parent / "fonts"


def fetch_fonts(font_dir: Path = FONT_DIR) -> None:
    font_dir.mkdir(parents=True, exist_ok=True)
    for name, family in FONTS.items():
        target = font_dir / name
        if target.exists():
            continue
        print(f"다운로드: {name}")
        urllib.request.urlretrieve(f"{BASE_URL}/{family}/{name}", target)


if __name__ == "__main__":
    fetch_fonts()
