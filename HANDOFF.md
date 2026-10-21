# 세션 인계 메모

`/clear` 후 이어서 작업할 때 가장 먼저 읽는다. 전체 계획은 `ROADMAP.md`, 태스크 상세는 `task-master show <id>`.
이 파일은 진행 상황이 바뀔 때마다 갱신한다.

## 현재 상태 (태스크 1 완료 직후)

- 완료: 태스크 1 (모노레포 및 개발 환경 초기 설정)
- 다음: **태스크 6 (합성 거래명세서 골든셋 생성기)**. 크리티컬 패스의 첫 작업이라 2번(Docker)보다 먼저 한다 (사용자 결정)
- 커밋: `8c4557e` (계획/에이전트/ROADMAP), `f7c7491` (모노레포 골격). 저장소는 독립 git이고 원격은 아직 없다
- 검증 상태: `pytest` 7건, `ruff`, `pyright`(strict), `npm run test` 2건, `tsc`, `lint` 모두 통과

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

## 태스크 6을 시작할 때

1. `task-master set-status --id=6 --status=in-progress`
2. 점수 7이므로 `task-master expand --id=6 --num=5`로 분해 (담당 에이전트: `ocr-engineer`)
3. TDD: 실패하는 테스트를 먼저 작성한다 (예: 생성기가 N장의 이미지와 같은 수의 정답 JSON을 만든다, 라벨 스키마 검증)
4. **새 라이브러리는 도입 전에 제안하고 확인받는다.** 후보와 확인할 점:
   - 이미지 렌더링: Pillow, 또는 HTML → 이미지(Playwright는 4번/27번에서 이미 도입 예정)
   - 가짜 데이터: Faker(ko_KR)
   - PDF 출력이 필요하면 reportlab
   - **한글 폰트가 필요하다.** 라이선스(OFL 등)를 확인하고 저장소에 포함할지, 다운로드 스크립트로 둘지 정해야 한다
5. 요구사항: 양식 5종 이상, 30장 이상, 난이도 변형(깨끗함/기울어짐/저해상도/촬영 느낌), 정답 라벨 JSON 자동 생성, 실제 개인정보 사용 금지
6. 산출물 위치: `samples/` (생성기 코드)와 `samples/golden/` (이미지와 라벨). 대용량이면 커밋 여부를 먼저 정한다

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

## 열려 있는 결정

| 시점 | 내용 | 현재 의견 |
|---|---|---|
| 6번 시작 | 이미지 렌더링 방식, 한글 폰트 확보 방법, 라이브러리 목록 | 제안 후 확인 |
| 7번 | psycopg 3 추가 (확정됨, 설치만 남음) | - |
| 10번 | PDF 분리: pypdfium2 vs PyMuPDF | pypdfium2 (PyMuPDF는 AGPL) |
| 14번 이후 | 표 인식이 충분한지, LLM 폴백 비중 | 벤치마크 결과로 판단 |
| P4 후반 | 데모 배포 대상 | 미정. 30번 착수 전 제안 |
| 시점 미정 | GitHub 원격 저장소 생성과 공개 범위 | 사용자 확인 필요 |
