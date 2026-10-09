# 01 — LEG Output Analysis

LEG가 실제로 무엇을 출력하는지 분석한다. (근거: `45cminc/leg` 실제 contracts/docs)

## 1. LEG의 위치와 성격

- `45cminc/leg` = 법령 도메인 시맨틱 런타임 엔진.
- LEG는 federation signal(`ACTION_REQUIRED/WARNING/INFO/HEALTHY`)과 `projection_hint`(category+ref_id)를 emit하며, **human-readable 텍스트를 생성하지 않는다**(PRJ가 재구성). (출처: `contracts/projection.boundary.md`, `contracts/signals/emitted-signals.md`)
- LEG는 도메인 판단 엔진이다(법령 적용·의무 분류·완전성 평가). 이 판단은 LEG의 권한이며 Check로 넘기지 않는다.

## 2. LEG 출력 3계층 (실제)

### (a) Raw engine output — `build_result()`
(출처: `docs/2026-05-30_LEG_output_adapter.md`)

```
{
  engine_version, mode, evaluated_at,
  total_rules_checked, not_applicable_count, applicable_count,
  appointment_required[], inspection_required[], action_required[],
  report_required[],            # notify 포함
  summary{ total, appointment, inspection, action, report, notify },
  not_applicable[]
}
```
각 항목은 rule dict(`rule_id`, `law_name`, `law_article/article_no`, `description`, `obligation_summary` 등).

### (b) UI-ready output — `services/leg_output_adapter.py` `adapt()`
```
{
  engine_version, mode, evaluated_at, adapter_version,
  obligations[],                 # flat, dedup(rule_id)+stable sort
  grouped_by_type{ appointment(선임)/inspection(점검)/action(조치)/report(신고)/notify(보고) },
  grouped_by_law[],
  evidence_refs[]{ law_name, count },
  display_summary{...}, adapter_stats{...}
}
```
어댑터는 판단하지 않는다(applies 재판정·risk_score·법적 문구 생성 금지). 정렬·dedup·label cleanup·grouping만 수행.

### (c) Obligation Standard — 의무 단위 표준
(출처: `docs/2026-05-31_LEG_RESULT_STANDARD_v1.md`)

```json
{
  "obligation_id": "",
  "title": "",
  "who": "", "when": "", "where": "", "what": "", "how": "", "why": "",
  "law_name": "", "article_no": "",
  "condition": { "exists": false, "code": "", "value": "" },
  "evidence": { "chain": [] },
  "metadata": { "source_type": "", "candidate_id": "" },
  "status": { "completeness": 0 }
}
```
`completeness`는 7개 텍스트 필드(law_name, article_no, what, who, when, how, why) 존재 점수를 100점 환산한 **LEG 자가평가**다. 근거(evidence) 실재 여부와는 무관하다.

## 3. 필드 분류 — 구조(structural) vs 도메인 판단(domain judgement)

| 필드 | 분류 | Check 전달 |
|------|------|-----------|
| obligation_id / candidate_id / rule_id | 식별자(ref) | O (claim_ref 원천) |
| evidence.chain[] | 구조적 연결(ref 목록) | O (evidence/chain 원천) |
| law_name + article_no | 식별 보조 | △ (ref 구성 보조용, 의미 아님) |
| who/what/when/where/how/why | 도메인 의미 | **X** |
| condition{exists,code,value} | 도메인 판단 | **X** |
| 의무 유형(appointment/…/notify) | 도메인 분류 | **X** |
| status.completeness | LEG 자가평가 | **X** |
| title, signals, projection_hint | 표현/신호 | **X** |

## 4. Check로 검증 가능한 것

Check는 Claim ↔ Evidence ↔ Evidence Chain의 **연결 상태**만 관측한다. 따라서 LEG 출력에서 검증 가능한 명제는:

> "각 의무(obligation)가 **선언한 근거 체인(evidence.chain)**이 구조적으로 실재·완결되어 있는가?"

이는 LEG의 `completeness` 자가평가와 **독립적**이다. LEG가 completeness=100이라 주장해도, 그 의무가 선언한 evidence가 실제로 첨부/존재하지 않으면 Check는 독립적으로 `BROKEN/REF_MISSING/NOT_ATTACHED`를 관측한다. → **독립적 구조 교차검증**이 통합의 가치.

## 5. 확인된 공백 (TAI가 정의해야 할 부분, 추측 금지로 명시)

- `evidence.chain[]`의 **요소 내부 구조**는 Result Standard에 빈 배열로만 표기되어 있어 확정되지 않음. 체인 요소의 식별자(evidence ref)와 "실제 보유 여부(attached)" 판정은 **TAI 어댑터에서 정의**해야 한다(02 문서).
- `45cminc/leg/src/api/*`는 현재 scaffolding(빈 placeholder). 실제 출력은 Python services(build_result + adapter)에서 생성됨 → 통합 호출 경계는 Python ↔ Check(TS)다(04 문서에서 다룸).
- 따라서 본 분석의 의무/체인 매핑은 **실재하는 Obligation Standard + adapter 출력**에 근거하며, 체인 요소 스키마 확정은 후속 결정 사항으로 표시한다.
