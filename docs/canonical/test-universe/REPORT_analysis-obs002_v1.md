---
wo: WO-ANALYSIS-003
class: records
type: report
scope: canonical
project: test-universe
title: Obs-002 Analysis (의무 다중 등장)
version: 1
status: active
owner: taiwang
---

# REPORT — WO-ANALYSIS-003 Obs-002 Analysis

> Obs-002(동일 category/law/obligation 다중 등장) 하나만 분석. 원인·영향까지. 수정·구현·CHG·코드변경 없음.
> Input: Observation Inventory(6be576e4), Priority(c78ccf7c), 전량 정독 Evidence(cebc8297).

## 1. Observation
Obs-002 — 한 profile 내에서 동일 (category, 법령, 의무텍스트)가 2회 이상 등장. 전량 정독 확인: 112/112, 최대 x4. 범위 전 sector. 영향 High.

## 2. Evidence (객관적 증거만)

### E1 — 중복 항목은 서로 다른 rule_id, 같은 law_article
- PF-0001 '안전보건교육의 실시 등' x3 = rule_id bdec4d90 / 9287b84b / 68345136 (모두 다름), law_article 전부 '6', law_name·obligation·category 동일. (스냅샷 report_required)

### E2 — rule_id는 저장 식별자가 아님 (runtime 생성)
- 3개 rule_id: executable_draft.id(0) · executable_draft.rule_candidate_id(0) · draft_slot.draft_id/part_id(0) · task_candidate.id(0) · diagnosis_candidate/diagnosis_rule_results/rule_candidate(0). 어느 저장 테이블에도 없음.

### E3 — 한 법조문(article)이 여러 part(draft)로 분화
- executable_draft에서 동일 article_id가 최대 35개 draft로 존재(56c8...=35), 전부 part_id가 서로 다름(각 1개). = 한 조문의 정상적 part 분화.

### E4 — 조립 경로가 part 단위 행을 article 단위 표시로 축약 (services/anonymous_factory_service.py)
- `evaluate_single_factory`: draft(part)별로 facility_applicability 행 insert. 같은 article의 여러 part → 여러 행.
- `_compiler_result_to_step1_format`: `applicability`(part 행) 순회 → `_applicability_to_rule_row`로 rule 생성. `rule_id = str(applicability.get("id") or draft_id)` → 행마다 다른 UUID(E1·E2 설명).
- `_applicability_to_rule_row`: `law_name`/`obligation_summary`가 draft_ctx(=article 제목/법령)에서 옴. 다른 part여도 **같은 article이면 law_name·obligation_summary 동일**(E1의 동일 텍스트).
- 조립 시 dedup 없음: `triggered[bucket].append(row)`로 전량 추가. `rules_table`/`*_required` 어디에도 (law, article, obligation) 기준 병합·중복제거 코드가 없음.
- applicability 행은 진단 후 `cleanup_temp_factory`로 삭제 → E2(저장 테이블에 없음)와 일치.

## 3. Root Cause
Evidence 기반 확정:
- 하나의 법조문이 여러 part(draft)로 분화되어 있고(E3, 정상 데이터), 각 part가 개별 facility_applicability 행으로 평가된다(E4).
- 조립 단계(`_applicability_to_rule_row` + `_compiler_result_to_step1_format`)가 각 part 행을 rule로 변환하는데, **표시값(law_name, obligation_summary)은 part가 아니라 article 제목에서 취한다**(E4). 따라서 서로 다른 part가 **동일 (category, law, obligation)로 축약**된다(E1).
- 조립 시 **(law, article, obligation) 기준 dedup이 없어**(E4) 축약된 동일 항목이 그대로 다중 출력된다.
- **Root Cause: part 단위 applicability를 article 단위 표시로 축약하면서 병합(dedup)하지 않는 것.** draft 중복 생성이 아니라 조립측 '표시 축약 + 중복제거 부재'의 결합. 계층 = Query/조립(코드), Rule Data 아님.
- 성격: 표시상 중복(같은 의무가 여러 번 보임). 근본 데이터(part 분화)는 정상.

## 4. Impact
- **조립(anonymous_factory_service)**: `*_required`·`rules_table`에 중복 rule 포함. (직접)
- **Measurement(applicable_count)**: total_applicable = triggered 버킷 길이 합이므로 중복이 계상됨. applicable_count가 실제 고유 의무보다 큼. (영향)
- **Review/사용자 표시**: 같은 의무가 여러 번 노출. (영향)
- **Rule Data/Engine 판정**: 무영향 — draft part 분화·applicability 판정은 정상. 문제는 조립 표시층. (무영향)
- 참고: dedup 시 어떤 part를 대표로 남길지(part별 조건·주기 차이 보존 여부)는 조립 정책 문제 — 본 WO는 원인까지만, 판단 보류.

## 5. Conclusion
- Obs-002 Root Cause = **조립측 part→article 축약 + dedup 부재**(services/anonymous_factory_service.py의 `_applicability_to_rule_row` 표시값 축약 및 `_compiler_result_to_step1_format`의 무병합 append)로 확정.
- draft/applicability 데이터·판정은 정상. 표시·집계층 문제.
- 본 WO는 원인까지. '어떻게 병합(dedup)할 것인가 / 대표 part 선택 정책'은 다음 CHG WO의 책임.
- 완료 상태: Root Cause 확정 · Evidence 문서화 · 수정 0 · CHG 0 · 다른 Observation 분석 0. 다음 CHG WO 실행 가능.
