# 합성 거래명세서 골든셋

OCR 정확도를 측정하기 위한 합성 거래명세서와 정답 라벨이다. 실제 개인정보는 쓰지 않고, 모든 값은 seed로 재현된다.

## 구성

| 경로 | 내용 |
|---|---|
| `doculens_samples/schema.py` | 거래명세서 모델 (금액 정합성 검증 포함) |
| `doculens_samples/data.py` | Faker(ko_KR) 기반 가짜 데이터, 사업자번호 검증 숫자 |
| `doculens_samples/render.py` | Pillow로 그리는 양식 5종 |
| `doculens_samples/degrade.py` | 난이도 변형: `clean`, `skewed`, `low_res`, `photo` |
| `doculens_samples/labels.py` | 정답 라벨(`GoldenLabel`) 읽기/쓰기 |
| `doculens_samples/batch.py` | 배치 생성과 검증 |
| `golden/` | 생성 결과 (이미지 40장 + 라벨 JSON 40개) |
| `fetch_fonts.py` | OFL 나눔 폰트 다운로드 (`fonts/`는 커밋하지 않음) |

## 사용법

```powershell
python samples/fetch_fonts.py          # 폰트가 없을 때 한 번만
cd samples
uv run --project ..\apps\api python -m doculens_samples --count 40 --seed 0
```

양식 5종 x 난이도 4종 조합을 번갈아 채운다. 같은 `--seed`면 바이트까지 같은 결과가 나온다.

## 라벨 형식

이미지 `invoice_000.png`에 대해 `invoice_000.json`이 대응한다.

```json
{
  "image": "invoice_000.png",
  "template_id": "classic",
  "difficulty": "clean",
  "seed": 0,
  "invoice": {
    "document_no": "2025-0001",
    "issue_date": "2025-03-14",
    "supplier": { "name": "...", "business_number": "...", "representative": "...", "address": "..." },
    "buyer": { "...": "..." },
    "items": [{ "name": "...", "spec": "...", "quantity": 1, "unit_price": 1000, "amount": 1000 }],
    "supply_amount": 1000,
    "tax_amount": 100,
    "total_amount": 1100
  }
}
```

## 저장 형식

노이즈가 있는 `low_res`, `photo`는 JPEG(품질 85), 나머지는 PNG다. 노이즈 이미지를 PNG로 저장하면 장당 7MB가 되어 저장소에 넣기 어렵다.

## 폰트 라이선스

나눔고딕, 나눔명조, 나눔고딕코딩은 SIL OFL 1.1이다. 저장소에는 포함하지 않고 `fetch_fonts.py`로 받는다.
