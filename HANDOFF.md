# 세션 인계 메모

`/clear` 후 이어서 작업할 때 가장 먼저 읽는다. 전체 계획은 `ROADMAP.md`, 태스크 상세는 `task-master show <id>`.
이 파일은 진행 상황이 바뀔 때마다 갱신한다.

## 현재 상태 (태스크 2 완료 직후)

- 완료: 태스크 1 (모노레포 및 개발 환경), 2 (Docker Compose), 6 (골든셋 생성기), 8 (OcrEngine Protocol), 9 (PaddleOCR 어댑터)
- 다음: `task-master next`로 확인한다. 병렬로 3번, 4번, 10번도 가능하다
- 저장소는 독립 git이고 원격은 아직 없다
- 검증 상태: `pytest` 1105건(slow 1건 포함, 2번에서 4건 추가), `ruff`, `pyright`(strict) 통과. 웹 `npm run test` 2건, `tsc`, `lint`도 통과(2번 작업 직후 확인)
- 의존성 순서를 먼저 확인한다: 태스크를 고르기 전에 `task-master show <id>`의 Dependencies가 모두 done인지 본다 (이번에 9번이 8번에 의존하는 것을 놓쳐 인계 메모가 틀렸었다)

## OCR 인터페이스 (태스크 8 산출물)

- `apps/api/app/ocr/engine.py`: `OcrEngine` Protocol(`name`, `supports_gpu`, `recognize(image) -> OcrPage`), `OcrToken`(text, bbox, confidence), `OcrPage`(width, height, tokens, `text`), `EngineRegistry`, 모듈 전역 `registry`
- bbox는 `(x_min, y_min, x_max, y_max)` 원본 이미지 픽셀 좌표다. PaddleOCR의 4점 다각형은 어댑터에서 바깥 사각형으로 바꾼다. confidence는 0~1, bbox 좌표가 뒤집히면 `ValueError`
- 입력 이미지는 RGB `NDArray[np.uint8]`(높이 x 너비 x 3)다
- 엔진 선택: 이름 인자 > 환경변수 `OCR_ENGINE` > 기본 `paddleocr` 순이다. 모르는 이름은 `UnknownOcrEngineError`(등록된 엔진 목록 포함)
- numpy는 런타임 의존성이다(dev에서 옮겼다). Pillow, Faker는 여전히 dev 의존성이다. 업로드 이미지를 디코딩하는 단계(10번 부근)에서 Pillow가 런타임에 필요하면 옮긴다

## Docker Compose (태스크 2 산출물)

- 루트 `docker-compose.yml`: postgres 16, redis 7, api(8000), worker(arq), web(3000). 모든 서비스에 헬스체크가 있고 5개 모두 healthy 확인했다. 실행은 `.env.example`을 복사해 만든 로컬 설정 파일에 `POSTGRES_PASSWORD`를 채운 뒤 `docker compose up --build`
- api와 worker는 `apps/api/Dockerfile` 이미지를 공유한다(command만 다름). web은 `apps/web/Dockerfile`이고 **빌드 컨텍스트가 저장소 루트**다(workspaces의 lock 파일 때문). `NEXT_PUBLIC_API_URL`은 빌드 때 박히므로 바꾸면 web을 다시 빌드한다
- 볼륨: `pgdata`, `uploads`, `logs`, `paddlex-cache`(OCR 모델 캐시, `/home/app/.paddlex`). 컨테이너 안 접속 주소(DATABASE_URL, REDIS_URL)는 compose가 서비스 이름으로 덮어쓴다
- 이번에 만든 앱 진입점: `app/main.py`(FastAPI, `/health`)와 `app/worker.py`(arq, `ping` 작업). 둘 다 `app.ocr.engines`를 import해 OCR 엔진을 등록한다. arq는 등록된 함수가 없으면 시작하지 않아 `ping`을 뒀다. 실제 작업이 생기면 `ping`을 정리해도 된다
- `.env.example`의 `OCR_ENGINE`이 `ppocrv5`였는데 레지스트리 이름은 `paddleocr`라 고쳤다. `OCR_USE_GPU`도 추가했다
- 컨테이너 안 OCR 추론 확인함: 골든셋 `invoice_000`을 api 이미지에서 읽어 토큰 77개(호스트와 동일), (paddlepaddle 3.2.2 적용 후 모델 로딩 3.4초, 인식 3.2초; 적용 전엔 17초와 18초). 첫 실행은 모델을 내려받는다. 이미지는 paddle 때문에 크다. postgres는 아직 사용하는 코드가 없고, psycopg는 7번에서 추가한다
- postgres(5432)와 redis(6379) 포트는 `127.0.0.1`에만 연다(사용자 결정, 실제 바인딩 확인함). api·web 포트는 전체에 열려 있다
- opencv 3종 중복(python/headless/contrib)은 사용자 결정으로 보류. 이미지 크기가 문제가 될 때 uv override로 정리를 검토한다
- 컨테이너는 검증 후 `docker compose down`으로 내렸다(볼륨은 유지)

## PaddleOCR 어댑터 (태스크 9 산출물)

- `apps/api/app/ocr/engines/paddleocr_adapter.py`, 테스트 `apps/api/tests/ocr/test_paddleocr_adapter.py`. `app.ocr.engines`를 import하면 `registry`에 `paddleocr`가 등록된다(`app/main.py`, `app/worker.py`가 시작 시 import한다). `create()` 때 모델을 로드하고, import만으로는 paddle을 import하지 않는다
- 설치: `paddleocr 3.4.1` + `paddlepaddle 3.3.1` (uv add). PP-OCRv5 한국어는 3.x에서만 된다. opencv 패키지가 3종 깔려 있지만(python/headless/contrib) 동작에 문제는 없다
- 환경변수 `OCR_USE_GPU`(1/true/on, 기본 CPU). 인식 모델은 `korean_PP-OCRv5_mobile_rec`, 검출 모델은 CPU면 `PP-OCRv5_mobile_det`, GPU면 `PP-OCRv5_server_det`. 모델은 첫 실행 때 `~/.paddlex`로 내려받는다
- **함정 1 (paddlepaddle 버전)**: **paddlepaddle을 3.2.2로 고정했다.** 3.3.1 CPU는 oneDNN 경로에서 `NotImplementedError: ConvertPirAttribute2RuntimeAttribute`를 낸다. 처음엔 `enable_mkldnn=False`로 우회했는데, 그러면 CPU 가속이 꺼져 인식이 5배 이상 느렸다(아래). 3.3 이상으로 올리기 전에 oneDNN이 되는지 확인한다
- **함정 2 (속도)**: 2339x1654 한 장이 CPU에서 서버 검출 모델 약 190초, 모바일 검출 모델 약 21초(oneDNN 끔)였다. 단계별로 재니 검출 2.7초, **인식 18초**(크롭 77개)로 인식이 병목이었고, 스레드 수·배치·입력 축소는 효과가 없었다. oneDNN을 켜니(paddlepaddle 3.2.2) 호스트 평균 **16.5초 → 5.0초**(중앙값 4.3, 최대 11.9), 컨테이너에서 인식 3.2초. 인식 텍스트는 50장 모두 이전과 완전히 동일하고 필드 일치도 1071개로 같다. 검출 모델 이름만 바꾸면 인식 모델이 중국어로 돌아가 한글이 깨지므로 둘 다 지정해야 한다
- bbox는 4점 다각형의 바깥 사각형을 이미지 경계로 자른 값이고, 입력은 RGB를 BGR로 뒤집어 넘긴다. 빈 텍스트 토큰은 버린다
- 느린 실제 모델 테스트는 `@pytest.mark.slow`다. 빠른 실행은 `uv run pytest -m "not slow"`
- 골든셋 3장 육안 확인(수치 아님, CPU 모바일 검출): `invoice_000`(인쇄 77토큰, 평균 신뢰도 0.985, 21초), `invoice_002`(인쇄 59토큰, 0.983, 17초), `invoice_040`(손글씨 모사 59토큰, 0.961, 16초). 제목, 문서번호, 날짜, 상호, 사업자번호, 대표자, 주소 헤더부는 라벨과 일치하게 읽었다. 손글씨 모사본도 헤더부는 잘 읽었고 최저 신뢰도는 0.44(`-` 기호). 품목 표 이하는 눈으로 확인하지 않았다
- **골든셋 50장 간이 측정** (2026-10-24, CPU 모바일 검출, 평균 16.5초/장). 지표는 "라벨 값이 OCR 전체 텍스트에 공백·쉼표를 무시하고 그대로 들어 있는가"뿐이다. 위치, 공급자/공급받는자 구분, 문자 단위 오류율은 보지 않는다. 스크립트는 저장소에 넣지 않았다(벤치마크 태스크에서 제대로 만든다). 필드 1160개 중 1071개 일치(92%)
  - 인쇄체 40장 94%, 손글씨 모사 10장 85%. 난이도(clean 91, low_res 93, photo 93, skewed 94)와 양식(88~96)은 차이가 작다
  - 필드별: 대표자 100, 사업자번호 99, 품목 금액 99, 문서번호 98, 합계 98, 날짜 96, 상호 95, **품목명 87, 주소 58**
  - 주소·품목명이 낮은 이유(실패 사례를 몇 건 직접 본 것이고 전부 분석한 것은 아니다): 주소는 둘째 줄로 줄바꿈된 `(서현이읍)`·`지하146`이 별도 토큰이 되어 문자열이 끊긴 경우가 있고, `양천구`→`양전구` 같은 진짜 오인식도 있다. 품목명은 `6.5oz`를 `6.50z`(영문 o를 숫자 0)로 읽는 패턴이 반복된다. 손글씨 모사는 품목명 73%로 가장 약하다
  - 따라서 주소는 토큰 위치(bbox)로 줄을 합치는 후처리가 필요할 수 있다. 판단은 추출기 태스크에서 한다
- **CPU 속도 실험** (oneDNN 끈 상태, invoice_000/040, 초): 기준 20.9/15.0, 스레드 6개 26.5/18.2, 스레드 12개 20.9/16.4, 인식 배치 16 20.5/16.0, 입력 1280 축소 19.2/15.2로 모두 효과 없었다. 원인은 oneDNN을 꺼 둔 것이었고 paddlepaddle 3.2.2로 해결했다(위 함정 2). 위 3장 수치와 50장 측정의 시간(16.5초)은 해결 전 값이다. 정확도 수치는 해결 후에도 같다
- 모델 로딩은 처음엔 약 17초였고 캐시가 있는 컨테이너에서는 3.4초였다. 그래도 워커 시작 시 한 번만 로드하고 상주시켜야 한다(작업마다 로드하면 안 된다)

## 골든셋 (태스크 6 산출물)

- 생성기: `samples/doculens_samples/`, 테스트: `samples/tests/`, 설명: `samples/README.md`
- 결과물 `samples/golden/`: 50장 + 라벨 JSON 50개(14.8MB)를 **커밋했다** (사용자 결정). 인쇄체 40장(`invoice_000~039`)은 양식 5종 x 난이도 4종(clean/skewed/low_res/photo)이 각 2장씩이고, 손글씨 모사 10장(`invoice_040~049`, 라벨 `writing: handwritten`)이 이어진다
- 손글씨는 폰트로 흉내 낸 모사다(실제 필기 아님). 값 칸만 손글씨체로 쓰고 라벨과 No 열은 인쇄체다. 이 데이터로 얻은 정확도를 실제 손글씨 성능처럼 말하지 않는다. 실제 필기 샘플이 필요하면 직접 촬영하고 라벨을 따로 단다
- 라벨 스키마는 `samples/doculens_samples/labels.py`의 `GoldenLabel` (이미지 파일명, 양식, 난이도, seed, 거래명세서 전체 필드와 품목 배열). bbox 라벨은 아직 없다. 9번 이후 위치 정확도가 필요해지면 렌더러에서 텍스트 좌표를 기록하도록 확장한다
- 재생성: `samples/`에서 `uv run --project ..\apps\api python -m doculens_samples --count 40 --handwritten 10` (seed 고정이라 같은 결과). 폰트는 `python samples/fetch_fonts.py`로 받는다 (`samples/fonts/`는 gitignore)
- 렌더링은 Pillow, 가짜 데이터는 Faker(ko_KR), 노이즈는 numpy다 (apps/api dev 의존성). 사업자번호는 검증 숫자를 맞춰 만든 임의 값이라 실제 사업자와 우연히 겹칠 수 있다
- **용량 함정**: 노이즈가 있는 이미지를 PNG로 저장하면 장당 7MB가 된다. low_res/photo는 JPEG(품질 85), clean/skewed는 PNG로 저장한다. 이미지 수를 늘릴 때 용량 상한 테스트(장당 1MB)를 확인한다
- 칸 넘침: 긴 주소는 칸 너비에 맞춰 줄바꿈하고 박스 높이를 늘린다. `find_overflows()`가 칸을 넘긴 글자를 돌려주고, 테스트가 양식 5종 x seed 100개로 검사한다 (이 검사가 없던 때는 좌우 배치 양식에서 주소가 옆 칸을 침범했다)
- 생성기의 품목 수 상한(`MAX_ITEMS=10`)은 가장 빡빡한 양식의 수용량(11행)에서 나왔다. 양식을 추가하면 통합 테스트가 어긋남을 잡아 준다

## 확정된 결정

| 항목 | 결정 |
|---|---|
| 대표 문서 | 거래명세서 (사업자등록증 아님) |
| 백엔드 | FastAPI (Python 3.12 고정, uv) |
| 기본 실행 환경 | CPU. GPU(PaddleOCR-VL)는 선택 옵션 |
| LLM | 옵트인 하이브리드. OCR 텍스트만 전송, 키가 없으면 자동 비활성화 |
| Python 타입 체커 | pyright (strict) |
| Postgres 드라이버 | psycopg 3. 아직 설치 안 함, 7번(DB 스키마)에서 추가 |
| Next.js | 15 유지. `npm audit` 7건은 알려진 이슈로 두고 4번 시점에 16 업그레이드 재검토 |
| PaddleOCR | 태스크 1에서 제외. 9번에서 설치와 호환성 검증 |
| 서브태스크 분해 | `expand --all` 금지. 해당 페이즈 진입 시 점수 7 이상만 `--num=5`로 분해 |

## 새 라이브러리 도입 정책

- 비용이 드는 것이 아니면 승인 없이 진행해도 된다 (사용자 결정, 2026-10-21). 도입한 뒤 무엇을 왜 넣었는지 알려 준다
- 유료 API, 과금 서비스, 라이선스 제약(예: AGPL)이 있는 것은 여전히 먼저 확인받는다

## 환경 메모 (이번 세션에서 겪은 문제)

- **uv**: winget으로 설치했다. 새 터미널에서는 PATH에 잡힌다. 현재 셸에서 안 잡히면 `$env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')`
- **PowerShell 5.1 함정**
  - `Set-Content -Encoding utf8`은 BOM을 붙인다. `.taskmaster/config.json`이 BOM 때문에 파싱 실패한 적이 있다. 파일 쓰기는 `[System.IO.File]::WriteAllText(경로, 내용, (New-Object System.Text.UTF8Encoding($false)))`를 쓴다
  - `git commit -F -`로 here-string을 넘길 수 없다. 메시지를 UTF-8 파일로 저장한 뒤 `git commit -F 파일`을 쓴다
  - 한글 출력이 깨지면 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`
- **보호 훅** (`~/.claude/hooks/protect-files.js`): `.env.example`은 허용된다. 명령 문자열에 `.env`라는 토큰이 단독으로 들어가면 차단되니 점검 목록 같은 곳에도 쓰지 않는다
- **`NUL` 파일**: 어떤 명령의 `2>nul` 때문에 저장소 루트에 `NUL`이라는 파일이 생긴 적이 있다. Windows 예약 이름이라 `cmd /c "del /f /q \\?\<경로>\NUL"`로 지워야 한다. 커밋 전에 `git status`로 확인한다
- **Task Master AI 명령**(`parse-prd`, `analyze-complexity`, `expand`)은 오래 걸린다(수 분~수십 분). `run_in_background`로 실행한다
- **`.mcp.json`**에는 API 키 자리표시자만 있다. 실제 키를 넣으면 커밋되므로 넣지 않는다 (현재 `claude-code` 공급자라 키가 필요 없다)
- `git add` 시 CRLF 변환 경고가 많이 나오지만 동작에는 문제 없다
- **bash 도구에는 uv가 PATH에 없다.** uv/pytest/ruff/pyright는 PowerShell에서 실행한다. 작업 디렉터리는 `apps/api`이고, `uv run pytest`가 `samples/tests`까지 함께 돈다 (`pyproject.toml`의 testpaths, pythonpath). `samples/tests`만 경로로 지정하면 rootdir이 달라져 import가 실패하니 `-k`로 거른다
- 루트에서 `npx tsc --noEmit`을 하면 tsconfig가 없어 도움말만 나온다. `apps/web`에서 실행한다
- 보호 훅이 `Remove-Item -Recurse -Force`를 막는다. 생성물을 지울 때는 `Remove-Item 경로\*.png`처럼 대상 파일을 지정한다
- bash 도구의 긴 heredoc 안에 따옴표가 섞이면 전체가 파싱 오류로 실행되지 않는다. 코드 파일은 Write 도구로 만든다

## 열려 있는 결정

| 시점 | 내용 | 현재 의견 |
|---|---|---|
| 9번 이후 | 실제 필기(손글씨) 샘플 확보 여부. 모사 10장은 이미 있음 | 일반 OCR 엔진은 한글 손글씨에 약해 정확도가 낮게 나올 가능성이 높다. 9번 결과를 보고 판단 |
| 7번 | psycopg 3 추가 (확정됨, 설치만 남음) | - |
| 10번 | PDF 분리: pypdfium2 vs PyMuPDF | pypdfium2 (PyMuPDF는 AGPL) |
| 14번 이후 | 표 인식이 충분한지, LLM 폴백 비중 | 벤치마크 결과로 판단 |
| P4 후반 | 데모 배포 대상 | 미정. 30번 착수 전 제안 |
| 시점 미정 | GitHub 원격 저장소 생성과 공개 범위 | 사용자 확인 필요 |
