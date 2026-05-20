# TAI Runtime 연결 — 기존 자산 재사용 중심 구현 작업지시서

## 작성일: 2026-05-20
## 상태: P0 운영 연결 단계

---

## 핵심 원칙

- 신규 시스템 개발 최소화
- 기존 DB / UI / Runtime 재사용 우선
- "엔진 개발" 금지, "운영 연결"만 수행
- Runtime은 기존 Safe 구조 위에 얹는다

---

## Source of Truth (변경 금지)

| 영역 | Source of Truth | Runtime 역할 |
|---|---|---|
| 사업장 | factories | 읽기 |
| 설비 | equipment_assets | 읽기 |
| 일정 | work_schedules | 단방향 sync |
| 점검항목 | inspection_set_items | 읽기 |
| 서식 | document_forms | 읽기 |
| 인력 | safety_personnel | 읽기 |
| 자격 | fix_qualification_master | 읽기 |

---

## 신규 개발 금지 목록

| 금지 | 이유 |
|---|---|
| 새 Schedule 시스템 | work_schedules 존재 |
| 새 점검 구조 | inspection_sets 존재 |
| 새 문서 구조 | document_forms 존재 |
| 새 Assignment 구조 | runtime_obligation_assignment 존재 |
| 새 인력 구조 | safety_personnel 존재 |
| 새 Cockpit | Projection 이미 존재 |
| 새 PDF 엔진 | Projection 구조 재사용 가능 |

---

## 12 Phase 구현 계획

### PHASE 1 — 무료 진단 기존 UI 재사용

새 페이지 생성 금지. 기존 결과 하단에 Candidate Preview 컴포넌트만 추가.

| 표시 | 허용 | 금지 |
|---|---|---|
| 의무명 | O | WHO/WHEN 상세 |
| 위험도 | O | SCHEDULE 상세 |
| 법령명 | O | Assignment Requirement |
| 상태색상 | O | Evidence |

### PHASE 2 — Activation CTA

기존 결과 페이지 하단에 CTA 연결.

```
[무료 PDF 다운로드]  [운영 시작 →]
```

기존 회원가입/결제 흐름 재사용.

### PHASE 3 — 유료 = 기존 Safe 세팅 재사용

새 입력 UI 금지. 기존 factories/equipment/inspection/schedule 입력 화면 재사용.

추가: 저장 완료 후 runtime_candidate 생성 Hook 연결.

### PHASE 4 — Cockpit 기존 홈 재사용

신규 Dashboard 금지. 현재 홈 화면을 Runtime Projection으로 확장.

| Feed | Source |
|---|---|
| overdue | runtime_instance |
| assignment missing | runtime_assignment_requirement |
| evidence missing | runtime_instance_evidence |
| reviewer pending | runtime_review_queue |
| escalation | runtime_escalation_log |

### PHASE 5 — work_schedules 재사용

work_schedules → runtime_schedule 단방향 sync. 수정은 반드시 work_schedules에서만.

### PHASE 6 — inspection_sets 재사용

점검 Runtime 생성 시 inspection_sets/items 직접 연결. 새 checklist 시스템 금지.

### PHASE 7 — Evidence 연결만 수행

document_forms + attachments + runtime_instance_evidence 연결.
점검실행 → 파일업로드 → evidence fulfilled. 신규 문서 시스템 금지.

### PHASE 8 — Assignment 기존 구조 재사용

safety_personnel + runtime_obligation_assignment + fix_qualification_master 연결.
Validation만 수행 (mismatch 표시). 자동 배정 금지.

### PHASE 9 — PDF Projection 기존 엔진 재사용

무료: 기존 요약형 유지.
유료: runtime_schedule 기반 일정/담당조건/증빗요구 추가. 신규 PDF 엔진 금지.

### PHASE 10 — Excel Projection 추가

| 시트 | Source |
|---|---|
| Task | runtime_task |
| Schedule | runtime_schedule |
| Assignment | requirement |
| Evidence | runtime_instance_evidence |
| Risk | runtime_metadata_resolution |

### PHASE 11 — Runtime Feed 강화

현재 홈 Feed에 overdue/증빗누락/reviewer backlog/assignment missing/qualification mismatch 추가.

### PHASE 12 — Virtual Runtime으로 검증

기존 Virtual World 재사용. Assignment/Evidence/Feed/PDF/Excel/Escalation 정상 동작 검증.

---

## 핵심 구현 원칙

**Runtime은 기존 시스템을 대체하지 않는다.**

Runtime은 기존 운영 데이터를 연결하고, 상태화하고, 투영한다.

## 현재 부족한 것

엔진 ❌ / 구조 ❌ / DB ❌

부족한 것: **연결 / Projection / 운영 UX**

## 최종 목표

무료진단 → Preview → 운영시작 → Cockpit → Assignment → Evidence → Feed → Projection

이 흐름을 **기존 자산 80~90% 재사용**으로 완성.
