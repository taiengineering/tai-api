---
wo: WO-E2E-BASELINE-001
class: records
type: registry
scope: canonical
project: test-universe
title: E2E Baseline Snapshot Set v1
version: 1
status: active
owner: taiwang
---

# REGISTRY — E2E Baseline Snapshot Set v1

> WO-E2E-BASELINE-001. 112 Consumer Profile 전수 라이브 실행. 판정·Golden 없음. 사실(Fact)만.
> On-your-computer 실행(클라우드 403 차단). 원칙: Snapshot=Fact, Baseline=Fact Collection.
> run_at: 2026-07-30T23:51:29.733255+00:00 · engine: v3.0-compiler-core-anonymous (전건 동일)

## 1. 실행 요약

| 항목 | 값 |
|---|---|
| 대상 Profile | 112 |
| 성공(http 200) | 110 |
| 실패 | 2 |
| 엔진 버전 | v3.0-compiler-core-anonymous (전건 동일) |

## 2. 실행 실패 목록 (사실 기록)

| Snapshot | Profile | Sector | HTTP | 오류 |
|---|---|---|---|---|
| SNAP-0107-001 | PF-0107 | SPECIAL_FACILITY | 502 | HTTP 502 (live gateway, transient) |
| SNAP-0111-001 | PF-0111 | SPECIAL_FACILITY | 502 | HTTP 502 (live gateway, transient) |

> 502는 라이브 게이트웨이 일시 오류(입력 문제 아님). 재실행 시 성공 가능. 판정하지 않는다.

## 3. 소재

| 파일 | 소재 |
|---|---|
| baseline_snapshot_set_v1.json | project: test-universe/ |
| snapshots_all/SNAP-*.json (112) | 사용자 PC ~/45cm-test/snapshots_all/ |
| 통계·이상치·후보 리포트 | tai-api canonical + project |

## 4. 다음 WO

> 이 Baseline이 최초 기준선. 다음=WO-E2E-GOLDEN-002(Baseline 기반 Golden 승인).
> Golden 승인·거부는 운영자가 이 Baseline 자료를 근거로 수행한다.
