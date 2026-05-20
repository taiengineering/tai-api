# TAI Runtime UI Strategy + 법령진단 Runtime 연결 — 구현 가이드

## 작성일: 2026-05-20
## 상태: 전략 확정 + 구현 가이드 생성

---

## 전체 Runtime Pipeline 현황 (실제 DB 기준)

| 계층 | 건수 | 역할 |
|---|---|---|
| 법령 | 768개 | Deterministic Legal Compiler 입력 |
| Applicability | 29,096 | 사업장별 법령 매칭 결과 |
| Metadata Resolution | 3,395 | WHO/HOW/WHEN/SCHEDULE 복원 |
| Assignment Requirement | 1,724 | 자격/기관/인원 요구조건 |
| Runtime Task | 339 (200 compiler + 59 bridge + 80 virtual) | 운영 작업 |
| Runtime Schedule | 339 | 반복 일정 |
| Runtime Instance | 339 | 실행 건 |
| Runtime Evidence | 342 | 증빗 요구 |
| Runtime Audit | 388 | 상태 변화 기록 |
| Escalation | 22 | 에스컨레이션 |
| Document Forms | 260 | 법정 서식 |
| Real Factories | 332 | 실제 사업장 |
| Virtual Factories | 10 | 시뮬레이션 |

---

## PHASE 1 — 무료 진단 Runtime Boundary

### 무료 출력 구조

| 출력 | 포함 | 제외 |
|---|---|---|
| **Candidate Preview** | 의무 목록 (이름만) | WHO/WHEN/HOW/SCHEDULE 상세 |
| **리스크 등급** | HIGH/MEDIUM/LOW | 수치 점수 |
| **적용 법령** | 법령명 + 조문번호 | 조문 상세 텍스트 |
| **PDF 보고서** | 의사결정용 요약 | 운영 계획서 |

### 무료 PDF 구조

```
1. 사업장 개요 (업종/인원/설비)
2. 적용 법령 목록 (MATCH 건수)
3. 주요 의무 Preview (상위 10건)
4. 리스크 등급 (HIGH/MEDIUM/LOW)
5. "운영을 시작하시겠습니까?" CTA
```

---

## PHASE 2 — 유료 진단 = Runtime Activation

### 유료 입력 = Safe 세팅 입력

| 입력 | Source Table | 건수 |
|---|---|---|
| 사업장 | factories | 332 |
| 설비 | equipment_assets | 1,285 |
| 공정 | factory_process | 9 |
| 인력 | safety_personnel | 15 (virtual) |
| 일정 | work_schedules | 59 |
| 점검세트 | inspection_sets | 324 |

### 유료 결과 = Runtime 생성

```
factories (입력)
  ↓ 법령엔진 실행
facility_applicability (MATCH/POSSIBLE/AMBIGUOUS)
  ↓ Runtime Metadata Resolution
runtime_candidate (상세 WHO/HOW/WHEN/SCHEDULE)
  ↓ 사람 승인 (Activation)
runtime_task → runtime_schedule → runtime_instance
  ↓
evidence requirement → cockpit projection
```

---

## PHASE 3 — Runtime Cockpit Web Projection

| 영역 | 내용 | 데이터 소스 |
|---|---|---|
| **오늘 상태** | overdue / pending / due today | runtime_instance |
| **Assignment** | 담당자 필요 / 자격 불일치 | runtime_assignment_requirement |
| **Schedule** | 이번 주 일정 / 반복주기 | runtime_schedule |
| **Evidence** | 증빗 누락 / 검토 대기 | runtime_instance_evidence |
| **Risk** | 위험도 점수 / 추이 | runtime health score |
| **Candidate** | 미승인 의무 목록 | runtime_candidate |

---

## PHASE 4 — PDF Projection

### 무료 PDF (의사결정용)

표지 / 요약 / 적용법령 / 주요의무(10건) / 리스크등급 / CTA

### 유료 PDF (운영 계획서)

사업장상세 / Candidate전체 / 일정표 / 담당조건 / 증빗요구 / 리스크상세 / 문서체크리스트

---

## PHASE 5 — Excel Projection

| 시트 | 내용 | Source |
|---|---|---|
| Task | 의무 목록 (WHO/HOW/WHEN) | runtime_task |
| Schedule | 반복주기 + 다음 실행일 | runtime_schedule |
| Assignment | 담당 자격 조건 + 인원수 | runtime_assignment_requirement |
| Evidence | 증빗 유형 + 필수여부 | runtime_instance_evidence |
| Risk | 위험도 + 법적 근거 | runtime_metadata_resolution |

---

## PHASE 6 — Activation CTA

```
무료 진단 결과 페이지
  ↓
"이 사업장에 N개 법적 의무가 있습니다" (Candidate Preview)
  ↓
[리스크: HIGH]
  ↓
[무료 PDF 다운로드]  [운영 시작 →]
  ↓ ("운영 시작" 클릭)
유료 세팅 입력 → Runtime Activation → Cockpit 진입
```

---

## PHASE 7 — Runtime Input Validation

| 입력 | 건수 | Runtime 연결 | 상태 |
|---|---|---|---|
| factories | 332 | → CONDITION/THRESHOLD | ✅ |
| equipment_assets | 1,285 | → CONDITION | ✅ |
| work_schedules | 59 | → runtime_schedule | ✅ |
| inspection_sets | 324 | → HOW/Evidence | ✅ |
| inspection_set_items | 5,184 | → Evidence type | ✅ |
| safety_personnel | 15 (virtual) | → Assignment | ⚠️ 데이터 투입 필요 |
| document_forms | 260 | → Evidence requirement | ✅ |

---

## PHASE 8 — Feed 기반 Runtime 홈

```
[오늘의 운영 상태]

🔴 위험성평가 overdue (3건)
🟡 증빗 누락 (37건)
🟠 담당자 필요 (11건)
🔵 검토 대기 (5건)
✅ 완료 (26건)

[최근 이벤트]
• 김안전님이 사출공장 B 정기점검 완료 (2시간 전)
• 소방설비 점검 증빗 반려됨 (yesterday)
• 안전관리자 자격 만료 경고 (3일 전)
```

---

## PHASE 9 — 문서/서식 Runtime 연결

| 연결 | 현재 | 필요 |
|---|---|---|
| runtime_task → document_forms | 68건 bindable | ✅ |
| doc_rule_mapping | 227건 PENDING | 🔴 검토 필요 |
| obligation_form_mapping | 11건만 | 🟠 확장 필요 |
| evidence → attachments | 0건 | 🟡 upload flow 필요 |

---

## PHASE 10 — End-to-End

### 무료

주소/업종/인원 입력 → 법령매칭 → Preview → 리스크 → PDF → CTA

### 유료

세팅입력 → 법령엔진 → Candidate → Activation → Task+Schedule+Instance → Evidence → Cockpit → PDF/Excel → 지속운영

---

## 운영 철학

| 철학 | 의미 |
|---|---|
| **Human Governance** | 사람이 최종 판단. TAI는 책임 대신 안 짐 |
| **Runtime State** | 업무 = 상태. 모든 것이 상태 전이 |
| **Deterministic** | 법령 구조 기반. LLM 추론 없음 |
| **Operational Continuity** | 1회 진단이 아니라 지속 운영 |
| **Runtime Projection** | 문서는 결과가 아니라 상태 투영 |
| **Optional Adoption** | 엑셀 운영도 가능. SaaS 강요 안 함 |

---

## P0 구현 작업

| 우선순위 | 작업 | 담당 |
|---|---|---|
| **P0** | 무료 진단에 Candidate Preview 컴포넌트 추가 | Frontend |
| **P0** | Activation CTA ("운영 시작") 버튼 + 유료 진입 흐름 | Frontend + API |
| **P0** | 유료 결과 = Runtime Cockpit 형태 웹 페이지 | Frontend |
| **P0** | 유료 PDF = 운영 계획서 (Schedule + Assignment + Evidence) | API |
| **P1** | Excel 출력 (5시트: Task/Schedule/Assignment/Evidence/Risk) | API |
| **P1** | Feed 기반 홈 화면 (이벤트 흐름) | Frontend |
| **P1** | doc_rule_mapping 227건 PENDING 검토 | Admin |
| **P2** | safety_personnel 실제 인력 데이터 투입 | Admin |
| **P2** | attachments upload flow 연결 | API + Frontend |
