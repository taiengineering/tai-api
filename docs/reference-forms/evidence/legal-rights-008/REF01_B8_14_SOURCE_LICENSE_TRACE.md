---
wo: WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008
doc_type: SOURCE_LICENSE_TRACE
date: 2026-10-10
base_head: 9864b9ac2039086747b68d0ff31507ac40806a27
---

# REF01 B8 14종 — 출처·라이선스 추적

## 1. 조사 범위 및 방법

### 접근 방법
- 이 조사 컨텍스트 내 읽기 전용 파일 열람: reports 02, 03, 10, 13, 15, 24, 31, 32 + governance_matrix.json
- 원본 HWP/HWPX/ZIP/PDF 파일 **접근 없음** — 기존 연구 문서 기록만 사용
- 외부 웹 접속 없음 — 기존 연구 문서 내 URL 인용 기록만 참조

### 핵심 선행 판정
- 14종 모두 `source_match=NOT_VERIFIED`, `source_document_access=NOT_CHECKED` (governance_matrix.json)
- **원본 파일 미검사 = SIMILARITY_UNVERIFIED** — 유사도 주장 불가, 독자성 주장도 사실 기반 미확인

---

## 2. 출처 유형별 분류

### A. TAI_PROPOSED 그룹 (C026–C029, C031, C033, C037)

**공통 특성:**
- 연구 레지스터(report 13): WORKFLOW_DRAFT / TAI_CANDIDATE
- 연구 문서(report 09 참조): MOEL 2023 컨설팅 안내 7개 워크플로우 카테고리 기반 독자 후보화
- 원본 3자 파일: 미검사
- TAI 주장 원창작성: `authoring_class=TAI_ORIGINAL_DRAFT` — 자기 기술이며 독립 증거 아님

**개별 출처 관련 추가 기록:**

| 서식 | 출처 연관 기록 | 유사 공식 서식 존재 여부 | 원본 검사 여부 |
|------|-------------|---------------------|-------------|
| C026 | 3단계 판단법 — report 02 S4 KOSHA FAQ snippet (방법 언급) | KOSHA 24종에 직접 대응 없음 | SOURCE_FILE_NOT_INSPECTED |
| C027 | 체크리스트형 — report 02 S4 방법 언급 | KOSHA 24종에 직접 대응 없음 | SOURCE_FILE_NOT_INSPECTED |
| C028 | OPS/핵심요인분석법 — TAI 명칭; 외부 원전 불명 | KOSHA 24종에 직접 대응 없음 | SOURCE_FILE_NOT_INSPECTED |
| C029 | 빈도강도법 — KOSHA 24종 REF-C006 '위험성평가표(빈도강도법)' 유사명 존재 | **주의: KOSHA 붙임2 HWP 원본 미검사** — 유사도 UNVERIFIED | SOURCE_FILE_NOT_INSPECTED |
| C031 | 안전보건교육일지 — KOSHA 24종 REF-C024 '안전보건교육일지 서식(엑셀·한글)' ZIP 유사명 존재 | **주의: 붙임5 ZIP 원본 미검사** — 유사도 UNVERIFIED | SOURCE_FILE_NOT_INSPECTED |
| C033 | 도급업체 이행점검표 — KOSHA 24종 REF-C011 '도급·용역·위탁 업체 안전보건 수준 평가' 유사명 존재 | **주의: KOSHA 붙임2 HWP 원본 미검사** — 유사도 UNVERIFIED | SOURCE_FILE_NOT_INSPECTED |
| C037 | 위험개선 건의대장 — KOSHA 24종 직접 대응 없음 | 없음 | SOURCE_FILE_NOT_INSPECTED |

**KOSHA 배포 서식 재사용 허가 여부 (C029, C031, C033 해당):**
- KOSHA posting (report 03): "게시된 참고서식은 사업장 상황에 맞게 수정 가능"
- **이 문구는 사업장 내부 사용 허가이며, 상업적 SaaS 배포·유료 다운로드 허가 아님**
- KOGL(공공누리) 적용 여부: 해당 KOSHA 게시 자료 대상 KOGL 유형 미확인 (유형 1~4 중 어느 것인지 미검사)
- 결론: 상업적 재배포 권한 → `RIGHTS_UNVERIFIED / PERMISSION_REQUIRED`

---

### B. MIXED 그룹 (C039–C044)

**공통 특성:**
- 연구 레지스터(report 13): CHEM_FIRE / MIXED — 공식 법령 참조 존재하나 원본 서식 파일 미확인
- `authoring_class=TAI_ORIGINAL_DRAFT` — 자기 기술

**WO-008A 정정 — KOSHA MSDS 경고 적용 범위 구분:**

WO-008에서 KOSHA MSDS 시스템 상업 재사용 경고(report 10 S2)를 C039-C044 전체에 적용한 것은 과잉 일반화임. 실제 적용 범위는 아래 3가지로 구분해야 함:

| 구분 | 대상 | 적용 서식 | 설명 |
|------|------|---------|------|
| CASE A | KOSHA MSDS 원본 콘텐츠 직접 재사용 | C040 (MSDS 이력) — UNVERIFIED | KOSHA MSDS 시스템이 제공하는 원본 MSDS 데이터 자체를 복사·재배포하는 경우. 명시적 상업 재사용 경고(report 10 S2) 적용. |
| CASE B | KOSHA MSDS 참조 기반 파생 서식 | C040, C044 — UNVERIFIED | MSDS 관리 실무를 반영하되 KOSHA 제공 MSDS 데이터 자체를 복사하지 않는 경우. 경고 적용 여부 불확실. |
| CASE C | TAI 독자 설계 관리 서식 | C039, C041, C042, C043 — UNVERIFIED | 법령 참조 구조를 갖추되 KOSHA MSDS 시스템과 직접 관련 없는 관리 서식. KOSHA MSDS 경고 직접 적용 근거 없음. 그러나 TAI 독자성 증거도 미확인. |

**주의**: CASE 구분은 현재 서식 JSON 명세 기반 잠정 분류. 원본 3자 파일 미검사로 정확한 유사도·파생관계 미확인.

**개별 출처 관련 추가 기록:**

| 서식 | 참조 출처 | MIXED 분류 근거 추정 | 원본 검사 여부 | KOSHA MSDS 경고 적용 | 권리 위험 |
|------|---------|-------------------|-------------|-------------------|---------|
| C039 | 산업안전보건법 제110조 / 화학물질관리법 (취급목록 관리) | 법령상 의무 존재 + TAI 서식 | SOURCE_FILE_NOT_INSPECTED | CASE C — 직접 적용 근거 없음 | UNVERIFIED |
| C040 | 산업안전보건법 제114조 (MSDS 보관) | 법령상 의무 존재 + MSDS 이력 실무 | SOURCE_FILE_NOT_INSPECTED | CASE A/B — MSDS 데이터 직접 복사 여부 미확인 | UNVERIFIED |
| C041 | 산업안전보건법 제115조 (GHS 경고표지) | GHS 기준 참조 + 점검 실무 | SOURCE_FILE_NOT_INSPECTED | CASE C — GHS 원문 도식 별도 라이선스 확인 필요 | UNVERIFIED |
| C042 | 화학물질관리법 보관시설 기준 | 법령 보관기준 참조 + 점검 실무 | SOURCE_FILE_NOT_INSPECTED | CASE C — 직접 적용 근거 없음 | UNVERIFIED |
| C043 | 화학물질관리법 제41조 (사고대비물질 비상대응) 추정 | 법령상 훈련 의무 + 실무 기록 | SOURCE_FILE_NOT_INSPECTED | CASE C — 직접 적용 근거 없음 | UNVERIFIED |
| C044 | 산업안전보건법 제114조 (MSDS 교육·주지) | 교육 의무 + 확인기록 실무 | SOURCE_FILE_NOT_INSPECTED | CASE B — MSDS 교육 기록 서식; 데이터 복사 여부 미확인 | UNVERIFIED |

---

### C. OFFICIAL_PROCESS_AND_TAI_HYPOTHESIS (GOV-01)

| 항목 | 기록 |
|------|------|
| 참조 출처 | 산업안전보건법 제24조 — 위원회 회의록 작성·보존 의무 (report 15 S1) |
| 원본 서식 | 법정 별지 서식 없음 — 법 제24조가 기록 의무를 부과하나 특정 양식을 지정하지 않음 |
| TAI 기여 | 열 구조 전체 TAI 제안 (회의일시·장소·참석·안건·논의·의결·서명) |
| 유사 공식 서식 | 미발견 (prescribed annex 없음) |
| 저작권 귀속 | 법정 절차 기반 독자 서식 — 정부 원본 복제 없음; TAI 창작성 주장 가능하나 독립 증거 확보 필요 |
| 재사용 권한 | RIGHTS_UNVERIFIED — 법적 절차 기반이라 해도 TAI 독자 표현에 대한 권리 별도 확인 필요 |

---

## 3. 권리 사용 가능 분류 요약

각 사용 형태별 14종 전체 판정:

| 사용 형태 | 판정 | 근거 |
|---------|------|------|
| 내부 사적 참조 | 제한 없음 (현재 상태) | INTERNAL_POC_ONLY 유지 중 |
| 독자 설계 빈 서식 작성 | 조건부 가능 — TAI 창작성 증거 확보 시 | source_match=NOT_VERIFIED; 원본 비교 미완료 |
| 원본 3자 필드 표현 복사 | UNVERIFIED / BLOCKED | 원본 파일 미검사; KOSHA 상업 재사용 경고 |
| 수정/파생물 재생산 | UNVERIFIED / BLOCKED | 원본 검사 없이 판단 불가 |
| PDF/DOCX 다운로드 배포 | BLOCKED (현재) | PUBLICATION=INTERNAL_POC_ONLY |
| 유료 SaaS 상업 배포 | BLOCKED | 어떤 형태의 명시적 상업 라이선스도 미확인 |
| KOSHA 자료 직접 재배포 | BLOCKED | KOSHA 상업 재사용 경고 명시 (report 10 S2) |

---

## 4. 권리 검토 위험도 요약

| 위험 등급 | 서식 | 이유 |
|---------|------|------|
| 주의 (원본 비교 시급) | C029, C031, C033 | KOSHA 24종 내 유사명 서식 존재 — 원본 HWP/ZIP 검사 전 판단 불가 |
| 검토 필요 | C039-C044 | MIXED class; KOSHA MSDS 상업 재사용 경고; 법령 조건 미확인 |
| 낮음 (상대적) | C026, C027, C028, C037, GOV-01 | KOSHA 24종 직접 대응 미발견 — 그러나 TAI 독자성 증거도 미확인 |

**주의: "낮음"은 위험 없음을 의미하지 않음. 모든 14종은 원본 비교 미완료 상태.**

---

## 5. 한계 및 다음 단계

1. 14종 전체 `original attachment = NOT_INSPECTED / UNVERIFIED` — 유사도 판단 불가
2. KOGL 적용 여부(유형 1~4) 미확인 — KOSHA 게시 자료 개별 검사 필요
3. 상업적 재배포 권한: 어떤 서식도 명시적 라이선스 없음 → `PERMISSION_REQUIRED` 이상 상태로 유지
4. TAI 독자 창작성: 자기 기술(`authoring_class=TAI_ORIGINAL_DRAFT`)만으로 권리 주장 불충분 — 설계 이력 증거 별도 필요

```
RIGHTS_CLEAR_COUNT      = 0
RIGHTS_UNVERIFIED_COUNT = 14
PERMISSION_REQUIRED     = 14
COMMERCIAL_BLOCKED      = 14
ORIGINAL_ATTACHMENT_INSPECTED = 0/14
```
