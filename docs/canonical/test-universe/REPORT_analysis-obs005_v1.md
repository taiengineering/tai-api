---
wo: WO-ANALYSIS-005
class: records
type: report
scope: canonical
project: test-universe
title: Obs-005 category 결정 경로 추적
version: 1
status: active
owner: taiwang
---

# REPORT — WO-ANALYSIS-005 Obs-005 Analysis (category 결정 경로)

> 핵심 질문: "선임 어휘 의무가 왜 신고 category로 결정됐는가"(사실 추적). "category가 틀렸다"(당위)는 다루지 않는다. 수정·CHG 없음.
> Input: Obs-005 재확인(VALID, beaa84c0), Observation Inventory(6be576e4).

## 1. Observation
Obs-005 — 선임/지정 성격 어휘 의무가 category=신고(report)에 위치(VALID, 235건, 제조·건축·건설).

## 2. category 결정 경로 (코드, services/anonymous_factory_service.py)
```text
draft_slot(section=THEN_ACTION).family_name   (조문의 실제 행위 어휘)
   ↓ _ACTION_TO_TASK[family_name]  예: REPORT_FAMILY → REPORT_TASK_CANDIDATE
   ↓ _bucket_for_task_type(task_type)  예: REPORT → ("report","신고")
category = 신고
```
- 즉 category는 **의무명(제목)의 어휘가 아니라 조문의 실제 행위(THEN_ACTION 동사)**로 결정된다.

## 3. Evidence

### E1 — 지목 항목의 조문 제목이 대부분 '선임신고/선임 보고'
- 위험물안전관리법 시행규칙 §53 "안전관리자의 **선임신고** 등" → THEN_ACTION `REPORT_FAMILY / 제출하여야 한다`.
- 화재예방법 시행규칙 §14 "소방안전관리자의 **선임신고** 등".
- 전기안전관리법 시행규칙 "전기안전관리자의 **선임 및 해임신고**" → THEN_ACTION `REPORT_FAMILY / 제출해야 한다`.

### E2 — '순수 선임(제목에 신고 없음)인데 REPORT'로 잡힌 15건도 실제 신고/보고 의무
- "안전관리자 등의 선임 등 **보고**"(제출), "임원 선임의 **보고** 등"(제출), "기계설비유지관리자 선임 등"(**신고하여야 한다**), "승강기 안전관리자의 선임 또는 변경 **통보**"(제출), "검사대상기기관리자의 선임"(**신고하여야 한다**).
- 제목엔 '신고'가 없지만 조문 행위(raw_token)가 신고/제출/통보 → category=신고가 조문 행위와 일치.

### E3 — 선임 조문의 THEN_ACTION 실제 동사 분포 (정량)
```text
제출해야/하여야 한다  68     ┐
신고하여야/해야 한다  30     │ 신고 성격 동사 ≈ 120건 → category=신고 정상
통보해야/하여야 한다  18     │
보고해야/하여야 한다   4     ┘
────────────────────────
선임하여야/해야/할수있다 62   → 선임 성격 동사 (APPOINT_FAMILY 32) → category=선임
확인해야/하여야 한다   27     → 점검/확인 성격
```
- category 결정이 동사를 정확히 반영: '제출/신고/통보'는 신고로, '선임'은 선임으로.

## 4. Root Cause
- **Obs-005는 category 오분류가 아니다.** category는 조문의 실제 행위(THEN_ACTION 동사)를 정확히 반영하며, 지목된 235건의 대부분은 실제 신고·보고 성격 의무("선임신고", "선임 등 보고")다.
- "선임"이라는 어휘가 제목에 있어도, 조문이 규정하는 행위가 "선임 사실을 신고/보고/통보하라"이면 신고 category가 정확하다.
- 남는 미묘한 계층: 한 조문이 복수 THEN_ACTION(선임 + 신고)을 가질 때 선임 성격과 신고 성격이 각각 파싱될 수 있다(예: 전기안전관리자 조문의 REPORT_FAMILY + MANDATORY_FAMILY). 이는 오분류가 아니라 **복합 의무의 다중 파싱**.
- **Root Cause 판정: 정상 동작(오분류 아님).** category 결정 메커니즘은 조문 행위를 올바르게 반영한다. Obs-004와 같은 '존재 ≠ 오류' 패턴.

## 5. Impact
- category 결정 로직: 정상(무영향).
- 표시: '선임'이라는 제목 어휘와 '신고' category가 병존해 사람 눈에 어색해 보일 수 있으나, 조문 행위 기준으로는 정확. 이는 표시/UX 인지 문제이지 분류 오류 아님.

## 6. Conclusion
- Obs-005 = **정상 동작 확인 (category 오분류 아님).** category는 조문 THEN_ACTION 동사를 정확 반영, 지목 235건 대부분 실제 신고·보고 의무.
- **CHG 불필요(현재 Evidence 기준).** '선임 어휘 + 신고 category 병존'이 사용자에게 혼란을 준다면 그것은 표시/UX 개선 논의이지 분류 수정이 아니다 — 별도 판단.
- 당위 판단('category가 틀렸다') 하지 않음. 조문 행위와 category의 일치를 사실로 확인.
- 완료: Root Cause(정상) 확정 · Evidence(E1~E3) · 수정 0 · CHG 0.

## 상태
```text
Obs-003 : RESOLVED
Obs-001 : RESOLVED
Obs-002 : RESOLVED
Obs-004 : ANALYZED (Metadata) → CHG(별도 커버리지 프로젝트)
Obs-005 : ANALYZED — 정상 동작(오분류 아님), CHG 불필요
Obs-006 : VALID → Analysis 대상
```
