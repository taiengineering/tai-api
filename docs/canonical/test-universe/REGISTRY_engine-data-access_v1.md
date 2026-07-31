---
wo: WO-ENGINE-DATA-ACCESS-001
class: records
type: registry
scope: canonical
project: test-universe
title: Engine Data Access Asset Registry v1
version: 1
status: active
owner: taiwang
---

# REGISTRY — Engine Data Access Asset Registry v1

> WO-ENGINE-DATA-ACCESS-001 · Goal G-ms8cylp2-eb6d75
> 대상 3자산의 위치·접근·SELECT 가능 여부 등록. 측정 환경 = 현재 클라우드 세션(guri-cf execute_sql).

## 자산 등록부

| # | 자산 | 계층 | 위치(schema.table) | 소속 프로젝트 | current project_ref | 접근 경로 | runtime | SELECT |
|---|---|---|---|---|---|---|---|---|
| 1 | draft_slot | Rule Data | `engine_isolated.draft_slot` | tai-api Supabase (단일) | UNKNOWN (Fly Secret, Git 미저장) | SUPABASE_URL (배포 시크릿) | Cloud 미도달 / On-your-computer 필요 | UNKNOWN |
| 2 | facility_applicability | Rule Data·Engine | `engine_isolated.facility_applicability` | tai-api Supabase (단일) | UNKNOWN (Fly Secret, Git 미저장) | SUPABASE_URL (배포 시크릿) | Cloud 미도달 / On-your-computer 필요 | UNKNOWN |
| 3 | law_sector_mapping | Master | `public.law_sector_mapping` | tai-api Supabase (단일) | UNKNOWN (Fly Secret, Git 미저장) | SUPABASE_URL (배포 시크릿) | Cloud 미도달 / On-your-computer 필요 | UNKNOWN |

## 폐기·비대상 ref (참고)

| ref | 상태 | 판정 |
|---|---|---|
| `xntdkrjhgcscmqctdzyo` (.env.example) | Resource has been removed | 폐기됨 — 대상 아님 |
| `iapzwbysfzootqnldtan` (governance) | engine_isolated 부재 | 엔진 DB 아님 |
| `wrfcedzgdrfupenzqhur` (leg-prod) | public/quarantine.facility_applicability만 | 엔진 DB 아님 |

## Evidence

| 근거 | 확인 |
|---|---|
| tai-api `services/compiler_engine_gateway.py` (fbe529b3) | engine_isolated schema를 db.supabase_client의 동일 SUPABASE_URL로 바인딩 |
| tai-api `services/anonymous_factory_service.py` (b822b865) | law_sector_mapping을 기본(public) 클라이언트로 조회 |
| tai-api `.env.example` (a0f4297a) | SUPABASE_URL=https://xntdkrjhgcscmqctdzyo.supabase.co → 해당 ref 폐기 확인 |
| tai-api `docs/TAI_Railway_백업CLI_20260411.md` (775525b8) | env는 Git 커밋 금지·시크릿 보관 원칙 → 현재 ref 리포 부재(설계상) |
| execute_sql (governance / leg-prod / xntdk...) | 위치·폐기 실측 |

## 조사 상태

측정 환경 = 현재 세션 기준 **UNKNOWN(측정 불가)**. 조사 완료(COMPLETED). Production project_ref 확보 시 재측정 가능.
