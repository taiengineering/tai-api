---
wo: WO-REVIEW-001
class: records
type: report
scope: canonical
project: test-universe
title: before_clean 112 Semantic Review
version: 1
status: active
owner: taiwang
---

# REPORT — WO-REVIEW-001 before_clean 112 Semantic Review

> E2E_REVIEW. 엔진 재실행 없음. 입력=before_clean(FROZEN). 수정 없음. 산출: Review Summary · Issue Inventory · Candidate CHG List.

## 0. 중대 전제 정정 (검토 데이터 범위)
- 지금까지의 모든 관측(CHG-001/002, WO-CHG-001-R1, WO-CHG-002-R1)은 **익명 preview(`rules_table` 12개)** 위에서 이뤄졌음.
- 실측 확인: 응답에 `hasFullResult:true`, `message:"일부 결과만 표시됩니다..."`, `rules_table`=`rules_preview`=12(preview). **전체 의무는 `appointment/inspection/action/report_required` 배열에 존재**하며 그 합 = `applicable_count`(112/112 일치 검증).
- 본 Review는 **전량 의무** 기준으로 재수행함.

## 1. Review Summary
- 112 전수 검토(제조 46·건축 29·건설 27·특수 10), 전부 ok=true.
- 의무 규모(applicable_count): 제조 18~23 · 건축 102~107 · 건설 19~24 · 특수 6~7. (risk: 건축·제조·건설 HIGH, 특수 MEDIUM)
- **CHG-002**: False Positive 유지 — 특수시설 10개 전량서도 산업안전 각 2건 커버.
- **CHG-001**: 이전 preview 기반 "전기·승강기=0(누락)" 판정은 **오류**. 전량서 건축물은 전기·승강기 3~7 보유 → "누락=0" 반증. 단 아래 Issue-001의 형태로 **동일 입력 간 3 vs 7 편차** 발견.

## 2. Issue Inventory

### Issue-001 — 동일 입력, 다른 출력 (High)
- Profile: PF-0020·0023·0027(building), PF-0030~0034·0036(construction), PF-0038(special) 등 10개(그룹 내 낮은값).
- Category: 결정성/평가 경로 (Query 또는 Engine 후보, 원인 미확정 = Unknown).
- Evidence: 동일 (site_kind,scale,workers) 그룹 내 applicable_count 편차 —
  building large300{102,107}·medium50{102,107}, construction large450{23,24}·medium75{23,24}·small22{19,20}, special large300{6,7}. manufacturing은 전 그룹 균일.
  건축 사례: PF-0020(medium/50)은 전기·승강기 3, 동일입력 PF-0021 등 13개는 7. 빠진 3개는 공통 [KEC 231.5]·[KEC 351.6]·[KEC 503.2.4].
  PF-0020·0023은 WO-MEASURE-002 `.order` 수정 전 흔들리던 12개에 포함 → `.order`는 same-profile-across-runs만 안정화했고 identical-input 편차는 미해결.
- Confidence: High (before_clean 결정적, 덤프로 재현 확인).

### Issue-002 — 전 profile 의무 중복 (High)
- Profile: 112/112.
- Category: Data 또는 Query (중복 행/DISTINCT 누락 후보).
- Evidence: 모든 profile에 (law,obligation) 중복 존재. 초과중복 상위 — 중대재해 안전보건교육 204건, 산안법 안전보건관리규정 102건, 소방 자체점검 87건, 안전보건교육규정 85건, 중대재해 안전보건관리체계 85건, 산안법 안전관리자 선임 85건 등. `applicable_count`가 중복을 포함 → 계수 신뢰성 저하(Issue-001의 편차와 연관 가능성).
- Confidence: High.

### Issue-003 — 측정 방법론: 익명 preview만 저장 (Info)
- Category: 측정 하네스(Runner) 설계.
- Evidence: Runner가 `/anonymous-diagnosis`(preview 12) 사용. 전체 의무는 `*_required`에 있으나 이전 파싱이 preview만 봄. → 과거 CHG 판정 오염의 근본 원인.
- Confidence: High. (수정 아님 — 향후 Runner가 `*_required` 전량을 스냅샷에 저장하도록 개선 필요.)

## 3. Candidate CHG List
> Evidence + 재현가능 + 영향범위 충족분만 승격. 분류: Display/Data/Query/Engine/Rule/Unknown.

| CHG 후보 | 근거 Issue | 영향 범위 | 분류 | 상태 |
|---|---|---|---|---|
| CHG-C1 동일 입력 결정성 | Issue-001 | building/construction/special 10 profile | **Unknown** (Query/Engine 후보) | 승격 — 최우선 |
| CHG-C2 의무 중복 제거 | Issue-002 | 112/112 | **Data/Query** | 승격 |
| (측정개선) Runner 전량 저장 | Issue-003 | 전 측정 | 측정 하네스 | 별도(비-CHG) |

## 4. 판정 정정 사항
- **WO-CHG-001-R1(CHG-001 False Positive)은 불완전(preview) 데이터 기반이므로 무효.** 전량 재검증 결과 CHG-001의 "전기·승강기 누락(=0)"은 반증되나, 동일입력 편차(Issue-001/CHG-C1)로 재정의됨.
- WO-CHG-002-R1(CHG-002 False Positive)은 전량서도 유지(유효).

## 5. 다음 (수정 아님)
- CHG-C1을 최우선으로 가설검증 Loop(WO-MEASURE-002 방식): 동일 입력 편차의 결정성 원인 확정 후 최소 수정.
- CHG-C2: 중복 원인(assembly/query) 확인 후 최소 수정.
- 단, 어떤 수정도 Evidence+재현+영향범위 확인 후 별도 WO에서. 본 WO는 검토·발굴까지.
