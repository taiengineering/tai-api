# TAI Safe 개발 세션 — 2026-04-08

## 완료 작업

### 🔴 긴급 수정

**[FIXED] 전체 서비스 502 에러 (최우선)**
- 원인: `inspection_schedule.py`에서 `from routers.inspection_sets import _calc_next_date` — 함수명 불일치 (`_next_planned_from`으로 변경됨)
- 수정: `from routers.inspection_sets import _next_planned_from as _calc_next_date` (alias)
- 파일: `routers/inspection_schedule.py`

**[FIXED] auth-guard.js 리다이렉트 URL**
- 수정 전: `https://tadmin.taieng.co.kr/html/.../auth-login-cover.html` (하드코딩)
- 수정 후: `/html/.../auth-login-cover.html` (상대경로)
- safe 도메인 → tadmin → Cloudflare 루프 해소

**[FIXED] factory-list.html — 시설관리 데이터 로딩**
- auth-guard.js 미포함 → `<head>` 첫 줄 추가
- API 파라미터 불일치 수정: `keyword→search`, `type→site_type`, `status→status_code`
- 응답구조 3가지 방어 처리 (`data.data.items`, `data.data`, `data`)
- 에러 시 테이블에 메시지 + console.error

---

### 🚀 성능 개선

**[DONE] DB 복합 인덱스 3개 추가 (Supabase)**
```sql
CREATE INDEX idx_equipment_assets_factory_operating_created
  ON equipment_assets(factory_id, is_operating, created_at DESC);

CREATE INDEX idx_inspection_sets_factory_active_source
  ON inspection_sets(factory_id, is_active, source);

CREATE INDEX idx_master_rules_active_type_sector
  ON master_building_legal_rules(is_active, obligation_type, sector);
```

**[DONE] api.js 개선**
- 12초 타임아웃 (AbortController)
- `apiCallAll(...promises)` 병렬 헬퍼 추가
- 파일: `tadmin/full-version/assets/js/tai/api.js`

**[DONE] my-equipment.html 병렬화**
- 초기화: `loadProcessList()` + `loadStats()` Promise.all 병렬 → 완료 후 `loadTable()`
- 시설 변경: `loadProcessList().then(refreshStatsAndTable)` 순서 보장
- `refreshStatsAndTable()`: `Promise.all([loadStats(), loadTable()])` 병렬

**[DONE] factory-list.html 병렬화**
- 패널 열기: `contacts + eqCount` → `Promise.all([getFactoryContacts, getEquipmentCount])`
- 패널 열기 응답시간 ~50% 단축

---

### ✨ 기능 복원

**[DONE] KSIC 업종 검색 드롭다운 복원**
- 원인: factory-list.html 재작성 과정에서 이전에 구현된 KSIC 검색 드롭다운이 단순 텍스트 입력으로 돌아감
- 복원 내용:
  - 텍스트 타이핑 → 300ms debounce → 드롭다운
  - API: `GET /ksic-engine/ksic-search?query={q}`
  - 드롭다운: 코드 + 업종명 + 경로(lv1>lv2>lv3)
  - X 버튼: 선택 초기화
  - 패널 열릴 때 기존 값 자동 표시 (뱃지)
  - readOnly 모드: 뱃지로 표시
  - 저장 시 `ksic_code`, `ksic_name` 포함

---

### 🏗 아키텍처 논의 및 결정

**속도 문제 원인 분석**
1. Railway Cold Start (Always On 이미 활성화)
2. Railway-Supabase 지역 레이턴시 (미국-도쿄)
3. 순차 API 호출 (Promise.all로 개선)
4. 인덱스 (복합 인덱스 추가)

**중장기 아키텍처 방향 결정**
- 단순 CRUD → Supabase PostgREST 직접 호출 (Railway 우회)
- 법령 엔진 (legal_engine.py 71KB Python 로직) → Railway 영구 유지
- Railway는 "법령엔진 전용 서버"로 역할 축소
- 목표 비용: Supabase Pro $25 + Railway Hobby $5 = 월 $30

---

## 변경 파일 목록

| 레포 | 파일 | 내용 |
|---|---|---|
| tai-api | `routers/inspection_schedule.py` | _calc_next_date ImportError 수정 |
| tai-admin | `assets/js/tai/auth-guard.js` | 리다이렉트 상대경로로 수정 |
| tai-admin | `assets/js/tai/api.js` | 12초 타임아웃 + apiCallAll 헬퍼 |
| tai-admin | `html/.../factory-list.html` | auth-guard 추가, API 파라미터 수정, KSIC 드롭다운 복원, 병렬화 |
| tai-admin | `html/.../my-equipment.html` | 초기화 병렬화 |

## 현재 Railway 배포 상태
- Always On: 활성화 완료
- inspection_schedule.py ImportError: 수정 완료 → 재배포됨

## PENDING
- 단순 CRUD PostgREST 이전 (api.js apiCall → Supabase 직접 호출)
- 안전관리자 대시보드 (safe.taieng.co.kr) 구현
- 공정관리 construction 섹터 지원
