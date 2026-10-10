---
wo: WO-REF01-060-B14-INVENTORY-RECONCILIATION-001
date: 2026-10-10
status: COMPLETE
base_head: 3834c2d45e3b1f147a3ae3b1fa2b21d2613a0ace
b15_ready_count: 8
---

# B15 제작 큐 — 8건

B14 중복 판정 결과 NEW_BUILD_REQUIRED(7) + SHARED_TEMPLATE_DISTINCT(1) 확정.

모든 항목은 기존 조사자료만으로 제작 가능하며, 법적 효력·공식 원본 복제 문제 없음.

---

## 제작 대상 목록

| # | research_id | source_title | document_type | B14_decision | 비고 |
|---|-------------|-------------|---------------|-------------|------|
| 1 | PRA-22-02 | 화학물질 로케이션 적치·이동기록 | REGISTER | NEW_BUILD_REQUIRED | |
| 2 | PRA-22-06 | 설비 보전작업 완료·재가동 인계서 | FORM | NEW_BUILD_REQUIRED | |
| 3 | PRA-22-08 | 연구실 사고·이상 발생 초동조치·종결 기록 | REPORT | NEW_BUILD_REQUIRED | |
| 4 | PRA-22-09 | 현장 안전점검 사진·증빙 인계목록 | CHECKLIST | NEW_BUILD_REQUIRED | |
| 5 | REF-C022 | 중량물 취급 작업계획서 | PLAN | NEW_BUILD_REQUIRED | |
| 6 | REF-C023 | 안전보호구 지급대장 | REGISTER | NEW_BUILD_REQUIRED | |
| 7 | REF-C067 | 현장 일일 안전점검 기록표 | CHECKLIST | NEW_BUILD_REQUIRED | |
| 8 | PRA-22-10 | 안전관리 미종결과제 주간 인수인계표 | RECORD | SHARED_TEMPLATE_DISTINCT | GOV-09 연관, 트리거 상이 |

---

## 항목별 제안 필드

### 1. PRA-22-02 — 화학물질 로케이션 적치·이동기록 (REGISTER)

```
기본정보: 사업장명, 기록 기간, 담당자
반복표 (10행 이상):
  번호 | 물질명 | 로케이션(적치구역) | 이동일 | 이동 후 위치 | 이동 사유 | 확인자
```

### 2. PRA-22-06 — 설비 보전작업 완료·재가동 인계서 (FORM)

```
기본정보: 설비명, 작업일시, 작업자
작업 내용 및 결과 (freeform)
재가동 전 체크사항 (체크리스트)
인계: 작업완료 서명, 수령자, 재가동 승인자
```

### 3. PRA-22-08 — 연구실 사고·이상 발생 초동조치·종결 기록 (REPORT)

```
기본정보: 연구실명, 발생일시, 보고자
사고 개요 (freeform)
초동조치 내용 (freeform)
원인 분석 (freeform)
종결 확인 및 서명 (approval)
```

### 4. PRA-22-09 — 현장 안전점검 사진·증빙 인계목록 (CHECKLIST)

```
기본정보: 현장명, 점검일, 인계자
반복표 (10행):
  번호 | 사진번호 | 촬영 위치·구역 | 점검 내용 | 조치 필요 여부 | 인계 확인
인계 서명 (approval)
```

### 5. REF-C022 — 중량물 취급 작업계획서 (PLAN)

```
기본정보: 사업장명, 작업일시, 작업책임자
작업 개요: 중량물명, 중량(kg), 작업 위치
취급 장비: 장비명, 용량, 검사 여부
안전조치 계획 (freeform)
작업 참여자 (반복표: 성명, 소속, 역할)
책임자 승인 (approval)
```

### 6. REF-C023 — 안전보호구 지급대장 (REGISTER)

```
기본정보: 사업장명, 관리부서, 담당자
반복표 (15행):
  번호 | 품목명·규격 | 지급일 | 지급수량 | 수령자명 | 소속 | 반납일 | 비고
```

### 7. REF-C067 — 현장 일일 안전점검 기록표 (CHECKLIST)

```
기본정보: 현장명, 점검일, 점검자
반복표 (15행, 구조화 점검):
  번호 | 점검 항목 | 점검 결과(양호/불량/해당없음) | 조치 내용 | 확인
점검자 서명 (approval)
```

### 8. PRA-22-10 — 안전관리 미종결과제 주간 인수인계표 (RECORD)

```
기본정보: 현장명, 인계 주차, 인계자
반복표 (10행):
  번호 | 과제 내용 | 발생일 | 현재 진행 상태 | 담당자 | 조치 기한 | 특이사항
인계·인수 서명 (approval)
```

---

## B15_READY 기준 확인

| research_id | 조사자료 입력항목 | 목적 명확 | engine 제작 가능 | 기존 중복 없음 | 법적 문제 없음 | B15_READY |
|-------------|----------------|----------|----------------|--------------|--------------|-----------|
| PRA-22-02 | YES | YES | YES | YES | YES | YES |
| PRA-22-06 | YES | YES | YES | YES | YES | YES |
| PRA-22-08 | YES | YES | YES | YES | YES | YES |
| PRA-22-09 | YES | YES | YES | YES | YES | YES |
| REF-C022  | YES | YES | YES | YES | YES | YES |
| REF-C023  | YES | YES | YES | YES | YES | YES |
| REF-C067  | YES | YES | YES | YES | YES | YES |
| PRA-22-10 | YES | YES | YES | YES | YES | YES |

B15_READY_COUNT = 8
