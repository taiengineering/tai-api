---
wo: WO-REVIEW-008
class: records
type: report
scope: canonical
project: test-universe
title: Observation Revalidation Obs-006
version: 1
status: active
owner: taiwang
---

# REPORT — WO-REVIEW-008 Observation Revalidation (Obs-006)

> Review only. 병합 반영 엔진(after_obs002)에서 Obs-006 실재를 §12.9 전량 정독으로 재확인. 등장 사실·위치만(§12.6). 원인·분리 정오 판단·Analysis·CHG 없음.
> Input: after_obs002(112, 병합 반영), Observation Inventory(6be576e4), REPORT_review-003-semantic(8869996a).

## 판정: Case A — Obs-006 유지 (새 엔진에서도 실재)

## 1. 존재 여부
- 같은 사안(같은 obligation_summary)이 모법과 시행령/시행규칙 등 다른 층위 법령으로 나뉘어 각각 등장함을 정독 확인. 131건.
- §12.6 준수: '분리가 잘못됐다/합쳐야 한다'는 판단 안 함. 법과 시행규칙이 각기 다른 의무를 규정하는 정상 케이스일 수 있음 — 정오는 Analysis 몫. 본 WO는 등장 사실+위치만.

## 2. 범위 (정독 확인)
```text
같은 사안이 법/시행령/시행규칙으로 분리 등장:
  제조 46/46 · 건축 29/29 · 건설 27/27 · 특수 0/10
  총 131건, 미관측 10 profile(특수 전부)
```

## 3. 영향
- 영향도: Medium(광범위 3 sector이나 중복성 성격). Confidence: 등장 사실 High.

## 4. 증거 위치 (§12.9, profile별 @pos)
- obs006_evidence_log.txt (365줄): profile마다 [의무] base법령 tiers=[법 층위들] @pos + READ COMPLETE. 예:
  - PF-0001: [안전보건관리규정의 작성] 산업안전보건법 tiers=[법, 시행규칙] @pos [9, 8].
  - PF-0002~: 동일 패턴 반복.
- 원본: after_obs002/SNAP-*.json 의 *_required 배열.

## 5. 다른 Observation (등록만 — §12.6)
- 정독 중 Obs-005(선임성격 report 위치) 재관측. 본 WO 판단 아님.

## 결론
- Obs-006 = **유지(Observation 유효)**. 병합 반영 새 엔진에서 실재·범위 전량 정독 확인.
- 주의: '분리가 오류다'는 판단하지 않음. 같은 사안명이 법/시행규칙에 나뉘어 등장한 사실만 확정. 정오(각 층위가 별도 의무인지 vs 중복 표시인지)는 Analysis 몫.

## 상태 (전 Observation 재확인 완료)
```text
Obs-003 : RESOLVED (측정)
Obs-001 : RESOLVED (기준선)
Obs-002 : RESOLVED (조립 Merge)
Obs-004 : ANALYZED (Metadata) → CHG(별도 커버리지 프로젝트)
Obs-005 : VALID → Analysis 대상
Obs-006 : VALID → Analysis 대상
```
