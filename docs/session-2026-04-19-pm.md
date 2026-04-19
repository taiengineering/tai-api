# 세션 6 PM 작업일지 — 2026-04-19

## 완료 작업

### 1. Gotenberg PDF 엔진 교체 (tai-api)
- **xhtml2pdf → Gotenberg (Chromium)** 전환 완료
- `tai-gotenberg` Fly 앱 배포 (nrt, 1GB, auto_stop)
- `diagnosis_proposal.py` v2.1.0: async httpx + Gotenberg API
- xhtml2pdf용 @font-face 주입 / .replace() 로직 제거
- 템플릿 font-family: Noto Sans CJK KR 직접 사용
- **해결한 이슈:**
  - `.internal` DNS 해석 실패 → public URL (`tai-gotenberg.fly.dev`)
  - Chromium OOM (512MB) → 1GB 증량
  - Cold start Chromium 기동 실패 → `CHROMIUM_AUTO_START=true`, `START_TIMEOUT=60s`
- **커밋:** 366bc8d, c9bca5f, 074ccc1, cdbf800, 54674e8

### 2. 기안 PDF URL 통일 (tai-api)
- `safe.taieng.co.kr` → `taieng.co.kr` 변경 (3곳)
- 모든 URL에 `https://` 추가 (6곳)
- **커밋:** cdbf800

### 3. Supabase Storage 다이어그램 한글 파일명 문제 조사
- `diagrams` 버킷에 25개 SVG 존재 (한글 파일명)
- Supabase Storage API가 한글 키를 `InvalidKey`로 거부 — download/access 불가
- REST API, Python SDK, JS SDK, signed URL, S3 프로토콜 모두 실패
- **diagram_proxy** 라우터 (v1.0.1)로 우회: tai-api 서버에서 프록시 (별도 커밋)
- **미해결:** 영문 파일명으로의 교체는 Dashboard 수동 작업 또는 DB 직접 접근 필요

### 4. fix-request.html 리디자인 (taieng)
- 좌우 분할 레이아웃 (40% 마케팅 / 60% 채팅)
- 왼쪽: 매칭 분야 4개, 이용 안내, 특허 정보
- 오른쪽: 다크 테마 채팅 UI, 세로 풀 높이
- 모바일 768px↓: 상단 축약 배너 + 풀스크린 채팅
- 기존 JS 로직 100% 유지 (DOM ID 변경 없음)
- `?from=diagnosis` 파라미터 컨텍스트별 인사 추가
- nav 아래 배치 + 푸터 추가
- **커밋:** e966f79, df11c95

---

## 미해결 이슈

### ISSUE-PM-01: Supabase Storage 한글 파일명 접근 불가
- **심각도:** 중 (diagram_proxy로 우회 중이나, 불필요한 API 호출 발생)
- **현상:** `diagrams` 버킷의 25개 SVG가 한글 파일명으로 저장되어 있어 API 접근 불가
- **원인:** Supabase Storage 서버가 non-ASCII key를 `InvalidKey`로 거부
- **우회:** `GET /api/v1/diagrams/{id}` 프록시 엔드포인트 (tai-api diagram_proxy.py)
- **근본 해결:** Supabase Dashboard에서 25개 파일을 영문명으로 재업로드 후 프록시 제거
- **영문 파일명 매핑:** `diagram_templates.filename` 컬럼에 이미 정의됨

### ISSUE-PM-02: Gotenberg .internal DNS 미작동
- **심각도:** 낮 (public URL로 우회 중, 기능 정상)
- **현상:** `tai-gotenberg.internal:3000` DNS 해석 실패 (Errno -5)
- **현재:** `GOTENBERG_URL=https://tai-gotenberg.fly.dev` (public URL 사용)
- **영향:** 내부 통신 대신 외부 경유 → 약간의 레이턴시 증가
- **해결:** Fly.io 지원팀에 `.internal` DNS 설정 문의 또는 같은 network에 join

### ISSUE-PM-03: 유료 PDF (diagnosis_report.py) Gotenberg 미적용
- **심각도:** 중 (현재 xhtml2pdf로 동작 중, CSS 렌더링 품질 낮음)
- **현상:** 기안 PDF만 Gotenberg 적용, 유료 PDF는 아직 xhtml2pdf
- **해결:** 동일 패턴(async httpx → Gotenberg) 적용 — 기안 PDF 코드 참조

### ISSUE-PM-04: Gotenberg cold start 지연
- **심각도:** 낮 (auto_stop 머신 재시작 시 첫 요청 ~7초)
- **현상:** idle 후 머신 정지 → 요청 시 재시작 → Chromium 기동 7초
- **현재:** `CHROMIUM_AUTO_START=true`로 머신 시작 시 즉시 Chromium 기동
- **대안:** `min_machines_running=1` (항상 1대 유지, 비용 증가 ~$5/월 추가)
