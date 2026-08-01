---
wo: WO-CONFIG-002
class: records
type: verification
scope: canonical
project: test-universe
title: Runtime DB Source-of-Truth
version: 1
status: active
owner: taiwang
---

# RUNTIME DB SOURCE-OF-TRUTH (전수 실측) — WO-CONFIG-002

> WO-CONFIG-001의 'Railway/Supabase 프로젝트 1개' 추측 오류 정정. 계정 키는 여러 프로젝트를 봄. 프로젝트 전수 열거 + 런타임 서비스 환경변수 실측 + 런타임 DB 테이블 실측. **코드/DB 수정 0, 추측 0.**

## 판정: RUNTIME DB CONFIRMED = vwlahtguyggrhvslabax

## 정정 (앞 WO 오류)
```text
앞 WO: Railway list-projects 1건·Supabase list_projects 1건 → 프로젝트 1개로 단정 (오류)
실측 : 계정 키는 워크스페이스 'TAI Engineering's Projects'를 봄
  프로젝트 45cm    : 13 서비스(mem·doc-engine·anl·ntf·adp·mcp-gateway·prj·ops·
                     doc-docling·45cm-federation-stage·insp-tools·prdc·collection-engine)
  프로젝트 tai-api : gotenberg·tai-api-prod·45cm-mkt-api·leg-runtime
(Railway MCP가 보여준 'kn541'은 다른 워크스페이스였음)
```

## 런타임 서비스 확정 (증거)
```text
진단 API 서비스 = tai-api-prod
  RAILWAY_PUBLIC_DOMAIN = api.taieng.co.kr  (라이브 진단 API 도메인과 일치)
  환경변수 SUPABASE_URL  = https://vwlahtguyggrhvslabax.supabase.co
  환경변수 DATABASE_URL  = ...@db.vwlahtguyggrhvslabax.supabase.co...
  → 런타임 실제 Project Ref = vwlahtguyggrhvslabax  (추측 아닌 실측)
부가:
  TAI_USE_RUNTIME_ENGINE=false · CANONICAL_PIPELINE=true · LEG_PIPELINE_ENABLED=true
  LEG_RUNTIME_URL=http://leg-runtime.railway.internal:8080 (별도 leg-runtime 서비스)
  키: SUPABASE_SERVICE_KEY·SUPABASE_KEY 둘 다 설정됨(코드 기대와 일치, 정상)
```

## 런타임 DB(vwlahtguyggrhvslabax) 실측
```text
law_master          존재
law_article         존재
law_sector_mapping  존재 ★ (_load_sector_allowed_draft_ids가 읽는 테이블)
sector_standard     존재
engine_isolated     스키마 존재 ★ (draft/slot/applicability)
pattern_dictionary  없음 ★★
role_mapping        없음 ★★ (public 및 전체 스키마 확인)
```

## 근본 오류 확정 — 우리는 '다른 DB'에 작업해왔다
```text
                     런타임 실제 DB          우리가 자산 넣은 DB
ref                  vwlahtguyggrhvslabax    wrfcedzgdrfupenzqhur
law_sector_mapping   있음                     없음
engine_isolated      있음                     없음
pattern_dictionary   없음                     있음(13)
role_mapping         없음                     있음(14)
law_master/article   있음                     있음

→ 두 DB는 완전히 다른 Supabase 프로젝트.
→ CHG-009로 pattern_dictionary·role_mapping을 넣은 wrfcedzgdrfupenzqhur는 런타임이 보지 않는 DB.
→ E2E-001 'RUNTIME NOT WIRED'의 진짜 원인: 코드 미배선 이전에, 애초에 '다른 DB'에 넣었기 때문.
→ MAPPING-005가 law_sector_mapping을 못 찾은 것은 정확한 관측이었고, 원인은 '잘못된 DB에서 찾음'.
```

## 이 프로젝트 원칙의 귀결
```text
"DB 존재 ≠ 런타임 사용"(E2E-001)에 더해, 이번에 더 근본:
  "우리가 작업한 DB" ≟ "런타임 DB"  — 이것을 처음부터 실측했어야 했다.
앞 WO들이 wrfcedzgdrfupenzqhur를 '엔진 DB'로 간주한 것 자체가 미검증 전제였다.
```

## 다음 (선행 순서)
```text
1. leg-runtime 서비스 환경변수·DB 확인 (LEG_RUNTIME_URL 분리 구조 → 진단이 그쪽 DB도 경유하는지)
   - CANONICAL_PIPELINE/LEG_PIPELINE_ENABLED=true, TAI_USE_RUNTIME_ENGINE=false의 실제 경로 의미 확정
2. 진단 런타임의 최종 DB(들) 확정 후, pattern_dictionary·role_mapping을 '올바른 DB'에 반영할지 결정
   (이때 비로소 MAPPING-005 재개 가능 — 단 대상 DB = vwlahtguyggrhvslabax 또는 leg-runtime DB)
3. wrfcedzgdrfupenzqhur의 기존 자산은 '잘못된 위치'였음을 기록(정리/이관 여부는 운영자 판단)
```

## Exit Criteria 점검
```text
[v] Railway/Supabase 프로젝트 전수 열거 (1개 단정 정정)
[v] 런타임 서비스(tai-api-prod) SUPABASE_URL 실측 = vwlahtguyggrhvslabax
[v] 런타임 DB 테이블 실측 (law_sector_mapping·engine_isolated 있음, 우리 자산 없음)
[v] 우리 자산 DB(wrfcedzgdrfupenzqhur)와 대조 (다른 DB 확정)
[v] 추측 0 (환경변수 실측 근거)
[v] 코드/DB 수정 0
```

## 산출물
```text
runtime_db_confirmation.csv · railway_project_inventory.csv
```

## 상태
```text
런타임 DB 확정   ✓ WO-CONFIG-002 → CONFIRMED = vwlahtguyggrhvslabax ← 현재
                   (우리 자산 DB wrfcedzgdrfupenzqhur와 다름 = 근본 오류 확정)
다음(선행)       : leg-runtime DB 확인 → 진단 최종 DB 확정 → 올바른 DB에 자산 반영 → MAPPING-005 재개
```
