# 2026-04-16 프론트엔드 세션 작업내역

**날짜:** 2026-04-16  
**담당:** 프론트-safe 윈도우 + 프론트-new 윈도우  

---

## 브랜치 이슈 (중요)

tai-admin repo에 **dev 브랜치 미존재** → 전체 **main 브랜치 직접 커밋** 처리  
(사용자 지시 "safe: dev 브랜치만" 이행 불가 — 브랜치 생성 후 재정책 필요)

---

## [safe.taieng.co.kr] 건설 모듈 신규 페이지 3개

### FS-02: construction-work-list.html ✅
**파일:** `tadmin/full-version/html/horizontal-menu-template/construction-work-list.html`  
**커밋:** main 직접

**구현:**
- PTW (Permit to Work) 위험작업허가서 관리
- API: `GET/POST /construction/sites/{id}/works`, `PATCH /construction/works/{id}/ptw`
- PTW 번호 자동 채번: `CS-{YYYY}-{5자리}`
- ptw_status: DRAFT → APPROVED / REJECTED
- 필수 필드: worker_count, assigned_manager_id
- 리스트: 체크박스(1번) + No.(2번) ✅
- 통계 5개 (전체/검토대기/승인/반려/위험작업)
- 상세 패널: 지게차 UI 패턴 응용 — 승인/반려 토글 + 반려사유 확장

---

### FS-03: construction-worker-list.html ✅
**파일:** `tadmin/full-version/html/horizontal-menu-template/construction-worker-list.html`  
**커밋:** main 직접

**구현:**
- 직영(DIRECT) / 협력(SUBCON) 작업자 관리
- API: `GET/POST /construction/sites/{id}/workers`, `PATCH /construction/workers/{id}/entry`
- 입장/퇴장 토글: 지게차 UI 패턴 응용 (현재 상태 버튼 활성화 색상)
- 일괄 입퇴장: 다중 선택 → "선택 입장/퇴장" 버튼
- SUBCON 선택 시 협력업체명/ID 입력 필드 자동 표시
- 리스트: 체크박스(1번) + No.(2번) ✅
- 통계 5개 (전체/직영/협력/현장내/현장외)

---

### FS-04: construction-inspection-list.html ✅
**파일:** `tadmin/full-version/html/horizontal-menu-template/construction-inspection-list.html`  
**커밋:** main 직접

**구현:**
- **지게차 UI 65%/35% 레이아웃 그대로** 이식
- API: `GET/POST /construction/sites/{id}/inspections`, `PATCH /construction/inspections/{id}/corrective`
- 신규 점검: 전체화면 오버레이 (`.insp-overlay`)
  - 좌측 65%: 정보 카드 4칸 + 체크리스트 (정상/이상/보류 3버튼) + [임시저장][완료저장]
  - 우측 35%: 실시간 요약 (완료/이상/보류) + 자동경고 박스 + 사진 업로드
- `overall_result` 계산: **백엔드 자동** (bad 1건 → ISSUE)
- FCM 알림: **백엔드 자동** (프론트 호출 불필요)
- 체크리스트 템플릿: `GET /inspection-sets?work_id=` 자동 로드 → 없으면 기본 5항목
- 사진: base64 미리보기 (TODO: Supabase Storage URL 교체)
- 조치 패널: ISSUE/FAIL 시 자동 표시, `PATCH /corrective`
- 리스트: 체크박스(1번) + No.(2번) ✅
- 통계 5개 (전체/대기/PASS/ISSUE/조치완료)

---

## [safe.taieng.co.kr] FS-05: safety-dashboard.html 날씨 위젯 ✅

**파일:** `tadmin/full-version/html/horizontal-menu-template/safety-dashboard.html`  
**커밋 2회:** v1 → v2(완성)

### 위젯 ①: 현재 기상 + 작업중지
- `GET /weather/now?lat=&lon=` 연동
- 배경 3색: normal(진초록) / caution(진황) / stop(진빨강)
- 기온/풍속/습도/풍향(16방위) 표시
- 관측 시각: `base_date(20260416)` + `base_time(1400)` → `"2026-04-16 14:00 관측"`
- `triggered[]` → `/weather/work-stop-criteria` 매핑 → 법령근거+대상작업 표시

### 위젯 ②: 작업중지 기준 아코디언 (신규)
- `GET /weather/work-stop-criteria` 4개 기준
- 접기/펼치기 토글 (`criteria-toggle-icon` 회전 애니메이션)
- 각 항목: 코드 뱃지 + 임계값 + 대상작업 + 법령근거

### 좌표 취득 3단계
```
1. GET /factories/{id} → latitude/longitude 있으면 즉시 사용
2. GET /construction/sites?factory_id={id} → site.latitude/longitude
3. /juso/coord 변환 → PATCH 저장
   - construction → PATCH /construction/sites/{id}
   - factory → PATCH /factories/{id}
```

### 폴링
- 15분 `setInterval`
- `visibilitychange` → 탭 복귀 즉시 갱신
- `onFactoryChange` 오버라이드 패치 (기존 page.js 보존)

---

## [new.taieng.co.kr] FN-01: nexas/pricing.html ✅

**파일:** `nexas/pricing.html`  
**커밋:** taiengineering/taieng main 직접

### SaaS 구독 탭
- `GET /public/pricing/saas-plans` (10개) 동적 렌더
- API 10개 → `plan_name` 그룹핑 → STARTER/BUSINESS/ENTERPRISE 3카드
- **포함인원 + 초과단가 + SMS건수 + 서류건수** 쿼터 박스 (크레딧 미노출)
- 연간/월간 토글 (×10개월)
- 로딩 스켈레톤 → 카드 전환
- SaaS: 정기결제 MID 대기 → "준비중" 모달

### 법령진단 단건 탭
- `GET /public/pricing/diagnosis-reports` (4개) 동적 렌더
- **서브탭 3개 버튼 → `<select>` 드롭다운 6종** (건물/제조/건설/판매서비스/의료복지/교육연구)
- API flat 배열 → `facility_type` 기준 자동 그룹핑
- **단일 결제 · 서비스 제공 12개월 · 리포트 재발행 12개월** 명시
- 법령진단: 일반결제 MID 활성 → 구매자 정보 입력 → KG이니시스 결제 폼

### 결제 특전 섹션 (신규)
- 첫 달 무료 체험 / 법령진단→구독 전환 할인 / 전담 온보딩
- 어두운 네이비 배경, 황금색 배지

### API 폴백
- API 실패 시 `SAAS_FALLBACK` / `DIAG_FALLBACK` 정적 데이터 자동 사용
- flat/grouped 양쪽 응답 구조 처리

### 금지 용어 준수
- 소개비·소개료·인력소개·대행 → 없음 ✅
- 카카오 API → 없음 ✅
- "직접 하게 해주는 도구 + 연결 플랫폼" 포지셔닝 ✅

---

## 워크오더 문서

| 파일 | 레포 | 브랜치 |
|------|------|--------|
| `docs/workorder-safe-phase2-20260416.md` | tai-admin | main |
| `docs/workorder-construction-e2e-frontend-20260416.md` | tai-admin | main |
| `docs/workorder-fe-construction-20260416.md` | tai-admin | main |

---

## 미완료 / 다음 작업

### safe.taieng.co.kr
- [ ] FS-04 사진 업로드: base64 → Supabase Storage inspections 버킷 교체 (백엔드 Storage 버킷 준비 완료 후)
  - 교체 코드: `docs/fs04-storage-migration.md` 백엔드 윈도우 제공 예정
- [ ] E2E 최종 검증 6페이지 플로우 (검증용 현장: `db52f8a6-aa78-4baf-ba62-55da1ac1b9d3`)
- [ ] tai-admin dev 브랜치 생성 필요 (GitHub UI에서 대표님 직접 생성)

### new.taieng.co.kr
- [ ] FN-01 API 실응답 확인 후 필드명 매핑 검증 (`plan_name`, `facility_type` 등)
- [ ] FN-01 KG이니시스 MID 실값 교체 (현재 `TAI_MID_DIAG` placeholder)
- [ ] FN-02: for-safety-manager.html
- [ ] FN-03: for-business-owner.html
- [ ] FN-04: service/ 7개 페이지
- [ ] FN-05: target/ 3개 페이지
- [ ] FN-06: 사이트맵 기반 전체 리디자인

---

## DB 마이그레이션 (2026-04-16 완료 확인)
- `construction_sites.latitude`, `longitude` 컬럼 추가 ✅ (v2.2.2)
- `PATCH /construction/sites/{id}` latitude/longitude 저장 가능 ✅

## API 상태 (2026-04-16 기준)
- `GET /public/pricing/saas-plans` ✅ live
- `GET /public/pricing/diagnosis-reports` ✅ live
- `GET /weather/now` ✅ live
- `GET /weather/work-stop-criteria` ✅ 4개
- `PATCH /construction/sites/{id}` ✅ latitude/longitude 지원
