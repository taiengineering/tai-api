---
wo: WO-REVIEW-004
class: records
type: report
scope: canonical
project: test-universe
title: Observation Revalidation Obs-002
version: 1
status: active
owner: taiwang
---

# REPORT — WO-REVIEW-004 Observation Revalidation (Obs-002)

> Review only. 새 기준선(before_clean, 안정 엔진 산물)에서 Obs-002 실재 재확인. 집계가 아니라 의무 전문 정독. 원인·Analysis·CHG 없음.
> Input: before_clean(신규 정식 기준선), before_clean2(검증본), Observation Inventory(6be576e4), REPORT_review-003-semantic_v1.

## 판정: Case A — Obs-002 유지 (새 기준선에서도 실재)

## 1. 존재 여부
- 새 기준선 정독 결과, 동일 (category, 법령, 의무 텍스트)가 한 profile 내에서 2회 이상 반복됨을 실제 텍스트로 확인.
- Obs-001과 달리 오염 기준선의 산물이 아님 — 안정 새 기준선(편차 10개가 높은값으로 안정: PF-0020=107 등)에서 그대로 재현.

## 2. 범위
- **112/112 전 profile.** 제조 46/46 · 건축 29/29 · 건설 27/27 · 특수 10/10. 예외 없음.
- 최대 다중도: 건축 x4 · 제조 x3 · 건설 x3 · 특수 x2.
- profile당 초과중복 항목수: 2 ~ 21.

## 3. 영향
- 중복이 applicable_count에 포함되어 계상됨(관측). 예: PF-0019 full_count(중복 포함)=107 = applicable_count=107. 의무 개수가 중복만큼 부풀려진 상태로 카운트됨.
- 영향도: High (전량, 계수 신뢰성).

## 4. 증거 위치 (정독 확인)
- MANUFACTURING PF-0001: [report] 중대재해 처벌법 시행령 | 안전보건교육의 실시 등 **x3**; [action] 안전보건교육규정 | 교육방법 x2; [action] 산안법 시행규칙 | 안전보건관리규정의 작성 x2.
- BUILDING PF-0019: [report] 소방시설 자체점검 결과의 조치 **x4**; [action] NFPC 203 수신기 x3, NFPC 103 헤드 x3, NFPC 301 피난기구 x3; [action] KEC 231.5 x2; 외 15종 다중.
- CONSTRUCTION PF-0028: [report] 건설기술진흥법 시행령 안전관리계획의 수립 **x3**, 안전보건교육의 실시 x3.
- SPECIAL PF-0037: [inspection] 장애인복지법 시행규칙 시설 설치·운영신고 x2; [action] 안전보건교육규정 교육방법 x2.
- 원본: before_clean/SNAP-*.json 의 partialResult.*_required 배열.

## 5. 다른 Observation (등록만 — 몰입 금지)
- 정독 중 Obs-005(선임류가 report에), Obs-006(법+시행규칙 분리) 재관측됨. 본 WO에서 판단·분석하지 않음. 각 Observation Revalidation WO에서 다룸.

## 결론
- Obs-002 = **유지(Observation 유효)**. 새 기준선에서 실재 확인.
- 다음 단계(Analysis)는 별도 WO. 본 WO는 실재 확인까지 — 원인·Analysis 없음.

## 상태
```text
Obs-003 : RESOLVED
Obs-001 : RESOLVED
Obs-002 : VALID (새 기준선 재확인 완료) → Analysis 대상
Obs-004 : OPEN (재확인 필요)
Obs-005 : OPEN (재확인 필요)
Obs-006 : OPEN (재확인 필요)
```
