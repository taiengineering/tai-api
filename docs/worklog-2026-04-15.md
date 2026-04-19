# 작업내역 — 2026-04-15

**세션 범위:** 건설 모듈 파이프라인 완성 + 마케팅 사이트 메뉴 정리  
**레포 대상:** tai-api · tai-admin · taieng

---

## Backend (tai-api)

### BE-1 ✅ inspection_sets 자동생성 로직
- **신규 파일:** `routers/inspection_set_auto.py`
- **수정 파일:** `legal_engine.py` → v5.6.8
- `diagnose/step1` 완료 시 `auto_create_inspection_sets_from_diagnosis()` 자동 호출
- 대상: `inspection_required=True` OR `obligation_type IN (INSPECT, BEFORE_WORK)`
- 중복 방지: `legal_rule_id` 기준, 배치 20건씩 처리
- `obligation_type` 정확 반영

### BE-2 ✅ inspection_sets obligation_type 정규화 (SQL)
- 기존 305건 전부 `INSPECT`로 들어가 있던 데이터를 `master_building_legal_rules` 원본과 매칭
- 결과: INSPECT 238 + BEFORE_WORK 65 + 기타 8건으로 분리 (총 67건 업데이트)

### BE-3 ✅ contract_amount_eok 필드 명확화
- `SiteCreate` 모델 description에 "억원 단위, 원화 입력 시 오판정" 명시

### BE-4 ⏭ SKIP
- `master_building_legal_rules`에 cycle 컬럼 추가 불필요
- 기존 `inspection_cycle_unit_code` → `CYCLE_CODE_MAP`으로 cycle 파생 가능 확인

---

## Frontend (tai-admin)

> **주요 발견:** tai-admin 레포는 **dev 브랜치 없음 — main 단일 브랜치** 운영  
> 이후 모든 tai-admin push는 `branch: "main"` 고정

### FE-1 ✅ construction-inspection-anchor.html — 법령진단 가이드 카드
- **파일:** `tadmin/full-version/html/horizontal-menu-template/construction-inspection-anchor.html`
- `#emptyGuide` 카드 추가 (🏗️ 아이콘 + "법령진단 실행하기" 버튼)
- `#tableCard` id 부여
- `renderTable()`: 0건 시 emptyGuide 표시 / tableCard 숨김 토글
- `runDiagnosis()` 함수 추가: `POST /construction/sites/{siteId}/diagnose` 호출 후 `loadRows()` 재조회
- **commit:** `5441d7c`

### FE-2 ✅ construction-process-list.html — KCSC 검색 UI
- **기존 구현 완료 확인** (`onProcessNameInput` + `kcscDropdown` 이미 존재)
- 추가 작업 불필요, 스킵

### FE-3 ✅ construction-site-list.html — 현장등록 신규 필드
- **파일:** `tadmin/full-version/html/horizontal-menu-template/construction-site-list.html`
- 모달에 추가한 필드:
  - 건설업 업종 대분류 (`f-biz-category`: GENERAL/SPECIALTY)
  - 세부 업종 (`f-biz-code`: system_codes 동적 로드)
  - 발주처 유형 (`f-client-type`: system_codes 동적 로드)
  - 발주처명 (`f-client-name`)
  - 지상 층수 (`f-floors-above`)
  - 지하 층수 (`f-floors-below`)
  - 연면적 ㎡ (`f-total-area`)
- 신규 JS 함수: `loadBizCodes()`, `loadClientTypes()`
- `resetModal()`, `openEditModal()`, `saveSite()` body에 신규 필드 반영
- **commit:** `5441d7c` (FE-1과 동일 커밋)

---

## Marketing Site (taieng / new.taieng.co.kr)

> **파일:** `nexas/assets/js/header.js`

### 헤더 메뉴 v2.1.1
- 회사소개 드롭다운 하위: `특허출원` → `TAI 기술력` 명칭 변경
- 링크 대상 `patents.html` 유지
- **commit:** `a3b8127`

### 헤더 메뉴 v2.1.2
- 탑메뉴 `회사소개` 드롭다운 (회사소개/TAI기술력/FAQ/안전정보) 전체 제거
- 대신 `안전정보` 단일 링크(`safety-news.html`)로 교체
- **탑메뉴 최종 구성:** 서비스 · 대상별 · 요금제 · 안전정보 + 로그인/무료진단
- **commit:** `f2da1a7`

---

## 인프라 메모

- tai-admin: main 단일 브랜치 (dev 없음) — Cloudflare Pages main → 자동 배포
- tai-api: main 브랜치 → Fly.io Tokyo 자동 배포
- taieng: main 브랜치 → Cloudflare Pages 자동 배포

---

## 다음 세션 우선 작업

1. E2E 검증: 건설 현장 등록 → 법령진단 → inspection_sets 자동생성 → 점검앵커 목록 확인
2. 점검앵커 4조건 설정 (기준일+담당자+체크항목) → 스케줄 생성 확인
3. 회사소개/TAI기술력/FAQ 페이지 — 푸터 또는 별도 경로 접근 방식 검토
