---
wo: WO-ANALYSIS-002
class: records
type: report
scope: canonical
project: test-universe
title: Obs-001 Analysis (동일 입력 다른 출력)
version: 1
status: active
owner: taiwang
---

# REPORT — WO-ANALYSIS-002 Obs-001 Analysis

> Obs-001(동일 입력, 다른 출력) 하나만 분석. 원인·영향까지. 수정·구현·CHG·코드변경 없음.
> Input: Observation Inventory(6be576e4), Priority(c78ccf7c).

## 1. Observation
Obs-001 — 동일 입력, 다른 출력. 관측: 동일 (site_kind,scale,workers) 그룹 내 profile 및 재실행 간 applicable_count 편차. 대상 10 profile: PF-0020·0023·0027(building 102↔107), PF-0030·0031·0032·0033·0036(construction 23↔24), PF-0034(19↔20), PF-0038(special 6↔7). 범위: building·construction·special. 영향: Critical.

## 2. Evidence (객관적 증거만)

### E1 — before_clean 편차 10개는 현재 전부 높은값으로 안정
- 실행결과(순차 워커1 3회 + 병렬 워커6 3회, PF-0020): applicable_count = 107 6회 전부 동일.
- 편차 10개 재실측(now) vs before_clean: 전부 CHANGED —
  PF-0020/0023/0027 102→107, PF-0030/0031/0032/0033/0036 23→24, PF-0034 19→20, PF-0038 6→7. (10/10 상향, 흔들림 없음)

### E2 — before_clean은 PR #122 머지 이전 시점 산물
- before_clean evaluated_at 범위: 2026-07-31 08:10:30 ~ 08:36:57 (112 profile 전체).
- PR #122(‘.order’ 안정 정렬, WO-MEASURE-002) squash merge: 2026-07-31 11:26. main 재배포는 그 이후.
- 즉 before_clean 전체가 머지 前, `fix/measure-orderby-stability` 브랜치 검증배포 시점에 생성됨.

### E3 — 단일 profile 타임라인
- PF-0020: before_clean evaluated_at 08:14:59 → applicable_count 102. after_obs003 evaluated_at 14:23:32 → 107. 현재 → 107 고정.

### E4 — 낮은값에서 누락되던 항목 (정독 관측, WO-REVIEW-003)
- building/medium/50 기준, 낮은값(102) profile에서 빠졌던 것: [KEC 231.5]·[KEC 351.6]·[KEC 503.2.4]·에너지절약형주택 설계조건. 높은값(107)엔 포함.

## 3. Root Cause
Evidence 기반 확정:
- before_clean(08:10~08:36)은 **`.order` 수정이 라이브에 완전히 안정되기 전 과도기 배포 상태**의 엔진에서 생성되었다(E2). PR #122 머지(11:26)·main 재배포는 그 이후.
- 그 과도기 엔진이 10 profile에서 일부 draft(KEC 3건 등, E4)를 누락하여 낮은값을 산출했다(E3).
- main 재배포(안정) 이후 현재 엔진은 동일 profile을 순차·병렬 무관하게 높은값으로 일관 산출한다(E1, E3). 편차는 현재 엔진에서 재현되지 않는다.
- **Root Cause: Obs-001의 '동일 입력, 다른 출력'은 현재 엔진의 실재 비결정이 아니라, 측정 기준선(before_clean)이 `.order` 과도기 배포 상태에서 생성되어 오염된 것이다.**
- 성격: 동시성(순차 vs 병렬) 원인 아님(E1에서 순차·병렬 모두 107 고정). 엔진 현재 로직의 비결정도 미재현.

## 4. Impact
- **Before Clean(기준선)**: 오염됨 — `.order` 과도기 상태 산물. Regression 기준으로 부적합. (직접 영향)
- **Measurement/Review**: before_clean 기반 관측(102 등)이 과도기 값. 현재 엔진과 불일치. (영향)
- **Engine(현재)**: 편차 미재현 — 현재 로직에는 영향 없음(안정). (무영향, 단 과도기 배포 중 노출됨)
- **Obs-004/005/006 등 다른 관측**: before_clean 기준으로 기술된 범위는 재확인 필요(오염 기준선 위였음). (본 WO에서 판단·수정 안 함)

## 5. Conclusion
- Obs-001의 Root Cause는 **측정 기준선(before_clean)이 `.order` 과도기 배포 상태에서 생성된 오염**으로 확정.
- 현재 엔진은 해당 10 profile을 순차·병렬 무관 결정적(높은값)으로 산출 — 편차 미재현.
- 본 WO는 원인까지만. '기준선을 안정 배포 후로 재생성한다' 등 조치(구현)는 다음 CHG WO의 책임.
- 완료 상태: Root Cause 확정 · Evidence 문서화 · 수정 0 · CHG 0 · 다른 Observation 분석 0. 다음 CHG WO 실행 가능.

## 참고 — 다음 CHG WO가 고려할 관측 (판단 아님)
- 현재 안정 엔진(main 재배포 후) 기준으로 Before Clean 재생성이 필요할 수 있음. after_obs003(14:19~, 머지 후, full 집계)이 이미 안정 엔진 산물로 존재.
