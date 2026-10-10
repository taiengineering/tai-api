---
wo: WO-REF01-XLS03-CLOSURE-EVIDENCE-FIX-005
date: 2026-10-11
status: UNVERIFIED
section: FIX-03
publication: NOT_FOR_PUBLICATION
---

# XLS03 GUI QA 검증 결과

WO-005 FIX-03 — 실제 Excel GUI 사용성 검증 시도 결과.

---

## 1. 검증 환경

| 항목 | 상태 |
|------|------|
| 실행 환경 | Python 3.14 / macOS (헤드리스 CI 유사 환경) |
| Microsoft Excel | 설치 없음 |
| LibreOffice Calc | 설치 없음 |
| openpyxl | 구조 검증 전용 (GUI 없음) |

---

## 2. GUI 검증 항목별 결과

| 검증 항목 | 결과 | 비고 |
|---------|------|------|
| 최초 제공 행 내 입력·저장·재열기 | UNVERIFIED | Excel GUI 접근 불가 |
| 최초 제공 행 초과 신규 행 추가 | UNVERIFIED | Excel GUI 접근 불가 |
| Excel Table 범위 자동 확장 여부 | UNVERIFIED | Excel GUI 접근 불가 |
| 신규 행 필터·서식·유효성 유지 | UNVERIFIED | Excel GUI 접근 불가 |
| 다른 섹션·승인란과 충돌 여부 | UNVERIFIED | Excel GUI 접근 불가 |
| 한글 표시·인쇄 미리보기 | UNVERIFIED | Excel GUI 접근 불가 |
| REF-C002 레거시 필드 시각 배치 | UNVERIFIED | Excel GUI 접근 불가 |
| 인쇄 시 빈 페이지 발생 여부 | UNVERIFIED | Excel GUI 접근 불가 |
| REF-C067 드롭다운 표시 | NOT_IMPLEMENTED | 별도 계약 필요 |

---

## 3. openpyxl 구조 검증 (PASS)

Excel 파일 열기 없이 검증 가능한 항목:

| 항목 | 검증 방법 | 결과 |
|------|---------|------|
| Excel Table 객체 존재 | `ws._tables` | 118/118 PASS |
| Table ref 범위 (≥60행) | `tbl.ref` 파싱 | PASS (`test_table_row_count_exceeds_default`) |
| Freeze panes 설정 | `ws.freeze_panes` | 117/118 PASS (MNT-03 제외) |
| 인쇄 범위 실제 콘텐츠 행 | `ws.print_area` | 재빌드로 수정됨 |
| 데이터 유효성 검사 설정 | `ws.data_validations` | 30 CHECKLIST 서식 결과열만 적용 |
| 메타데이터 | `wb.properties.title` | 118/118 PASS |

---

## 4. 동적 행 확장 계약 (LIMITATION)

Excel Table은 마지막 행에서 Tab 키 또는 직접 입력 시 자동 확장됩니다 (Excel 네이티브 동작).

| 항목 | 상태 |
|------|------|
| 사전 할당 60행 이내: 서식·필터·유효성 | STRUCTURAL_PASS (openpyxl 검증) |
| 사전 할당 초과 후 Table 자동 확장 | UNVERIFIED_GUI |
| 사전 할당 초과 후 인쇄 범위 자동 갱신 | NOT_SUPPORTED — 수동 갱신 필요 |

**사용 지침 (기록)**: 사전 할당 행 초과 시 Excel의 '페이지 레이아웃 → 인쇄 영역 → 인쇄 영역 설정'으로 수동 갱신 필요.

---

## 5. 결론

GUI 검증 9개 항목 전부 UNVERIFIED.
구조 검증 (openpyxl 기반) 6개 항목 PASS.

Excel GUI 접근 가능한 환경에서 추가 검증 필요.
현재 상태로 CLOSED_FINAL 불가.
