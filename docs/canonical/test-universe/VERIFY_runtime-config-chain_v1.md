---
wo: WO-CONFIG-001
class: records
type: verification
scope: canonical
project: test-universe
title: Runtime Configuration Chain Verification
version: 1
status: active
owner: taiwang
---

# RUNTIME CONFIGURATION CHAIN VERIFICATION — WO-CONFIG-001

> Runtime이 실제 사용하는 Supabase Project가 어디서 결정되는지 Configuration Chain을 증거로 확정. **코드/DB/Mapping/Sector 수정 0, 추론 0.**
> 엔진 코드 taiengineering/tai-api.

## 판정: CONFIG_CHAIN_BROKEN

## STEP 1 — Configuration Source Inventory
```text
코드      : db/supabase_client.py → create_client(os.environ["SUPABASE_URL"], KEY)
배포설정1 : fly.toml → app="tai-api-prod", region=nrt(도쿄), /health; [env]엔 SUPABASE_URL 없음
배포설정2 : fly.staging.toml
Dockerfile: [build]
.env.example : SUPABASE_URL=https://xntdkrjhgcscmqctdzyo.supabase.co (예시)
README    : naver_monitor는 Railway 크론
실제 secrets : Fly.io / Railway (값 비공개)
체인: Runtime → os.environ[SUPABASE_URL] → project_ref → DB → law_sector_mapping
```

## STEP 2 — Configuration Override 확인 (리포 실증)
```text
railway.toml     : 부재 (README 언급, 파일 없음)
fly.toml         : 있음. [env] PORT/ENVIRONMENT만. SUPABASE_URL은 secrets 주입.
fly.staging.toml : 있음(staging)
Dockerfile       : 있음
.env.production  : 부재 · .env : 부재(.gitignore) · .env.local : 부재
.env.example     : SUPABASE_URL=xntdkrjhgcscmqctdzyo (예시값)
Vercel           : 해당 없음(FastAPI, Fly/Railway)
Runtime Override : 코드가 os.environ만 읽음, dotenv 로더 없음
★ 코드는 순수 os.environ[SUPABASE_URL], 파일 override 없음. 실제 값은 배포 secrets(비공개).
★ .env.example ref(xntdkrjhgcscmqctdzyo)는 삭제됨('Resource has been removed').
```

## STEP 3 — Configuration Priority
```text
코드 증거(supabase_client.py): os.environ.get("SUPABASE_URL") 단일 소스, fallback 없음.
적용 순서: OS Environment(Fly secrets / Railway vars) → os.environ["SUPABASE_URL"].
           .env 파일 로더 없음(dotenv import 없음). 로컬은 수동 source.
```

## STEP 4 — Configuration Chain Review
```text
Runtime (db/supabase_client.py)
  ↓ os.environ["SUPABASE_URL"]          [OK] 코드 확정
SUPABASE_URL 값
  ↓                                      [BROKEN] 값 비공개; .env.example ref 삭제됨
Project Ref
  ↓                                      [UNKNOWN]
Database → law_sector_mapping            [UNKNOWN]

★ 중간(SUPABASE_URL 값 → Project Ref)이 비어 있음 → Chain Broken.
```

## STEP 5 — Decision: CONFIG_CHAIN_BROKEN
```text
관측 사실(추론 아님):
  1. 코드는 os.environ["SUPABASE_URL"] 단일 소스(fallback 없음).
  2. 실제 값은 Fly.io/Railway secrets, 리포·MCP로 비공개.
  3. .env.example 예시 ref xntdkrjhgcscmqctdzyo = 삭제됨('Resource has been removed').
  4. wrfcedzgdrfupenzqhur(엔진 DB로 써온 ref)엔 law_sector_mapping·engine_isolated 없음.
  5. 이 리포는 진단 API(Fly tai-api-prod) + naver 크론(Railway) 모노리포.

사유: 체인 핵심 연결(SUPABASE_URL 값 → Project Ref)이 끊김. 리포의 유일 구체 ref는 삭제됨.
      실제 배포 secrets 값 없이 런타임 DB 확정 불가.
```

## 앞 WO 대비 진전
```text
RUNTIME-DB-001 : EVIDENCE_INSUFFICIENT ('런타임 DB 모르겠다')
CONFIG-001     : CONFIG_CHAIN_BROKEN ('체인 추적 완료, 끊긴 곳 = 배포 secrets의 SUPABASE_URL 값')
                 + 구체 단서: .env.example ref(xntdkrjhgcscmqctdzyo) 삭제됨, 배포=Fly tai-api-prod
→ 논리적 비약 해소: 값을 못 읽는다≠증거 없다. 체인 구조·끊긴 지점을 증거로 특정.
```

## 다음 (증거 확보, 운영자 권한 필요)
```text
1. Fly.io: `fly secrets list -a tai-api-prod` → SUPABASE_URL 값(ref) 확인.
   (또는 Railway 해당 서비스 variables)
2. 그 ref에 law_sector_mapping·engine_isolated·pattern_dictionary·role_mapping 존재 확인.
3. 확정되면 WO-MAPPING-005 재개(그 ref가 실제 런타임 DB).
```

## Exit Criteria 점검
```text
[v] Runtime Configuration Source 확인 (os.environ[SUPABASE_URL], fly.toml)
[v] Runtime Configuration Priority 확인 (OS env 단일, dotenv 없음)
[~] Project Ref 결정 위치 확인 → 배포 secrets(값 비공개)로 특정, 값 미확인
[v] Override 여부 확인 (파일 override 없음)
[v] 추론 0 (미확정은 미확정으로)
[v] 코드 수정 0
```

## 산출물
```text
runtime_config_chain.md · config_chain_matrix.csv · config_ref_evidence.csv · config_source_inventory.csv
```

## 상태
```text
런타임 DB 확정   ✗ RUNTIME-DB-001 EVIDENCE_INSUFFICIENT → CONFIG-001 CONFIG_CHAIN_BROKEN ← 현재
                   끊긴 지점 = 배포 secrets의 SUPABASE_URL 값(.env.example ref는 삭제됨)
다음(선행)       : 운영자가 Fly/Railway secrets에서 SUPABASE_URL 값 확인 → 런타임 ref 확정 → MAPPING-005 재개
```
