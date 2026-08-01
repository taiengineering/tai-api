---
wo: WO-CHG-003
class: records
type: report
scope: canonical
project: test-universe
title: Obs-002 Presentation Merge & E2E
version: 1
status: active
owner: taiwang
---

# REPORT — WO-CHG-003 Obs-002 Presentation Merge Policy & E2E

> 중복 제거가 목적이 아니라 Part→Article Presentation Merge Policy를 Evidence로 정의하고 최소 수정 후 E2E. 병합이 의미를 보존함이 Obs-002 병합 그룹 범위에서 Evidence로 검증되어 KEEP.
> Input: Root Cause(765c6f70), Merge Policy(POLICY_merge-obs002_v1, 84a17621).
> 표현 정정(v1.1): Semantic 검토 범위를 실제 Evidence(Obs-002 병합 그룹)에 정확히 한정. '112 전체 Semantic Review 완료' 같은 넓은 표현을 '112 profile의 Obs-002 병합 그룹 전량 검토'로 교정.

## 판정
**CHG-003 KEEP — Obs-002 병합 검증 PASS.**
112개 profile의 중복 그룹에 대해 병합 전 반복 횟수와 병합 후 대표 위치가 기록됐고, profile별 고유 의무 수가 보존됐다. 단, 이는 전체 의무의 법적 타당성 검증이나 다른 Observation의 해결을 의미하지 않는다.

## STEP 1 — Root Cause 재확인
Report(765c6f70): article→part 분화(정상) · runtime rule 생성(rule_id=applicability UUID) · presentation 축약(law_name/obligation이 article에서) · dedup 없음(triggered append). 새 조사 없음.

## STEP 2 — Merge Policy (84a17621, POLICY_merge-obs002_v1)
- grouping key = (law_name, law_article, obligation_summary, category).
- cycle/condition/penalty가 그룹 내 상이하면 병합하지 않음(의미 보존).
- 대표 = then_action_token 있는 첫 항목. 병합은 Presentation Layer(anonymous_factory_service 조립)에서만.
- 관측 Evidence: PF-0019 16 중복그룹 전량 — cycle/condition 전부 부재, 차이는 rule_id(UUID)+then_action_token 문구변형뿐. 경계: 소방시설법 12 관리(MANAGE)+통보(REPORT) = category 다른 별개 의무.

## STEP 3 — Self Review
"이 정책으로 part 의미가 사라지는가?" → 아니오. 주기/조건/벌칙 다른 part는 병합 제외(별개 유지), 소실은 UUID·문구변형(비의미)뿐.

## STEP 4 — Minimal Change (Presentation Layer 한 곳)
- services/anonymous_factory_service.py: `_merge_presentation_duplicates` 헬퍼 추가 + `triggered` 조립 직후 bucket별 병합 적용(3줄). Rule Engine·Applicability·Draft·Query·Law Data 불변.
- 배포: main a52abcf (Railway auto-deploy). 반영 확인 PF-0019 107→86.

## STEP 5 — After
- before_clean(안정 기준선) 기준 112 전량 실행 → after_obs002 생성(112/112).
- 총 applicable_count: before 4,798 → after 3,711 (감소 1,087).

## STEP 6 — Semantic Review (범위: Obs-002 병합 그룹)
**검토 범위 = 112 profile의 Obs-002 병합 그룹 전량.** (전체 4,798 의무의 법적 의미 정독이 아님 — 아래 '증명하지 않는 것' 참조.)
병합 그룹 대상 안전성 검사 112/112:
- After 신설된 고유의무(=After에만 있는 (cat,law,art,ob)): **0**
- Before 고유의무 소실(=Before에만 있는 (cat,law,art,ob)): **0**
- After 잔존 중복(병합 누락): **0**
- 고유의무 집합(키 기준) Before==After: **112/112**
병합 관점 4문항:
- 병합 대상 의무가 사라졌는가 → 아니오 (고유 키 집합 불변)
- 병합으로 (키 기준) 의미가 달라졌는가 → 아니오 (신설·소실 0)
- 단순 병합인가 → 예 (같은 (cat,law,art,ob)만 x N→x1)
- 잘못 합쳐졌는가 → 아니오 (경계 29건 분리 유지, cycle/cond 다른 것 병합 제외)

## STEP 7 — Evidence (profile별 @pos)
- chg003_evidence_log.txt (1,037줄): profile마다 병합 그룹의 before x N → after x1 과 @after_pos 기록 + READ COMPLETE.
- 경계 사례: 같은 law/article·다른 category 29건 전부 After에 별개 유지.
- 병합 대표에 merged_count 부가: 813건.
- After 총 3,711 = 고유의무(키 기준) 3,711.

## STEP 8 — Regression
- after applicable_count == before 고유의무수(키 기준): **112/112 정확 일치**.
- 병합은 표시 리스트 후처리 → 엔진 판정(applicability/risk) 불변. 판정 대상 집합(고유의무 키) 불변 112/112.

## 이 Report(+로그)가 증명하는 것
- 112 profile 모두에 Obs-002 병합 Evidence 존재.
- 병합 대상 중복이 (키 기준) x N → x1로 축약.
- 병합 후 대표 항목 위치(@after_pos) 추적 가능.
- profile별 병합 전 고유 개수(키 기준) == 병합 후 개수.

## 이 Report(+로그)가 증명하지 않는 것 (범위 밖)
- 4,798개 모든 의무의 법적 의미를 사람이 각각 정독했다는 사실.
- cycle·condition·penalty가 다른 모든 경계 사례가 안전하게 보존됐다는 사실(관측 표본 + 정책 안전장치로 뒷받침되나 전량 정독은 아님).
- 타 도메인 적용(Obs-004)·category 오류(Obs-005)·법/시행령 분리(Obs-006) 등 다른 Observation의 정상 여부.
- 전체 엔진 의미 품질의 PASS.

## Conclusion
- Obs-002 = **RESOLVED (Presentation Merge, KEEP)** — 단, 위 '증명하는 것' 범위에서. 병합이 (키 기준) 의미를 보존함이 Evidence로 검증됨: 고유의무 키 집합 완전 보존, 소실·신설·오병합 0, 경계/의미필드 분리 유지. 소실된 것은 UUID·문구변형(비의미)뿐.
- 첫 실제 코드 수정 CHG(Obs-003/001은 측정 문제였음). Presentation Layer 한 곳 최소 수정으로 완료.

## 상태
```text
Obs-003 : RESOLVED (측정)
Obs-001 : RESOLVED (기준선)
Obs-002 : RESOLVED (Presentation Merge, KEEP — 병합 검증 범위)
Obs-004 : OPEN (재확인 필요)
Obs-005 : OPEN (재확인 필요)
Obs-006 : OPEN (재확인 필요)
```

## 파급 (기록만)
- after_obs002가 병합 반영된 새 상태. 향후 Obs-004/005/006 재확인은 이 병합 반영 엔진 기준으로.
- before_clean(병합 전)은 Obs-002 Before 근거로 보존.
- 주의: Obs-002 KEEP은 '병합 대상의 축약·보존'을 증명할 뿐, 병합 후 남은 의무들의 법적 타당성(타 도메인/category/분리 등)은 각 Observation WO의 몫.
