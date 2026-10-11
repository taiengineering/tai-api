---
wo: WO-REF01-XLS03-CLOSURE-EVIDENCE-FIX-005
date: 2026-10-11
status: BUILD_COMPLETE
correction_of: WO-REF01-XLS03-FINAL-FUNCTIONAL-CLOSURE-004
supersedes: WO-REF01-XLS03-FINAL-FUNCTIONAL-CLOSURE-004
publication: NOT_FOR_PUBLICATION
---

# XLS03 기능 QA 최종 교정 보고서

WO-REF01-XLS03-CLOSURE-EVIDENCE-FIX-005 FIX-01~03 완결 증거.
Baseline: `2876765c04839bc4f502e8b71ee0eb9efa690492`

---

## 1. 교정 결과 요약

| 항목 | 결과 |
|------|------|
| 빌드 대상 | 118 |
| 빌드 성공 | 118 / 0 ERROR |
| 유효성 검사 PASS | 118 / 118 |
| 필드 커버리지 PASS (강화, FIX-01) | 118 / 118 |
| 섹션별 개별 검증 (FIX-01) | 118/118 (sections_rendered=sections_source) |
| CALC_AGG 계약 교정 (FIX-02) | 13종 / 112열 / NOT_APPLICABLE_TEXT 68열 수정 |
| GUI QA (FIX-03) | UNVERIFIED (환경 없음 — 문서화 완료) |
| pytest | **188 passed / 0 failed** |
| 기존 PDF/DOCX 변경 | 0건 (PDF 147 + DOCX 145) |

---

## 2. FIX-A — CHECKLIST 입력 검증 수정 (WO-003 유지)

**문제**: 모든 데이터 열에 ○/× 적용
**교정**: label이 `결과|여부|유무|확인 (+(입력))?$` 패턴으로 끝나는 열에만 적용

| 서식 | 수정 전 | 수정 후 |
|------|--------|--------|
| CITYGAS-01 | 4개 열 전체 | C열만 (점검결과) |
| REF-C067 | 5개 열 전체 | E열만 (확인) |
| PRA-22-09 | 6개 열 전체 | E/F열 (여부·확인) |
| RP-17 | 5개 열 전체 | C열만 (이수 여부) |

검증 regex: `(결과|여부|유무|확인)\s*(\(입력\))?\s*$`

테스트: `test_citygas01_only_result_col_validated` / `test_result_suffix_regex` (16개 파라미터)

---

## 3. FIX-B — 행 추가 및 누적 기능 (WO-003 유지)

**문제**: 고정 행 수에 필터/검증 범위 한정
**교정**: repeat_table → Excel Table (TableStyleMedium2)

| 항목 | 변경 내용 |
|------|---------|
| 데이터 구조 | Excel Table (자동 확장) |
| 행 사전 할당 | max(default_rows × 4, 60) 행 |
| 자동 필터 | Table 내장 (ws.auto_filter 미사용) |
| 데이터 유효성 | 전체 할당 행 적용 |
| 인쇄 범위 | FIX-2에서 교정 |

테스트: `test_excel_table_present` / `test_table_row_count_exceeds_default`

**동적 확장 계약 (FIX-1)**:

Excel Table은 Excel 네이티브 기능으로 마지막 행에 새 행 입력 시 자동 확장된다.
사전 할당 60행 이내: 기존 서식·필터·유효성 검사 자동 적용.
사전 할당 초과 추가: Excel Table 범위 자동 확장(네이티브 동작), 인쇄 범위는 수동 갱신 필요.

| 검증 항목 | 결과 |
|---------|------|
| Excel Table 구조체 존재 (openpyxl) | PASS (118/118) |
| Table ref가 header+60행 이상 포함 | PASS (test_table_row_count_exceeds_default) |
| Freeze panes 설정 | PASS (test_freeze_panes) |
| GUI 실제 행 추가·저장·재열기 | UNVERIFIED (Python 환경 불가) |
| 사전 할당 초과 후 Table 자동 확장 | UNVERIFIED (GUI 필요) |
| 다른 섹션·승인란과 충돌 없음 | UNVERIFIED (GUI 필요) |

---

## 4. FIX-C — 계산식 전면 제거 (WO-003 유지)

**문제**: `_NUMERIC_KEYWORDS` 기반 SUM 자동 생성
**교정**: 모든 SUM 수식 제거. 수식 생성 로직 삭제.

| 서식 유형 | 이전 | 이후 |
|---------|------|------|
| CALC_AGG 비금지 (10건) | SUM 수식 생성 | 수동 입력 전용 |
| FORMULA_DIRECTION_UNVERIFIED (3건) | SUM 금지 | SUM 금지 (유지) |
| 비율/달성률 열 | SUM 적용됨 | 제거 |

테스트: `test_no_sum_formulas` (CHW-02, P-20, P-26, REF-C016, GOV-10)

---

## 5. FIX-D — 섹션 정의 순서 렌더링 + 필드 커버리지 (WO-003 유지)

**문제**: 타입 그룹별 복잡한 index 비교 → 동일 콘텐츠 섹션 순서 오류 가능
**교정**: sections[] 정의 순서 그대로 렌더링

추가 수정:
- `approval` 섹션 level label 렌더링 추가 (REF-C016: `연간 교육계획`)
- 필드 커버리지 검증기 `xlsx_field_coverage.py` 신설 (FIX-3에서 강화)

| 검증 항목 | 결과 |
|---------|------|
| 118종 basic_info 필드 | 118/118 PASS |
| 118종 repeat_table 컬럼 | 118/118 PASS |
| 118종 labeled_grid 레이블 | 118/118 PASS |
| 118종 freeform/approval 레이블 | 118/118 PASS |
| 118종 text_flow 문단 (FIX-3 추가) | 118/118 PASS |
| 중복 레이블 발생 횟수 검증 (FIX-3 추가) | 118/118 PASS |

테스트: `test_field_coverage_all_118` / `test_ref_c016_approval_label_rendered`

---

## 6. FIX-E — 문서 메타데이터 (WO-003 유지)

모든 .xlsx 파일에 다음 메타데이터 포함:
- `title`: 서식명
- `description`: `TAI-FORM | {rid} | INTERNAL_POC_ONLY | LEGAL_REVIEW_PENDING | RIGHTS_UNVERIFIED | GPT_REVIEW_REQUIRED`
- `creator`: TAI

테스트: `test_document_metadata`

---

## 7. FIX-1 — 동적 행 확장 계약 (WO-004 신규)

Excel Table 자동 확장 동작 계약:

| 범위 | 동작 | 상태 |
|------|------|------|
| 사전 할당 행 (최소 60행) 이내 입력 | 기존 서식·필터·유효성 유지 | STRUCTURAL_PASS |
| 사전 할당 행 초과 행 추가 | Excel Table 자동 확장 (Excel 네이티브) | UNVERIFIED_GUI |
| 인쇄 범위 자동 갱신 | 불가 — 수동 갱신 필요 | LIMITATION_DOCUMENTED |
| 여러 repeat_table 독립 확장 | 해당 없음 (전 서식 단일 Table) | N/A |

---

## 8. FIX-2 — 인쇄 범위 교정 (WO-004 신규)

**문제**: `row + 200` 고정 지정 → 빈 페이지 대량 출력 위험
**교정**: `ws.print_area = f"A1:{col}{row - 1}"` (실제 마지막 콘텐츠 행)

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| 인쇄 범위 | `A1:{col}{last_row+200}` | `A1:{col}{last_row}` |
| fitToPage | 1 (유지) | 1 (유지) |
| fitToWidth | 1 (유지) | 1 (유지) |
| 사전 할당 초과 인쇄 | 자동 포함 | 수동 인쇄 범위 확장 필요 |
| 실제 PDF 출력 검증 | UNVERIFIED | UNVERIFIED |

---

## 9. FIX-3 / FIX-01 — 필드커버리지 전수 검증 강화 (WO-004 + WO-005)

WO-004: text_flow 포함, 중복 레이블 횟수 검증
WO-005 FIX-01: sections_rendered 유형 수 → 개별 섹션 인스턴스 수로 교정

| 강화 항목 | 변경 내용 |
|---------|---------|
| text_flow 문단 | 검증 대상에 추가 |
| 중복 레이블 구별 | 발생 횟수 비교 (expected >= source count) |
| sections_rendered (FIX-01) | 고유 유형 수 → 개별 섹션 인스턴스별 검증 |
| count_mismatches | 별도 항목으로 기록 |
| sections_missing | 레이블 누락 섹션 수 별도 기록 |

결과: 118/118 OK — sections_rendered=sections_source 118/118 확인
(ENV-04, GOV-01, H2-02, MNT-03, P-25, REF-C008, REF-C043, REF-C044, REF-C047, RP-04 회귀검증 PASS)

---

## 10. FIX-4 / FIX-02 — CALC_AGG 전량 수동입력 계약 (WO-004 + WO-005)

13종 CALC_AGG 서식 전량 `ALL_MANUAL` 상태 확정.

| 서식 | 제목 | 수동 이유 |
|------|------|---------|
| CHW-02 | 화학물질 출고·사용 불출대장 | 집계 기준 미확정 |
| CHW-03 | 화학물질 재고실사·차이처리표 | FORMULA_DIRECTION_UNVERIFIED |
| GOV-09 | 안전보건 시정조치(CAPA) 관리대장 | 완료율 판단 기준 미확정 |
| GOV-10 | 안전보건 연간 활동계획·실적 대비표 | 달성률 기준 미확정 |
| P-20 | 산업안전보건관리비 사용계획·집행내역 | 법정 집계 기준 별도 확인 필요 |
| P-26 | 월간 안전보건 지표·경영보고서 | 계획값 기준 가변 |
| REF-C004 | 유해·위험물질 목록 작성 서식 | FORMULA_DIRECTION_UNVERIFIED |
| REF-C007 | 안전보건예산 편성 서식 | 연도·구분별 복합 계산; 기준 미확정 |
| REF-C011 | 도급·용역·위탁 업체 안전보건 수준 평가 | 가중치 미검증 |
| REF-C016 | 연간 안전보건교육 수립 서식 | 대상 인원 기준 가변 |
| REF-C029 | 빈도·강도법 위험성평가표 | FORMULA_DIRECTION_UNVERIFIED |
| REF-C071 | 건강진단 일정·실시 관리대장 | 수검 대상 인원 변경 가능 |
| RP-01 | 설비 예방보전 일정·실적표 | 점검결과 분류 후 담당자 판단 |

WO-005 FIX-02 교정:
- `불출처/수령자`, `수급업체`, `CAS번호`, `CAS No`, `분자식` 등 문자 열 → `numeric=NO / NOT_APPLICABLE_TEXT`로 수정
- formula_status 3단계 구분: `REMOVED_VERIFIED` (테스트 검증 완료) / `REMOVAL_NOT_VERIFIED` (수치열이나 미테스트) / `NEVER_GENERATED` (FORBIDDEN 서식) / `NOT_APPLICABLE_TEXT` (문자열)

| formula_status | 건수 | 의미 |
|---------------|------|------|
| NOT_APPLICABLE_TEXT | 68 | 문자/날짜 열 — 수식 대상 아님 |
| NEVER_GENERATED | 33 | FORBIDDEN 서식 (CHW-03/REF-C004/REF-C029) |
| REMOVED_VERIFIED | 7 | 수치열, FIX-C 테스트로 제거 확인 |
| REMOVAL_NOT_VERIFIED | 4 | 수치열이나 명시적 테스트 없음 |

상세 근거: `XLS03-CALC-AGG-MANUAL-CONTRACT.csv` (112행)

신규 수식 추가 조건: 근거·입력·출력·경계값이 확인된 것만, 별도 계약 필요.

---

## 11. pytest 188/188 PASS (WO-005 재실행)

```
pytest test_xlsx_builder.py
  188 passed / 0 failed
  실행 로그: XLS03-PYTEST-LOG-005.txt
```

테스트 분류 (수정됨 — 구 보고서 표 합계 오류 187 → 188 정정):

| 범주 | 건수 |
|------|------|
| Registry/JSON | 5 |
| 기본 빌드 | 12 |
| 제목·메타데이터 | 7 |
| Excel Table (FIX-B) | 10 |
| Checklist validation (FIX-A) | 23 |
| 수식 금지 (FIX-C) | 8 |
| 섹션 순서/필드 (FIX-D) | 5 |
| 전수 Validation | 118 |
| **합계** | **188** |

---

## 12. 미검증 사항 (UNVERIFIED — 변경 불가)

| 항목 | 상태 |
|------|------|
| Excel GUI 실제 입력·저장·재열기 | UNVERIFIED |
| 사전 할당 초과 행 추가 후 Table 자동 확장 GUI | UNVERIFIED |
| 인쇄 출력·PDF 변환 레이아웃 | UNVERIFIED |
| 사전 할당 초과 시 인쇄 범위 수동 갱신 필요 | LIMITATION_DOCUMENTED |
| REF-C002 어댑터 필드 시각 배치 | UNVERIFIED |
| REF-C067 `점검 결과(양호/불량/해당없음)` 별도 드롭다운 | NOT_IMPLEMENTED |

---

## 13. 기존 파일 불변

```
output/*.pdf  → 147건 변경 없음
output/*.docx → 145건 변경 없음
scripts/*.json → 변경 없음
```

---

## 14. 증거 파일 목록

| 파일 | 내용 |
|------|------|
| XLS03-FUNCTIONAL-QA-RESULT.csv | 118종 빌드·유효성·커버리지·SHA256 (sections_rendered 포함) |
| XLS03-118-FIELD-COVERAGE.csv | 118종 섹션별 개별 커버리지 (FIX-01 교정) |
| XLS03-FORMULA-CONTRACT-RESULT.csv | 711열 수식 계약 |
| XLS03-CALC-AGG-MANUAL-CONTRACT.csv | CALC_AGG 13종 formula_status 4단계 (FIX-02 교정) |
| XLS03-PYTEST-LOG-004.txt | WO-004 pytest 원문 로그 |
| XLS03-PYTEST-LOG-005.txt | WO-005 pytest 원문 로그 |
| XLS03-GUI-QA-005.md | GUI QA UNVERIFIED 증거 문서 (FIX-03) |

---

## 15. 법률·권리·공개 HOLD 유지

모든 서식: `LEGAL_REVIEW_PENDING | RIGHTS_UNVERIFIED | INTERNAL_POC_ONLY | GPT_REVIEW_REQUIRED`
