---
wo: WO-ENGINE-DATA-ACCESS-001
class: records
type: report
scope: canonical
project: test-universe
title: Engine Data Access Measurement Environment v1
version: 1
status: active
owner: taiwang
---

# REPORT — Engine Data Access (측정환경 확보) v1

> WO-ENGINE-DATA-ACCESS-001. Cause Investigation에서 UNKNOWN으로 남은 Rule Data / Master / Engine 계층을 **측정 가능한지** 조사.
> **조사 WO. 문제 해결 WO 아님. 목적은 측정 환경 확보 여부의 기록이며 접속 성공이 아니다.**
> 원칙: Measure Before Modify — 읽기(SELECT)만. Engine·Rule·Master 무수정.
> Goal: G-ms8cylp2-eb6d75 · Input: REPORT_engine-cause-investigation_v1.md (CHG-001·CHG-002)

## 1. 대상 자산

| 자산 | 계층 |
|---|---|
| draft_slot | Rule Data |
| facility_applicability | Rule Data / Engine |
| law_sector_mapping | Master |

## 2. 위치 확인 — 확정(PASS)

| 자산 | 위치(schema.table) |
|---|---|
| draft_slot | `engine_isolated.draft_slot` |
| facility_applicability | `engine_isolated.facility_applicability` |
| law_sector_mapping | `public.law_sector_mapping` |

## 3. 아키텍처 확인 — 확정(PASS)

```
compiler_engine_gateway.py  (sha fbe529b3)
        ↓ import SUPABASE_URL, SUPABASE_KEY
db.supabase_client
        ↓ 동일 SUPABASE_URL
create_client(..., schema="engine_isolated")
```

- `engine_isolated`는 별도 DB가 아니라 **tai-api의 단일 Supabase 프로젝트 안의 schema**.
- `law_sector_mapping`은 동일 프로젝트의 기본(`public`) schema에서 기본 클라이언트로 조회(anonymous_factory_service).
- → 세 자산 모두 **하나의 Supabase 프로젝트**에 존재.

## 4. project_ref 상태 — 확정(PASS)

| 항목 | 실측 |
|---|---|
| 리포 내 유일 ref (`.env.example`) | `xntdkrjhgcscmqctdzyo` → execute_sql 응답 **"Resource has been removed"** = 폐기된 프로젝트 |
| 현재 production ref | **Fly Secret**. 백업 문서가 "env의 GitHub 커밋 절대 금지" 명시 → Git 미저장(설계상) |
| governance ref (`iapzwbysfzootqnldtan`) | engine_isolated 부재 → 엔진 DB 아님 |
| leg-prod ref (`wrfcedzgdrfupenzqhur`) | `public/quarantine.facility_applicability`만 존재, engine_isolated·draft_slot·law_sector_mapping 부재 → 엔진 DB 아님 |

## 5. 접근 · SELECT 가능 여부 — UNKNOWN

```
현재 클라우드 세션
        ↓
production project_ref
        ↓
접근 불가 (live ref는 Fly Secret, 이 세션 미도달)
        ↓
SELECT 가능 여부 = UNKNOWN
```

## 6. 조사 결론 (Fact)

**현재 세션에서는 Rule Data / Master / Engine 계층을 측정할 수 없다.**
이것이 이번 WO의 확정된 조사 결과이며, 유효한 Fact이다. (측정 불가도 유효한 Fact)

- 확정된 것: 자산 위치(schema.table), 단일 프로젝트 아키텍처, 리포 ref 폐기, 현재 ref의 Fly Secret 격리.
- 미지수로 남는 것: production project_ref, 그에 따른 SELECT 가능 여부.

## 7. 다음 단계 — WAIT

새로운 Fact(**Production project_ref 확보**)가 생기기 전까지 `WO-ENGINE-FIX-001`은 시작하지 않는다.
확보 경로(참고): 운영자 로컬 On-your-computer(배포 env의 `SUPABASE_URL`) 또는 운영자가 현재 ref 제공. 본 WO 범위 밖.

## 8. WO 상태

조사 완료(COMPLETED). 시스템상 PASSED로 종료하며 결론에 **"현재 세션 측정 불가 확인"**을 명시한다. FAIL 아님 — 조사 목적(측정 가능 여부 확정)은 달성됨.
