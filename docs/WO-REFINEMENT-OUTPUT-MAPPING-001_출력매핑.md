# WO-REFINEMENT-OUTPUT-MAPPING-001 — 출력 매핑

**작성일:** 2026-06-26 | **상태:** 완료 (Layer ⑤ Refinement, 출력 매핑 + 커버리지 실측)
**선행:** LEGAL-TRACE-001, TRACE-CLEANUP-001
**원칙:** 새 화면 0 · 새 생성 0 · 없는 값은 정직하게 미공급 · Data Contract/Boundary 무변경

> 이 WO는 새 출력 시스템을 만들지 않는다. 기존 두 화면(진단결과 HTML, SaaS 점검항목관리)가
> 요구하는 필드를 현재 엔진/Trace 출력과 **1:1 대응**시키고, 없는 값은 미공급으로 남긴다.

---

## Boundary Check

```
Applicability 내부 작업인가?   NO
Boundary 변경 필요한가?        NO
Data Contract 변경 필요한가?   NO
Breaking Change인가?           NO
→ Layer ⑤ 내부 매핑 작업. 읽기 전용 조사 + 매핑표. 새 HTML/화면/생성 0.
```

---

## TASK-001 — 진단결과 HTML 출력필드 (실측)

소스: `routers/diagnosis_report.py` v2.0.0 + `templates/diagnosis_report_paid.html` (Gotenberg).
데이터 출처: `anonymous_diagnosis_results.full_result.{rules_table|obligations}`.

**per-의무 렌더 필드 (rule 테이블 행 — 매핑 대상):**
```
obligation_type(→ 선임/점검/조치/보고/신고 배지)  law_name(법령)  law_article(조항)
obligation_summary | remarks(내용)  inspection_cycle(주기)  submit_org_label(제출기관)
cycle_base_guide(기준점, 부록B)  qualification_required(자격요건, 부록C)  penalty_summary(벌칙)
```

**리포트 레벨 필드 (입력/집계 — trace 대상 아님):**
```
company_name·sector_label·business_no·ceo_name·address·industry_type·worker_count·area·floors
total·appointment_count·inspection_count·action_count·report_notify_count·law_count·risk_level
max_penalty_text·csia_applicable·top5_risks·recommended_plan_*  → input_data + 집계에서 공급
```

---

## TASK-002 — SaaS 점검항목관리 출력필드 (실측)

소스: `routers/inspection_setup.py` v1.2.0 (`/inspection-checklist/prefill`·`/setup`) + 테이블 `inspection_set_items`.
**Prefill 출처: `inspection_master` (설비 표준코드 `equipment_std` 기반 점검 템플릿).**

```
item_name  legal_basis(법적근거)  cycle(주기)  check_type(BOOLEAN 등)  check_method(점검방법)
pass_description(합격기준)  fail_action(불합격조치)  risk_type  threshold_value  unit  is_mandatory/is_required
```

> ★ 구조 실측: `inspection_master` 1,246행 / legal_basis(텍스트) 1,026행 / **법령 FK 컬럼 0개**
> (clause_id·source_clause_id·obligation_id·semantic_clause_id·rule_id 전무).
> → SaaS 점검항목관리는 **법령 trace 엔진과 구조적으로 분리**도어 있다. 연결은 legal_basis 텍스트뿐.

---

## TASK-003 / 004 — Output Mapping (1:1) + 누락 분류

### A. 진단결과 HTML ← 현재 Trace/Adapter 출력

```
HTML 필드            ← 공급원                                 판정
───────────────────────────────────────────────────
law_name             ← traced WHY / law_master.law_name        ✓ 있음(직접)
law_article          ← law_article.article_no + article_title  ✓ 있음(직접)
obligation_summary   ← adapter.title / article_title           ✓ 있음(직접)
obligation_type      ← adapter.category / rule_type (매핑 필요) ✓ 있음(매핑)
inspection_cycle     ← traced_cycle (정제 후 15/171)            △ 부분
submit_org_label     ← traced_recipient (12/171, 신고 의무)     △ 부분
remarks              ← (없음)                                   ✗ 미공급
cycle_base_guide     ← (없음, 이전점검일 기준=SaaS 스耀耀)       ✗ 미공급
qualification_required← (없음, 별표 필요)                        ✗ 미공급
penalty_summary      ← (없음, 과태료 필요)                       ✗ 미공급
```

### B. SaaS 점검항목관리 ← 현재 Trace 출력

```
SaaS 필드          ← 공급원                              판정
────────────────────────────────────────
legal_basis        ← traced WHY (law_name+article)        ✓ 있음(교차李李)
is_mandatory       ← 법적의무=필수 (기본 true)            ✓ 있음
item_name          ← adapter.title (WHAT은 미해결)        △ 부분
cycle              ← traced_cycle (15/171)                △ 부분
risk_type          ← adapter.risk_level                   △ 부분
check_type         ← (없음, 점검 템플릿 속성)             ✗ 미공급
check_method       ← (없음, HOW 미해결)                   ✗ 미공급
pass_description   ← (없음, 합격기준=점검 실행 detail)     ✗ 미공급
fail_action        ← (없음, 불합격조치)                   ✗ 미공급
threshold_value    ← (없음, 설비 기준값)                  ✗ 미공급
unit               ← (없음)                               ✗ 미공급
```

> 분류는 "있음→직접 매핑" 또는 "없음→미공급" 두 가지로만. 없는 값은 생성하지 않았다.

---

## TASK-005 — 미공급 원인 (Layer 기준, 해결하지 않음)

```
remarks              → Check Engine 미공급 (요약 외 비고 필드 없음)
cycle_base_guide     → 도메인 외 (SaaS 스耀耀 = 이전점검일 기준, 법령 trace 아님)
qualification_required→ 상위 법령 미적재 (law_appendix 1행 = 별표 없음)
penalty_summary      → master_rule_v2 0건 (과태료 구조화 미적재)
inspection_cycle 부분 → semantic_clause cycle_text 부분만 분해 (15/171)
submit_org 부분      → recipient 신고 의무에만 존재 (12/171)
check_type/method    → Legal Trace 미공급 (HOW 0%, 점검 실행 detail 아님)
pass_description     → 도메인 외 (점검 합격기준 = inspection_master 고유)
fail_action          → 도메인 외 (불합격조치 = inspection_master 고유)
threshold/unit       → master_rule_v2 scope 0건 + 설비 기준값 도메인
```

**구조적 원인:** SaaS 점검항목관리는 `inspection_master`(설비 템플릿)가 공급원이며 법령엔진과 FK 0.
법령 trace는 **의무 레벨(WHO/WHY/조문)**을 생산하지, **설비 점검 실행 항목(합격기준/조치/기준값)**을 생산하지 않는다.

---

## TASK-006 — Output Coverage (실측)

```
[진단결과 HTML] per-의무 필드 9개
  있음(직접/매핑)  4   law_name · law_article · obligation_summary · obligation_type
  부분             2   inspection_cycle · submit_org_label
  미공급           3   cycle_base_guide · qualification_required · penalty_summary
  → 핵심 매핑 Coverage 4/9 완전 + 2/9 부분  (remarks는 summary로 대체 가능)
  → 리포트 레벨(회사·집계)은 input_data/집계에서 별도 공급 (trace 무관)

[SaaS 점검항목관리] 필드 11개
  있음             2   legal_basis · is_mandatory
  부분             3   item_name · cycle · risk_type
  미공급           6   check_type · check_method · pass_description · fail_action · threshold · unit
  → trace 직결 Coverage 2/11 + 부분 3/11
  → 구조적으로 별도 파이프(inspection_master). trace는 이 페이지의 공급원이 아님.
```

---

## TASK-007 — 171건 실제 출력 검증

```
[HTML 진단결과]
  출력 성공      171/171 (law_name·law_article·obligation_summary·obligation_type 100%)
  Broken Mapping 0    (skeleton 100%, 끊김 없음)
  NULL/부분      inspection_cycle 156 NULL(15 값) · submit_org 159 NULL(12 값)
  미공급 필드    cycle_base_guide·qualification_required·penalty_summary = 171 전건 공란
  → 진단결과 HTML은 171건 출력 가능 (핵심 4필드 완전, 3필드 공란 정직 표기)

[SaaS 점검항목관리]
  171 obligation → inspection_set_items 직접 출력 불가
  사유: 키 불일치(source_clause_id vs equipment_std) + 핵심 필드 도메인 외 + 법령 FK 0
  → trace는 이 페이지를 공급하지 않음. legal_basis 교차李李만 가능.
```

---

## TASK-008 — Refinement Layer 책임 (명시)

```
Refinement는 표현만 한다.
  - 새 법령 생성 안 함 · 새 증빙 생성 안 함 · 새 6W 생성 안 함.
  - Check Layer(Legal Trace) 결과를 기존 출력 형식으로만 변환.
  - 미공급 필드는 공란/—로 정직하게 표기. 채우지 않는다.
```

---

## 성공 기준 충족

```
✓ 진단결과 HTML 요구 필드 ↔ 현재 Trace 결과 1:1 대응표 작성 (TASK-003 A)
✓ SaaS 점검항목관리 요구 필드 ↔ 현재 Trace 결과 1:1 대응표 작성 (TASK-003 B)
✓ 없는 값은 정직하게 미공급 (HTML 3 · SaaS 6) + Layer별 원인 기록
✓ Data Contract 변경 0 · Boundary 변경 0 · 새 화면 개발 0 · 새 생성 0
```

---

## 결론 — 연결점의 실제 모습

```
입력 → Applicability → Glue → Adapter → Check Engine → Check Layer(Legal Trace) → Refinement
  └─→ [진단결과 HTML]  : trace 출력으로 공급 가능 (핵심 4필드 완전, cycle/recipient 부분,
                          qualification/penalty/cycle_base는 상위 미적재로 공란)
  └─→ [SaaS 점검항목관리]: 구조적으로 별도 파이프(inspection_master 설비 템플릿).
                          trace는 공급원이 아님. legal_basis 텍스트 교차李李만 가능.
                          핵심 실행 필드(합격기준/조치/기준값/점검방법)는 법령 trace 도메인 밖.
```

**정직한 결론:** "마지막 연결점"은 **진단결과 HTML**에 대해 성립한다(부분 커버리지).
**SaaS 점검항목관리**는 법령 trace가 흘러드는 구조가 아니다 — 별도 설비 템플릿 시스템이며,
trace로 그 페이지를 채우려면 없는 값을 생성해야 하므로 이 WO의 금지사항에 걸린다.
연결을 원한다면 별도 결정 필요: (a) legal_basis 교차李李 수준 연결, 또는
(b) 상위 적재(별표·penalty·HOW 분해) 후 의무→점검항목 매핑 설계 (GPT/Architecture 경계, 별도 WO).

---

*WO-REFINEMENT-OUTPUT-MAPPING-001 완료. 만든 게 아니라 연결하고, 안 닿는 곳은 정직하게 표시했다.*
*HTML 핵심 4/9 완전·2/9 부분 · SaaS는 구조 분리 확인 · 생성 0 · 계약 무변경.*
