# TAI Backend 세션 메모리 — 2026-04-01

## 완료된 작업

### 1. construction.py v1.1.0
- **신규:** `GET /construction/kcsc/works` — 전체 위험작업 목록 (is_hazardous 필터)
  - step3 탭① KCSC 위험작업 직접 선택에서 호출
  - 파라미터: is_hazardous, work_type_code, hazard_type, search, page, size
- **버그 수정:** `GET /construction/kcsc/processes`
  - 정렬 컬럼: `process_code` → `kcs_code` (실제 컨럼명 수정)
  - work_type_code 필터 새로 추가
- **개선:** `GET /construction/kcsc/works/{process_id}`
  - is_active=True 필터 추가
- **모델 확장:** ProcessCreate/Patch에 kcsc_process_id, work_type_code 필드 추가

### 2. public.py (v5.2.0 유지)
- `POST /public/diagnosis-request` — 비회원 신청 접수 (v1/v2/v3 공통)
- `GET /public/diagnosis-request/{request_no}` — 접수번호로 상태 조회
- 테이블: public_diagnosis_requests
- 접수번호 형식: TAI-D1-YYYYMMDD-XXXX

### 3. public_admin.py (v5.2.0 유지)
- `GET /admin/public-diagnosis-requests` — 목록
- `GET /admin/public-diagnosis-requests/stats` — 통계
- `POST /admin/public-diagnosis-requests/{id}/run-diagnosis` — 법령진단 실행
- `PATCH /admin/public-diagnosis-requests/{id}/result-html` — 결과 HTML 수정
- `POST /admin/public-diagnosis-requests/{id}/mark-sent` — 발송완료
- **누락 가능성:** `PATCH /admin/public-diagnosis-requests/{id}/status` — 상태변경 API

## 미완료 / 진행 중

### 알럿관리 API (작업지시만 작성, 미구현)

**대상 파일:** `routers/alert_messages.py` 신규 생성

**system_alert_messages 테이블 현황:**
- 총 30개 알럿
- 필드: id, alert_code, platform(ALL/TADMIN/ADMIN), category(ERROR/SUCCESS/INFO/CONFIRM/WARNING),
  context(AUTH/COMMON/DIAGNOSIS/WORKER/CONSTRUCTION/INSPECTION/EDUCATION/CONTRACT),
  message_ko, message_en, variables(jsonb), example, is_active, sort_order

**구현할 엔드포인트:**
```
GET  /alert-messages          — 목록 (필터: category/context/platform/search/is_active)
GET  /alert-messages/codes    — 코드 전체 조회 (인증 불필요, 프론트 JS용)
GET  /alert-messages/contexts — context 목록
POST /alert-messages          — 신규 등록
PATCH /alert-messages/{id}   — 수정 (message_ko 필드 포함)
PATCH /alert-messages/{id}/toggle — 활성화 토글
DELETE /alert-messages/{id}  — 비활성화
```

**main.py 등록 필요:**
```python
from routers.alert_messages import router as alert_messages_router
app.include_router(alert_messages_router)
```

**버전:** 5.2.0 → 5.2.1

## main.py 현재 상태
- 버전: 5.2.0
- CORS allow_origins에 taieng.co.kr 포함 (비회원 request/v1~v3에서 API 호출 가능)
- public_router, public_admin_router 등록 완료

## Railway 정보
- URL: api.taieng.co.kr
- 자동 배포: main 브랜치 push 시 2~4분
- 버전 확인: GET https://api.taieng.co.kr/ → version 필드
