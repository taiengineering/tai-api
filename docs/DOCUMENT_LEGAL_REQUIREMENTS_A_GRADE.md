# A등급 29건 법적 필수 기재항목 + TAI 수집 갭 분석

> 작성일: 2026-04-30
> 목적: 문서 엔진의 설계 기준 — 앱에서 수집해야 할 항목 확정
> 핵심 원칙: 법이 요구하는 건 "기록 유지"이지 "특정 양식"이 아님

---

## 요약

| 구분 | 건수 | 법정양식 | TAI 설계 자유도 |
|------|------|----------|----------------|
| 카테고리 1: 안전보건교육 기록 | 3건 | 없음 (항목만 규정) | ★★★★ |
| 카테고리 2: 안전점검 기록 | 6건 | 없음 (기록 유지 의무) | ★★★★★ |
| 카테고리 3: TBM 기록 | 2건 | 없음 (권고, 가이드만) | ★★★★★ |
| 카테고리 4: 보호구 점검 기록 | 1건 | 없음 | ★★★★★ |
| 카테고리 5: 설비별 점검 기록 | 16건 | 없음 (개별법 기록 의무) | ★★★★ |
| 카테고리 6: 공사일지 | 1건 | **있음** (건기법 시행규칙 별지) | ★★ |

---

## 카테고리 1: 안전보건교육 기록

**해당 문서:** DOC-OSH-006, DOC-OSH-037, DOC-SERA-006
**법적 근거:** 산안법 제29조, 시행규칙 제26조, 별표4(교육시간), 별표5(교육내용)
**법정 양식:** 없음
**보존 기간:** 3년

### 법적 필수 기재항목

| No | 항목 | 근거 | TAI 현재 | 추가 필요 |
|----|------|------|---------|----------|
| 1 | 교육일시 (날짜 + 시간) | 시행규칙 별표4 | education_history.completed_at ✅ | - |
| 2 | 교육내용 (별표5 교육대상별) | 시행규칙 별표5 | education_master.education_code ✅ | - |
| 3 | 교육시간 (실시 시간) | 시행규칙 별표4 | education_history.completed_hours ✅ | - |
| 4 | 교육대상자 명단 | 시행규칙 제26조 | education_history.user_id ✅ | - |
| 5 | 출석 여부 | 안전보건교육규정 | education_history.status_code ✅ | - |
| 6 | 교육 방법 (집체/현장/원격 등) | 안전보건교육규정 제3조의 2 | education_history.method ✅ | - |
| 7 | 교육 장소 | 안전보건교육규정 | education_history.location ✅ | - |
| 8 | 교육 강사 (자격 요건 충족자) | 시행규칙 제26조② | ❌ | **추가 필요** |
| 9 | 교육자료 (제목/내용 요약) | 안전보건교육규정 | ❌ | **추가 필요** |

### TAI 수집 갭

- **추가 필요 필드 2개:**
  - `education_history.instructor_name` (TEXT) — 교육 강사명
  - `education_history.material_summary` (TEXT) — 교육자료 제목/요약

---

## 카테고리 2: 안전점검 기록

**해당 문서:** DOC-OSH-007, DOC-OSH-017, DOC-OSH-038, DOC-OSH-055, DOC-CON-007, DOC-CON-LAW-014
**법적 근거:** 산안법 제38조(안전조치), 건기법 제62조
**법정 양식:** 없음 ("점검 결과를 기록·보존"만 규정)
**보존 기간:** 3년

### 법적 필수 기재항목

| No | 항목 | TAI 현재 | 추가 필요 |
|----|------|---------|----------|
| 1 | 점검일시 | safety_inspections.inspection_date ✅ | - |
| 2 | 점검자 (성명) | safety_inspections.inspector_id ✅ | - |
| 3 | 점검 대상 (설비/장소) | safety_inspections.asset_id ✅ | - |
| 4 | 점검 항목별 결과 (정상/이상/보류) | safety_inspection_results.result_code ✅ | - |
| 5 | 이상 발견 시 조치사항 | safety_inspection_results.note ✅ | - |
| 6 | 이상 발견 시 사진 | safety_inspection_results.photo_urls ✅ | - |
| 7 | 점검 완료 상태 | safety_inspections.status_code ✅ | - |

### TAI 수집 갭

- **추가 필요 필드: 없음** — 현재 구조로 충분
- 점검 항목(inspection_set_items) → 항목별 결과(safety_inspection_results) 매핑 완료
- 이상 시 사진(photo_urls JSONB) + 메모(note) 수집 완료

---

## 카테고리 3: TBM 기록

**해당 문서:** DOC-OSH-056, DOC-CON-012
**법적 근거:** 산안법 제38조 (권고, 법적 의무 아님)
**법정 양식:** 없음
**교육시간 인정 요건:** 교육일지/작업일지/앱 등으로 기록 유지 (고용노동부 2024.4 지침)

### 법적 필수 기재항목 (고노부 가이드 기준)

| No | 항목 | TAI 현재 | 추가 필요 |
|----|------|---------|----------|
| 1 | 작업일시 | tbm_meetings.work_date ✅ | - |
| 2 | 작업장소 | tbm_meetings.work_location ✅ | - |
| 3 | 작업내용 | tbm_meetings.work_description ✅ | - |
| 4 | 진행자 (관리감독자) | tbm_meetings.conductor_name ✅ | - |
| 5 | 위험요인 파악 | tbm_meetings.risk_items (JSONB) ✅ | - |
| 6 | 안전대책 | tbm_meetings.safety_items (JSONB) ✅ | **구조 개선 필요** (아래 참조) |
| 7 | 참석자 명단 | tbm_attendees.name ✅ | - |
| 8 | 참석 확인 (서명/앱) | tbm_attendees.signature_url ✅ | - |
| 9 | 건강상태 확인 (음주/피로/질병) | ❌ | **추가 필요** |
| 10 | 보호구 착용 확인 (개인별) | ❌ | **추가 필요** |

### TAI 수집 갭

- **구조 개선:** `risk_items`와 `safety_items`가 별도 JSONB로 분리되어 있어 위험요인-대책 매칭이 안 됨
  - 방안 A: risk_items 내부에 countermeasure 필드 추가 `{description, level, countermeasure}`
  - 방안 B: 현재 구조 유지하고 문서 렌더링 시 순서로 매칭

- **추가 필요 필드 2개 (`tbm_attendees` 테이블):**
  - `health_status` (TEXT, default 'OK') — 건강상태 (양호/이상)
  - `ppe_checked` (JSONB) — 개인별 보호구 착용 체크 `{"\uc548\uc804\ubaa8":true,"\uc548\uc804\ud654":true,...}`

---

## 카테고리 4: 보호구 점검 기록

**해당 문서:** DOC-OSH-046
**법적 근거:** 산안법 제41조 (보호구 지급·착용 의무)
**법정 양식:** 없음

### 법적 필수 기재항목

| No | 항목 | TAI 현재 | 추가 필요 |
|----|------|---------|----------|
| 1 | 점검일시 | ✅ inspections 모듈 | - |
| 2 | 점검자 | ✅ inspector_id | - |
| 3 | 작업자별 착용 보호구 종류 | ❌ | **TBM ppe_checked로 통합 가능** |
| 4 | 착용 상태 (정상/불량/미착용) | ❌ | **TBM ppe_checked로 통합 가능** |
| 5 | 조치사항 (불량 시 교체 등) | ❌ | **필요 시 메모 필드** |

### TAI 수집 갭

- TBM 카테고리의 `ppe_checked` JSONB와 통합 가능
- 별도 점검 데이터가 필요한 경우: 점검 모듈의 점검세트(inspection_sets)에 "보호구 점검" 세트 추가
- **결론: TBM에서 개인별 보호구를 수집하면 이 문서는 자동 해결**

---

## 카테고리 5: 설비별 점검 기록

**해당 문서 (16건):**
- 산업: DOC-OSH-059(기계), DOC-OSH-060(전기)
- 건설: DOC-CON-013(장비), DOC-CON-014/026(비계), DOC-CON-032(타워크레인), DOC-CON-043(방호조치)
- 건물: DOC-BLD-002(소방), DOC-BLD-009(전기), DOC-BLD-011(승강기), DOC-BLD-016(석면)
- 시설: DOC-FAC-002(가스), DOC-FAC-008(위험물), DOC-FAC-013(보일러), DOC-FAC-016(냉동기)
- 화학: DOC-CHEM-003(유해화학물질)

**법적 근거:** 각 개별법 (산안법, 전기안전관리법, 승강기법, 소방시설법, 고압가스법, 위험물법, 에너지법 등)
**법정 양식:** 없음 ("점검 결과를 기록·보존"만 규정)
**보존 기간:** 법별 상이 (2~5년)

### 법적 필수 기재항목 (공통)

| No | 항목 | TAI 현재 | 추가 필요 |
|----|------|---------|----------|
| 1 | 점검일시 | safety_inspections.inspection_date ✅ | - |
| 2 | 점검자 (성명 + 자격) | safety_inspections.inspector_id ✅ | - |
| 3 | 점검 대상 설비 (명칭/관리번호) | safety_inspections.asset_id ✅ | - |
| 4 | 점검 항목별 결과 | safety_inspection_results.result_code ✅ | - |
| 5 | 이상 발견 시 조치 내용 | safety_inspection_results.note ✅ | - |
| 6 | 사진 (이상 부위) | safety_inspection_results.photo_urls ✅ | - |
| 7 | 다음 점검 예정일 | work_schedules ✅ | - |

### TAI 수집 갭

- **추가 필요 필드: 없음** — 현재 구조로 충분
- 설비별 점검세트(inspection_sets + inspection_set_items)가 이미 설비 유형별로 분리 구성됨
- 점검 항목은 법령엔진에서 자동 생성되므로 설비별 항목이 이미 DB에 존재
- 16건 문서가 모두 **동일한 데이터 구조**(safety_inspections + results)를 사용
- 차이점은 점검세트의 항목 구성만 다름 (소방점검 항목 vs 전기점검 항목 vs 승강기점검 항목)

---

## 카테고리 6: 공사일지 (건설)

**해당 문서:** DOC-CON-006
**법적 근거:** 건설기술진흥법 시행규칙
**법정 양식:** **있음** — 시행규칙 별지 서식 (유일하게 법정 양식 존재)
**보존 기간:** 준공 후 10년

### 법정 필수 기재항목

| No | 항목 | TAI 현재 | 추가 필요 |
|----|------|---------|----------|
| 1 | 공사명 | construction_sites.name ✅ | - |
| 2 | 공사금액 | factories.construction_amount ✅ | - |
| 3 | 날씨 (천후) | ❌ | **추가 필요** (기상청 API 연결 가능) |
| 4 | 건설인력 (직종별 인원) | construction_workers ✅ | - |
| 5 | 장비 현황 (종류/대수) | ❌ | **추가 필요** |
| 6 | 작업내용 (공종별 작업 내역) | construction_inspections △ | 부분적 |
| 7 | 특기사항 | ❌ | **추가 필요** |
| 8 | 안전관리 활동 | construction_inspections △ | 부분적 |
| 9 | 기술관리 활동 | ❌ | **추가 필요** |

### TAI 수집 갭

- **추가 필요 필드:**
  - 날씨: 기상청 API 자동 연동 가능 (weather.py 이미 구현)
  - 장비 현황: construction_sites 또는 별도 테이블
  - 특기사항/기술관리: 간단 텍스트 입력 필드
- 이 문서는 법정 양식이 있으므로 해당 양식에 맞춰 템플릿 제작 필요

---

## 종합 갭 분석 요약

### DB 스키마 추가 필요 항목

| 테이블 | 추가 칼럼 | 타입 | 용도 |
|--------|----------|------|------|
| `education_history` | `instructor_name` | TEXT | 교육 강사명 |
| `education_history` | `material_summary` | TEXT | 교육자료 요약 |
| `tbm_attendees` | `health_status` | TEXT DEFAULT 'OK' | 건강상태 (OK/이상) |
| `tbm_attendees` | `ppe_checked` | JSONB | 개인별 보호구 체크 |

### 앱 입력 화면 수정 필요 영역

| 앱 화면 | 변경 내용 | 우선순위 |
|---------|----------|----------|
| TBM 참석 체크인 | 건강상태 선택(OK/이상) + 보호구 체크박스 | ★★★★★ |
| 교육 등록 화면 | 강사명 + 교육자료 제목 입력 필드 | ★★★★ |
| 건설 공사일지 | 장비현황 + 특기사항 + 기술관리 입력 | ★★★ |

### 핵심 발견

1. **29건 중 28건은 법정 양식 없음** → TAI가 표준 설계 가능
2. **앱 입력 화면 수정 범위가 작음** → 칸럼 4개 + 앱 화면 2~3개 수정으로 29건 전체 커버
3. **카테고리 2+5 (22건)는 이미 데이터 수집 완료** → 문서 템플릿만 만들면 됨
4. **가장 긴급한 갭: TBM의 개인별 보호구 + 건강상태** → 매일 사용하는 화면이므로 우선
5. **공사일지(1건)만 법정 양식 존재** → 해당 양식에 맞춰 별도 템플릿 제작 필요

### 권장 실행 순서

1. `tbm_attendees`에 `health_status` + `ppe_checked` 칸럼 추가 (오늘 바로)
2. TBM 체크인 앱 화면에 보호구 체크 + 건강상태 선택 UI 추가
3. `education_history`에 강사명 + 자료요약 칸럼 추가
4. 문서 템플릿 제작 (카테고리 2+5는 비이상 데이터로 바로 가능)
5. 공사일지 법정 양식 템플릿 별도 제작
