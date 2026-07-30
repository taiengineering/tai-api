---
wo: WO-E2E-RUNNER-001
class: records
type: registry
scope: canonical
project: test-universe
title: E2E Snapshot Index v1
version: 1
status: active
owner: taiwang
---

# REGISTRY — E2E Snapshot Index v1

> WO-E2E-RUNNER-001 산출. 라이브 엔진(api.taieng.co.kr) 실행 Snapshot 4건 등록.
> On-your-computer 모드에서 실행(클라우드는 프록시 403 차단). Golden/Diff 미평가.
> run_at: 2026-07-30T23:32:24.037885+00:00

## 1. Snapshot 목록

| Snapshot ID | Profile | Sector | Engine | public_token | HTTP | risk | total | 선임 | 점검 | 조치 | 신고 | 법령수 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SNAP-0001-001 | PF-0001 | MANUFACTURING | v3.0-compiler-core-anonymous | 98bbe6ac-8b5e-45d5-afe2-f15f92d9efa7 | 200 | HIGH | 18 | 3 | 2 | 6 | 7 | 12 |
| SNAP-0019-001 | PF-0019 | BUILDING | v3.0-compiler-core-anonymous | d9037d86-5da3-4b0a-9b17-d58b7be34301 | 200 | HIGH | 107 | 9 | 5 | 70 | 23 | 18 |
| SNAP-0028-001 | PF-0028 | CONSTRUCTION | v3.0-compiler-core-anonymous | 653a1543-e011-4e46-bce9-334836099b92 | 200 | HIGH | 24 | 2 | 4 | 5 | 13 | 9 |
| SNAP-0037-001 | PF-0037 | SPECIAL_FACILITY | v3.0-compiler-core-anonymous | 8221a1cb-a67a-444b-b7be-169445f4cd54 | 200 | MEDIUM | 7 | 0 | 3 | 4 | 0 | 5 |

## 2. 실행 사실 (관찰)

| 항목 | 값 |
|---|---|
| Runner | tai-api tools/test_universe/e2e_runner.py |
| 실행 환경 | On-your-computer (사용자 PC 실네트워크). 클라우드=프록시 403 차단 |
| 엔드포인트 | POST https://api.taieng.co.kr/anonymous-diagnosis |
| 엔진 버전 | v3.0-compiler-core-anonymous (전 Snapshot 동일) |
| engine_OK | 4/4 (전건 http 200) |
| Golden/Diff | 미평가 (다음 WO) |

## 3. Snapshot 파일 (원본)

> 전문 JSON은 project 지식(45CM)에 등록됨. 대용량이라 repo에는 인덱스만 둔다.

| 파일 | 소재 |
|---|---|
| SNAP-0001-001.json | project: test-universe/snapshots/ |
| SNAP-0019-001.json | project: test-universe/snapshots/ |
| SNAP-0028-001.json | project: test-universe/snapshots/ |
| SNAP-0037-001.json | project: test-universe/snapshots/ |
| run_log.json | project: test-universe/snapshots/ |
| (실행 사본) | 사용자 PC ~/45cm-test/snapshots/ |

## 4. 다음 WO

> 이 Snapshot 집합은 WO-E2E-SNAPSHOT-001(Snapshot 관리)·WO-E2E-GOLDEN-001(Golden 생성)의 입력 기준선이다.
> Golden 승격·Diff 판정은 이 문서에서 확인된 Snapshot Evidence만 기반으로 수행한다.
