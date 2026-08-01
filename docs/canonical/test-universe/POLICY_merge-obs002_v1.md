---
wo: WO-CHG-003
class: records
type: policy
scope: canonical
project: test-universe
title: Obs-002 Part→Article Presentation Merge Policy
version: 1
status: active
owner: taiwang
---

# MERGE POLICY — Obs-002 Part → Article Presentation

> 목적: Part 단위 결과를 Article 단위 Presentation으로 어떻게 표현할지 정의한다. "중복 제거"가 아니라 "표현 정의". 병합이 의미를 보존함이 Evidence로 확인될 때만 적용한다.
> Input: Root Cause(765c6f70), 중복 그룹 실측(PF-0019 16그룹 전량 관측).

## 1. 관측 Evidence (PF-0019 16 중복 그룹 전량)
- 모든 중복 그룹에서 `inspection_cycle_value`·`inspection_cycle_unit_code`·`condition_code`·`condition_value` **부재**. → 병합 시 주기·조건 정보 손실 없음.
- 그룹 내 항목 차이는 두 가지뿐:
  1. `rule_id` — runtime UUID(무의미, 저장 안 됨).
  2. `then_action_token` 표현 변이 — 예: '선임하여야 한다'/'선임할 수 있다'(화재예방법 24), '설치해야 한다'/'설치할 것'(NFPC 203 감지기), '보고해야'/'통보해야'/'제출해야'(자체점검 x4). 동일 의무의 문구 변형.
- 경계 사례: '소방시설 설치 및 관리에 관한 법률 / 12'에서 [action]관리(MANAGE) + [report]통보(REPORT)가 공존 — **category·obligation_type이 다른 별개 의무.** 병합 금지 대상.

## 2. Article grouping 기준 (병합 키)
```text
key = (law_name, law_article, obligation_summary, category)
```
- category를 키에 포함 → 경계 사례(같은 조문·다른 category, 예: 관리 vs 통보)는 **자동으로 분리 유지**된다.
- 같은 key를 가진 2개 이상 rule만 하나로 표현한다.

## 3. 표시 기준 (대표 rule 선정)
- 대표 = 그룹에서 **then_action_token 정보가 있는 첫 항목**(없으면 첫 항목). 표시값(law_name, law_article, obligation_summary, category, obligation_type, source_action_family, rule_type)은 대표를 따른다.
- 이 값들은 그룹 내 정의상 동일(키에 포함되거나 article에서 파생)하므로 대표 선택이 표시를 바꾸지 않는다.

## 4. cycle 처리
- 관측상 중복 그룹에 cycle 부재. 정책: **그룹 내 cycle 값이 서로 다르면 병합하지 않는다**(안전장치). 동일하거나 모두 부재면 대표값 유지.

## 5. condition 처리
- cycle과 동일. **condition_code/condition_value가 그룹 내 상이하면 병합하지 않는다.** 동일/부재면 대표값 유지.
- (4)+(5): 병합은 cycle·condition이 동일하거나 모두 없을 때만. 다르면 별개로 남긴다 → part 의미(주기·조건 차이) 보존.

## 6. evidence(penalty) 처리
- penalty_summary가 그룹 내 다르면 병합 보류(별개 유지). 관측상 penalty 부재 → 현 데이터에선 대표값 유지.

## 7. part 정보 보존 여부
- rule_id(무의미 UUID)와 then_action_token 문구 변이는 **비의미 정보** → 병합으로 소실돼도 의무의 의미는 보존된다.
- 선택적 보존: 대표 rule에 `merged_count`(병합된 part 수)를 부가할 수 있다(표시 영향 없음, 감사용). 필수는 아님.
- cycle/condition/penalty가 다른 경우는 (4)(5)(6)에 의해 애초에 병합하지 않으므로, part의 의미 있는 차이는 항상 별개 rule로 남는다.

## 8. 병합이 일어나는 위치 (Presentation Layer만)
- 대상: `services/anonymous_factory_service.py` `_compiler_result_to_step1_format`의 조립 단계 — `triggered[bucket]`에 append된 뒤 `rules_table`/`*_required`를 만들기 직전, bucket별 리스트에 grouping 키 기준 병합을 적용.
- 불변: Rule Engine·Applicability 계산·Draft·Query·Law Data. draft/applicability 행 자체는 그대로. 병합은 표시 리스트에서만.

## 9. 적용 조건 (KEEP 게이트)
- 이 정책은 **cycle·condition·penalty가 동일하거나 부재할 때만 병합**한다. 하나라도 다르면 별개 유지.
- 따라서 "part 의미가 사라지는가?"(STEP3)의 답은 **아니오** — 의미 있는 차이(주기·조건·벌칙)는 병합 대상에서 제외되고, 소실되는 것은 UUID와 문구 변형뿐.

## 10. Self Review 결과 (STEP 3)
```text
이 정책으로 part 의미가 사라지는가?
→ 아니오.
  - 주기/조건/벌칙이 다른 part는 병합하지 않음(별개 유지).
  - 병합되는 것은 (law,article,obligation,category)가 완전히 같고
    cycle/condition/penalty도 같은 경우뿐 — 소실은 UUID·문구변형(비의미).
→ STEP4 진행 가능.
```
