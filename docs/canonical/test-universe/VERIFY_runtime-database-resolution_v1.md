---
wo: WO-RUNTIME-DB-001
class: records
type: verification
scope: canonical
project: test-universe
title: Runtime Database Resolution
version: 1
status: active
owner: taiwang
---

# RUNTIME DATABASE RESOLUTION — WO-RUNTIME-DB-001

> 엔진 Runtime이 실제 조회하는 Supabase ref와 law_sector_mapping 실제 위치를 증거로 확정. **코드 수정 0, 추론 0.**

## 판정: EVIDENCE_INSUFFICIENT

## STEP 1 — Runtime Client Resolution
```text
db/supabase_client.py:
  SUPABASE_URL = os.environ.get("SUPABASE_URL")
  SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
  get_supabase() = create_client(SUPABASE_URL, SUPABASE_KEY)
→ 런타임 DB는 배포 환경변수 SUPABASE_URL이 결정. 코드에 ref 하드코딩 없음.
```

## STEP 2 — Environment Resolution
```text
Railway 프로젝트 kn541(95b38706) · 서비스 kn541(67b83ab1) · production:
  SUPABASE_URL 존재 · SUPABASE_SERVICE_ROLE_KEY 존재 · SUPABASE_ANON_KEY 존재
  ★ 변수 값은 연결 앱(MCP)에 비공개 → SUPABASE_URL 실제 값(ref) 읽기 불가
Runtime Project Ref : UNRESOLVED (값 비공개)
Source : Railway env SUPABASE_URL · Evidence : 변수 존재 확인, 값 미확인
※ 관측: 코드는 SUPABASE_SERVICE_KEY/SUPABASE_KEY 기대, Railway엔 SUPABASE_SERVICE_ROLE_KEY (이름 불일치 가능성, 확인 대상)
```

## STEP 3 — Database Identity (접근 가능 ref별)
```text
ref                    lm la lsm pd rm ss  note
wrfcedzgdrfupenzqhur   1  1  0   1  1  1   engine_isolated 스키마 없음
iapzwbysfzootqnldtan   0  0  0   0  0  ?   projection 전용(guri-cf default)
ghtkropmnrelkxivzpim   0  0  0   0  0  0   kn541shop(Supabase MCP, 무관)
kn541-cf               ?  ?  ?   ?  ?  ?   JWT 실패 접근불가
SUPABASE_URL 값         ?  ?  ?   ?  ?  ?   값 비공개
```

## STEP 4 — Runtime Contract Verification
```text
코드 요구: supabase.table("law_sector_mapping") + engine_isolated 스키마(draft/slot/applicability)
접근 가능 ref 검사: law_sector_mapping 0곳 · engine_isolated 0곳
→ 코드 요구 런타임 테이블/스키마가 접근 가능한 어느 ref에도 없음.
→ 런타임 실제 대상은 '접근 가능 ref 중엔 없음'이 관측 사실(값 비공개로 실제 ref 미확인).
```

## STEP 5 — Identity Matrix
```text
Runtime Ref (SUPABASE_URL 값) : UNRESOLVED
Current 'Engine DB' Ref       : wrfcedzgdrfupenzqhur

테이블             wrfcedzgdrfupenzqhur   Runtime Ref
law_master         존재                   UNKNOWN
law_article        존재                   UNKNOWN
law_sector_mapping 없음                   UNKNOWN(코드 요구)
pattern_dictionary 존재                   UNKNOWN
role_mapping       존재                   UNKNOWN

Same/Different : 판정 불가(Runtime Ref 미확정)
확정 사실: wrfcedzgdrfupenzqhur는 law_sector_mapping·engine_isolated 부재 →
          코드 요구 런타임 계약을 완전히 충족하지 못함.
```

## STEP 6 — Decision: EVIDENCE_INSUFFICIENT
```text
사유:
  - 런타임 SUPABASE_URL 값(ref)이 Railway에서 비공개 → 직접 확인 불가.
  - 접근 가능 4 ref 중 어디에도 law_sector_mapping·engine_isolated 없음.
  - '런타임이 보는 DB'를 증거로 확정 불가.

확정 사실(추론 아님):
  1. 런타임 DB = env SUPABASE_URL 결정(하드코딩 없음).
  2. wrfcedzgdrfupenzqhur엔 law_sector_mapping·engine_isolated 부재
     → 코드 요구 런타임 계약 미충족(=이 ref는 런타임 완전 대상 아닐 가능성, 단 미확정).
  3. iapzwbysfzootqnldtan·ghtkropmnrelkxivzpim도 엔진 DB 아님.
  4. kn541-cf JWT 실패 접근불가.
```

## 이 WO가 드러낸 것
```text
지금까지 'wrfcedzgdrfupenzqhur = 엔진 DB'로 간주하고 CHG-009 등을 반영해 왔으나,
이 ref엔 런타임이 실제 쓰는 law_sector_mapping·engine_isolated가 없음.
→ 우리가 pattern_dictionary·role_mapping을 넣은 DB가
  '런타임이 실제 보는 DB와 같은지'가 미확정.
→ 이것이 E2E-001에서 관측한 RUNTIME NOT WIRED의 더 근본적 원인일 수 있음(단, 확정 아님).
```

## 다음 (증거 확보 경로, 운영자/추가 권한 필요)
```text
1. Railway 대시보드/CLI에서 SUPABASE_URL 값 직접 확인 → 런타임 ref 확정.
2. 그 ref에 law_sector_mapping·engine_isolated·pattern_dictionary·role_mapping 존재 확인.
3. 키 이름 불일치(SUPABASE_SERVICE_KEY vs SUPABASE_SERVICE_ROLE_KEY) 확인.
이 3가지가 풀려야 WO-MAPPING-005 재개 가능.
```

## Exit Criteria 점검
```text
[~] Runtime Project Ref 확정 → UNRESOLVED(값 비공개)
[v] Runtime DB 확인 시도 (접근 가능 ref 전수)
[v] law_sector_mapping 실제 위치 → 접근 가능 어느 ref에도 없음(확정)
[~] Runtime DB와 현재 DB 관계 → 판정 불가(Runtime ref 미확정), 단 현재 ref 미충족은 확정
[v] 추론 0 (미확정은 미확정으로 남김)
[v] 코드 수정 0
```

## 산출물
```text
runtime_database_identity.md · runtime_ref_matrix.csv · runtime_table_inventory.csv · runtime_contract_review.md
```

## 상태
```text
Role→Sector 결정   ✗ WO-MAPPING-005 STOPPED (law_sector_mapping 부재)
런타임 DB 확정     ✗ WO-RUNTIME-DB-001 → EVIDENCE_INSUFFICIENT ← 현재
                     (런타임 SUPABASE_URL 값 비공개, 접근 가능 ref엔 lsm/engine_isolated 없음)
다음(선행)         : SUPABASE_URL 값 확인(운영자) → 런타임 ref 확정 → 그 DB 검사 → MAPPING-005 재개
```
