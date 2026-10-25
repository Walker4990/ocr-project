# 세션 인계 메모

`/clear` 후 이어서 작업할 때 가장 먼저 읽는다. 전체 계획은 `ROADMAP.md`, 태스크 상세는 `task-master show <id>`.
이 파일은 진행 상황이 바뀔 때마다 갱신한다.

## 현재 상태 (태스크 11 완료 직후)

- 완료: 태스크 1 (모노레포 및 개발 환경), 2 (Docker Compose), 3 (FastAPI 골격), 4 (Next.js 구조), 6 (골든셋 생성기), 8 (OcrEngine Protocol), 9 (PaddleOCR 어댑터), 10 (전처리), 11 (표 구조 인식)
- 다음: `task-master next`로 확인한다. 의존성은 `task-master show <id>`로 먼저 본다
- 저장소는 독립 git이고 원격은 아직 없다
- 검증 상태: `pytest -m "not slow"` 1175건, `ruff`, `pyright`(strict) 통과. 웹 `npm run test` 16건, `tsc`, `lint` 통과(3·4·10번 병합 후 확인). 3·4·10번은 서브에이전트 3개가 worktree에서 병렬로 구현해 병합했고 worktree는 정리했다
- 병합 후 docker compose에서 api 헬스체크가 새 `/health`로 통과하는지는 아직 돌려 보지 않았다 (로직상 DB는 psycopg가 없어 skipped, Redis는 ok라 200이어야 한다)
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

## FastAPI 골격 (태스크 3 산출물)

- 오류 응답 형식: `{"error": {"code", "message", "requestId", "details"?}}`. 새 라우트와 서비스는 `app/exceptions.py`의 예외(`ValidationError` 422, `NotFoundError` 404, `ConflictError` 409, `RateLimitedError` 429)를 던진다. 500에는 내부 메시지를 담지 않고, 검증 실패 `details`에는 입력 값을 넣지 않는다
- `app/main.py`의 `create_app(settings, health_checkers)` 팩토리로 테스트에서 설정과 체커를 주입한다. 컨트롤러는 `app/controllers/`, 서비스는 `app/services/`에 둔다. 설정은 `app/config.py`(`Settings`, pydantic-settings)
- 미들웨어(바깥부터): CORS → `RequestIdMiddleware`(`X-Request-ID`, 클라이언트가 보낸 값은 UUID 형식일 때만 받음, structlog contextvars 바인딩, 요청당 `request_completed` 로그) → `RateLimitMiddleware`(IP당 60초 고정 윈도우, 프로세스 메모리, `/health` 제외, 한도 0 이하면 꺼짐)
- `GET /health`: `{"status": "ok"|"degraded", "checks": {"database", "redis"}}`, 값은 `ok`/`down`/`skipped`, 하나라도 `down`이면 503. psycopg가 없으면 DB는 `skipped`(compose가 `DATABASE_URL`을 주입해도 헬스체크가 깨지지 않게). **7번에서 psycopg를 설치하면 실제 `SELECT 1`을 수행**하므로 DB가 안 뜨면 503이 된다. 비동기 엔진을 쓰면 체커를 엔진 재사용 방식으로 바꿀지 검토한다
- 의존성: `structlog`(런타임) 추가
- 테스트 함정: `create_app`이 `configure_logging`을 호출하므로 `structlog.testing.capture_logs()` 블록 안에서 앱을 만들면 캡처가 풀린다(앱을 먼저 만든다). 500 경로 테스트는 `TestClient(raise_server_exceptions=False)`
- 한계: 레이트 리밋은 인스턴스마다 따로 센다. 리버스 프록시 뒤에서는 `X-Forwarded-For` 처리가 필요하다. 업로드 후 잡 enqueue 때 `structlog.contextvars`의 requestId를 잡 인자에 실어 워커에서 다시 bind해야 한다(아직 안 함)

## Next.js 구조 (태스크 4 산출물)

- `apps/web`: `lib/api-client.ts`(`apiFetch`, `ApiError{status, code, message, requestId}`, `createRequestId`, 모든 요청에 `X-Request-ID`, 기준 주소는 `NEXT_PUBLIC_API_URL`이고 없으면 `http://localhost:8000`), `stores/ui-store.ts`(Zustand), `components/error-notice.tsx`, `components/ui/{button,card,badge}.tsx`, `components.json`(shadcn, style radix-nova, Tailwind v4)
- 오류 파싱은 백엔드 규격 `{"error": {...}}`에 맞춘다(병합 때 에이전트의 가정을 고쳤다). 본문에 requestId가 없으면 `X-Request-ID` 헤더, 그것도 없으면 보낸 값. 네트워크 오류는 status 0, code `network_error`
- 컴포넌트 테스트는 파일 상단에 `// @vitest-environment jsdom` 주석 + testing-library. Vitest는 `vitest.config.ts`(`@` 별칭)
- 의존성(모두 무료): zustand, radix-ui, class-variance-authority, clsx, tailwind-merge, lucide-react, tw-animate-css, shadcn(런타임) / testing-library, jsdom, @vitejs/plugin-react(dev)
- **shadcn 주의**: `npx shadcn add` 후 출처 불분명한 `cn` npm 패키지 import가 생기면 `@/lib/utils`로 고친다. 최신 스타일은 `radix-ui` 통합 패키지를 쓴다(`Slot.Root` 등). 생성된 `globals.css`의 `--font-sans` 순환 참조는 고쳐 두었다
- 검증 못 한 것: `npm run dev` 화면 확인, web Docker 이미지 재빌드. OpenAPI 타입 생성(openapi-typescript 등)은 미도입(연동 시 제안)

## 전처리 (태스크 10 산출물)

- `apps/api/app/ocr/preprocessing.py`, 테스트 `tests/ocr/test_preprocessing.py`와 slow `test_preprocessing_ocr.py`. 모두 RGB `NDArray[np.uint8]` 입출력이고 입력을 바꾸지 않는다
- 함수: `decode_image(bytes)`(Pillow, EXIF 회전 반영), `split_pdf(bytes, dpi=200)`(pypdfium2), `estimate_skew_angle`/`deskew`(Hough, 반시계가 양수, 0.3도 미만이면 그대로, 15도 초과 선분 무시, 빈 곳 흰색), `enhance_contrast`(LAB + CLAHE), `adaptive_threshold`(가우시안, 0/255 RGB), `resize_max_side`(줄이기만 함). **기본으로 켤 단계는 모듈이 정하지 않는다**(호출하는 쪽 설정)
- 의존성: `pypdfium2` 추가(PDF 분리 결정 확정), `pillow`를 dev에서 런타임으로 이동
- **간이 측정** (7장: clean 000, skewed 005·006, low_res 010·011, photo 015·016 / 필드 149개 / 위 50장 측정과 같은 간이 지표 / 1회 측정이라 시간 오차 큼): 원본 138(92.6%), deskew 137(91.9%), deskew+CLAHE 136(91.3%), +적응형 임계화 122(81.9%), deskew+긴 변 1600 리사이즈 138(92.6%). 임계화만 low_res에서 5~7건 떨어졌다. **전처리의 정확도 이득은 이 샘플에서 확인되지 않았고 임계화는 해로웠다.** 기본 on/off는 벤치마크 태스크에서 CER·필드 정확도로 판단한다. 골든셋 기울기(1.5~4도)는 PaddleOCR가 이미 잘 읽어서 이득이 안 보인다. 5~15도는 합성 회전 테스트(오차 0.7도 이내)로만 확인했다. 손글씨 모사와 실제 촬영본은 측정하지 않았다
- 한계: 회전만 보정하고 photo의 원근 왜곡은 보정하지 않는다. 글줄이 충분히 길어야 하며 선분을 못 찾으면 0도. `split_pdf`에 페이지 수·크기 상한이 없으니 업로드 API(11번 부근)에서 제한한다. pypdfium2는 타입 스텁이 없어 Protocol 캐스팅과 `# pyright: ignore` 한 줄을 썼다

## 표 구조 인식 (태스크 11 산출물)

- `apps/api/app/ocr/table_recognizer.py`, 테스트 `tests/ocr/test_table_recognizer.py`(일반 19건 + slow 1건). `OcrEngine`/`OcrPage`는 그대로 두고 **별도 호출**이다: `build_table_recognizer(use_gpu=None, max_tables=None)`로 만들고 `TableRecognizer.recognize(rgb) -> tuple[OcrTable, ...]`. 모델이 추가로 8~30초 걸리고 Protocol을 건드리면 모든 엔진이 영향을 받아 `OcrPage`에 넣지 않았다. 호출자가 `OcrPage`(약 5초)와 조합한다. 레지스트리에는 등록하지 않았다. import만으로는 paddle을 로드하지 않으며, 워커에 한 번 만들어 상주시킨다
- 타입: `OcrTable`(bbox, n_rows, n_cols, `cells`, `grid()`, `rows()`), `TableCell`(row, col, row_span, col_span, text, bbox). 좌표 규약은 기존과 같다. HTML 셀 수와 상자 수가 다르면 `TableStructureError`를 내고 인식기는 그 표만 건너뛴다(WARNING 로그)
- 흐름: `PP-DocLayout-L`로 표 영역 검출 → `select_table_boxes`로 중복(IoU 0.7 초과)과 다른 표를 둘 이상 품은 상자를 걸러냄 → 영역별로 잘라 `TableRecognitionPipelineV2`(`use_layout_detection=False`)에 입력 → `pred_html`의 `<td>` 순서와 `cell_box_list`를 짝지어 셀 구성. 한국어 인식 모델과 모바일 검출 모델을 명시한다(GPU면 서버 검출)
- 의존성: `paddlex[ocr]==3.4.3` 추가(표 파이프라인이 요구, 24개 패키지, `.venv` 약 +158MB, AGPL 없음). paddlepaddle 3.2.2 고정은 유지, 표 모델도 이 버전의 CPU oneDNN에서 돈다. 모델은 첫 실행에 PP-DocLayout-L, 표 분류, 유선·무선 셀 검출(RT-DETR-L), SLANeXt를 `~/.paddlex`로 받는다(첫 로딩 약 2분, 이후 약 15초)
- **함정 3**: 레이아웃을 켠 채 이미지 전체를 파이프라인에 맡기면 중복 검출과 페이지 전체 표 때문에 장당 약 40초가 들고, 페이지 전체를 한 표로 넣으면 HTML과 셀 상자의 짝이 어긋난다. 레이아웃을 끄고 이미지 전체를 한 표로 넣으면 약 10초지만 구조가 틀리고 금액 열을 잃는다
- **속도** (CPU, oneDNN, 1회 측정): 기본 8~31초/장(표 1개당 6.5~8.3초, 병목은 SLANeXt_wired), `max_tables=1`이면 7.5~12초. 기본 CPU에서 실용적이라고 하기 어렵다
- **간이 측정** (골든셋 8장 시도, 6장 평가 / 1회 / 정확 일치 / 에이전트 측정): "행 수 일치"는 헤더 이후 합계류 제외 데이터 행 수가 라벨 items 수와 같은지, "셀 일치"는 라벨 k번째 품목이 인식 표 k번째 데이터 행의 셀(공백·쉼표 제외)과 같은지. 표가 검출된 6장 중 행 수 일치 3장(000, 002, 040). 6장 40개 품목 기준 품목명 21, 수량 24, 단가 24, 금액 23개 일치
  - classic(000, 040 손글씨 모사)·serif_simple(002)은 거의 맞는다. blue_stacked 001은 두 행이 한 셀로 합쳐져 행이 어긋났고(값은 맞음), 촬영본 016은 구조가 붕괴했다
  - red_totals_top 003은 레이아웃이 페이지 전체를 감싼 표 하나만 내서 첫 품목 행이 사라지고 전부 밀렸다(위치 기반 지표라 0점)
  - **mono_receipt(004, 044)는 선 없는 영수증 스타일이라 표 미검출**. 5개 양식 중 2개는 현재 쓸 수 없다
  - 표본이 양식당 1~2장이라 통계적 의미가 없다. 손글씨 모사 결과를 실제 필기 성능으로 말하지 않는다. 측정 스크립트는 저장소에 없다(벤치마크 태스크에서 만든다)
- 구현하지 않은 대안: 기존 OcrPage 토큰 bbox를 행/열로 군집화하는 방식. 선 없는 표와 페이지 전체 표에 필요할 가능성이 크고 추가 비용이 거의 없다. 벤치마크에서 "표 모델 vs 토큰 군집화 vs 폴백"을 비교한다

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
- **새 worktree에는 `samples/fonts/`(gitignore)가 없어** samples 테스트 약 890건이 FileNotFoundError로 실패한다. 메인 체크아웃의 폴더를 복사하거나 `python samples/fetch_fonts.py`로 받는다
- **`uv sync`와 opencv**: 로컬 환경에 opencv 3종이 같이 깔려 있으면 `uv sync`가 잠금 파일에 없는 둘을 지우면서 공용 `cv2` 폴더가 망가진다(`module 'cv2' has no attribute 'putText'`). `uv sync --reinstall-package opencv-contrib-python`으로 복구한다. 잠금 파일에는 contrib 하나뿐이라 Docker 이미지는 영향이 없다
- 새 의존성이 들어온 브랜치를 병합한 뒤에는 루트에서 `npm ci`, `apps/api`에서 `uv sync`를 먼저 한다
- `task-master show`는 저장소 루트에서 실행한다(`apps/api` 안에서는 Task not found)
- **bash 도구에는 uv가 PATH에 없다.** uv/pytest/ruff/pyright는 PowerShell에서 실행한다. 작업 디렉터리는 `apps/api`이고, `uv run pytest`가 `samples/tests`까지 함께 돈다 (`pyproject.toml`의 testpaths, pythonpath). `samples/tests`만 경로로 지정하면 rootdir이 달라져 import가 실패하니 `-k`로 거른다
- 루트에서 `npx tsc --noEmit`을 하면 tsconfig가 없어 도움말만 나온다. `apps/web`에서 실행한다
- 보호 훅이 `Remove-Item -Recurse -Force`를 막는다. 생성물을 지울 때는 `Remove-Item 경로\*.png`처럼 대상 파일을 지정한다
- bash 도구의 긴 heredoc 안에 따옴표가 섞이면 전체가 파싱 오류로 실행되지 않는다. 코드 파일은 Write 도구로 만든다

## 열려 있는 결정

| 시점 | 내용 | 현재 의견 |
|---|---|---|
| 9번 이후 | 실제 필기(손글씨) 샘플 확보 여부. 모사 10장은 이미 있음 | 일반 OCR 엔진은 한글 손글씨에 약해 정확도가 낮게 나올 가능성이 높다. 9번 결과를 보고 판단 |
| 7번 | psycopg 3 추가 (확정됨, 설치만 남음) | - |
| 10번 | PDF 분리: pypdfium2 vs PyMuPDF | pypdfium2 확정, 설치 완료 (PyMuPDF는 AGPL) |
| 14번 이후 | 표 인식이 충분한지, LLM 폴백 비중 | 벤치마크 결과로 판단 |
| 11번 이후 | 선 없는 표(mono_receipt)·페이지 전체 표(red_totals_top) 대응으로 토큰 bbox 군집화를 병행할지, 기본 `max_tables`를 1로 둘지 | 11번 간이 측정상 표 모델 단독은 2개 양식에서 쓸 수 없고 나머지도 일부 어긋나며(표본 적음) 느리다. 군집화 병행을 권한다. 벤치마크 태스크에서 판단 |
| P4 후반 | 데모 배포 대상 | 미정. 30번 착수 전 제안 |
| 시점 미정 | GitHub 원격 저장소 생성과 공개 범위 | 사용자 확인 필요 |
