# 세션 인계 메모

`/clear` 후 이어서 작업할 때 가장 먼저 읽는다. 전체 계획은 `ROADMAP.md`, 태스크 상세는 `task-master show <id>`.
이 파일은 진행 상황이 바뀔 때마다 갱신한다.

## 현재 상태 (태스크 6 완료 직후)

- 완료: 태스크 1 (모노레포 및 개발 환경), 태스크 6 (합성 거래명세서 골든셋 생성기, 서브태스크 6.1~6.5)
- 다음: **태스크 9 (PaddleOCR 어댑터, 크리티컬 패스 다음 칸)**. 병렬로 2번(Docker), 3번, 4번, 8번, 10번도 가능하다. 9번은 시작 시 점수를 확인해 7 이상이면 `--num=5`로 분해한다
- 저장소는 독립 git이고 원격은 아직 없다
- 검증 상태: `pytest` 402건, `ruff`, `pyright`(strict), `npm run test` 2건, `tsc`(apps/web에서 실행), `lint` 모두 통과

## 골든셋 (태스크 6 산출물)

- 생성기: `samples/doculens_samples/`, 테스트: `samples/tests/`, 설명: `samples/README.md`
- 결과물 `samples/golden/`: 40장 + 라벨 JSON 40개(10.8MB)를 **커밋했다** (사용자 결정). 양식 5종 x 난이도 4종(clean/skewed/low_res/photo)이 각 2장씩이다
- 라벨 스키마는 `samples/doculens_samples/labels.py`의 `GoldenLabel` (이미지 파일명, 양식, 난이도, seed, 거래명세서 전체 필드와 품목 배열). bbox 라벨은 아직 없다. 9번 이후 위치 정확도가 필요해지면 렌더러에서 텍스트 좌표를 기록하도록 확장한다
- 재생성: `samples/`에서 `uv run --project ..\apps\api python -m doculens_samples --count 40` (seed 고정이라 같은 결과). 폰트는 `python samples/fetch_fonts.py`로 받는다 (`samples/fonts/`는 gitignore)
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
| 9번 이후 | 손글씨 골든셋: 현재는 전부 인쇄체. 손글씨 폰트(나눔펜, 개구, 푸어스토리 등 OFL)로 기입란을 채운 양식을 추가할지 | 제안 후 확인. 폰트 모사라 실제 필기와 다름을 README에 밝힌다 |
| 7번 | psycopg 3 추가 (확정됨, 설치만 남음) | - |
| 10번 | PDF 분리: pypdfium2 vs PyMuPDF | pypdfium2 (PyMuPDF는 AGPL) |
| 14번 이후 | 표 인식이 충분한지, LLM 폴백 비중 | 벤치마크 결과로 판단 |
| P4 후반 | 데모 배포 대상 | 미정. 30번 착수 전 제안 |
| 시점 미정 | GitHub 원격 저장소 생성과 공개 범위 | 사용자 확인 필요 |
