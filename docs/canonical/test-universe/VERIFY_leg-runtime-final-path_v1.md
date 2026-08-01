---
wo: WO-CONFIG-003
class: records
type: verification
scope: canonical
project: test-universe
title: leg-runtime Final Path Verification
version: 1
status: active
owner: taiwang
---

# LEG-RUNTIME 최종 경로 확인 — WO-CONFIG-003

> 런타임 DB 후보(vwlahtguyggrhvslabax) 확정 후, 별도 leg-runtime 서비스가 만드는 최종 경로 하나만 확인. **코드/DB 수정 0, 추측 0. 자산 복사·MAPPING-005 재개 안 함.**
> 두 독립 차단(DB 위치 오류, Runtime 미배선)을 분리.

## 판정: LEG 경로 DB = wrfcedzgdrfupenzqhur (DATABASE_URL) / 데이터모델 = production_semantic_repository. 라이브 진단이 TAI냐 LEG냐는 미확정.

## 진단 경로 구조 (코드 확정)
```text
tai-api에 독립된 두 진단 경로:
(A) POST /anonymous-diagnosis      (TAI) → run_anonymous_diagnosis
      → law_sector_mapping·engine_isolated SELECT  [WIRING 시리즈가 추적한 경로]
(B) POST /anonymous-diagnosis-leg  (LEG) → run_leg_diagnosis
      → HTTP POST leg-runtime /rtm/evaluate
      clients/leg_runtime_client.py 주석: "Repository 직접 접근 없음.
        DATABASE_URL 사용 금지. LEG_RUNTIME_URL만 사용."
      → tai-api는 DB 미접근, leg-runtime 서비스가 DB 읽음
```

## leg-runtime 데이터 소스 (코드 확정)
```text
clients/leg_runtime_client.py: tai-api ──HTTP──> LEG Runtime ──> 31,434 Approved Atom ──> 4-Result
45cminc/leg production_repository.py:
  SELECT atom_id, mapped_field, semantic_clause_id, law_name, law_article, evidence, ...
  FROM public.production_semantic_repository ORDER BY atom_id
  EXPECTED_ROW_COUNT=337 · RC1 freeze=15cd17e8... · SEMREPO-RC1-2026.07.20
→ LEG는 law_sector_mapping·engine_isolated·pattern_dictionary·role_mapping 미사용.
  production_semantic_repository(337 atom)만 읽음.
```

## leg-runtime DB 연결 (코드+환경변수 확정)
```text
runtime_v3/repository/connection.py: dsn_from_env(env_var="DATABASE_URL")
api/server.py 주석: "DATABASE_URL   leg-prod (읽기 전용 사용)"
Railway leg-runtime 서비스 변수 실측:
  DATABASE_URL    → ref wrfcedzgdrfupenzqhur (pooler)   ← 코드가 읽는 것
  SUPABASE_DB_URL → ref vwlahtguyggrhvslabax            ← 코드가 이 이름 안 씀
→ leg-runtime 실제 DB = DATABASE_URL = wrfcedzgdrfupenzqhur
```

## production_semantic_repository 위치 실측
```text
wrfcedzgdrfupenzqhur : 있음, 337행 (코드 EXPECTED_ROW_COUNT 일치)  ← leg-runtime이 읽는 곳
vwlahtguyggrhvslabax : 테이블 있음 (양쪽 다 존재)
```

## 전제 대전환
```text
WIRING 시리즈는 TAI 경로(run_anonymous_diagnosis)만 추적 → law_sector_mapping·engine_isolated → vwlahtguyggrhvslabax.
그러나 LEG 경로는 완전히 다른 데이터 모델(production_semantic_repository @ wrfcedzgdrfupenzqhur).

정답 DB는 '라이브가 어느 경로냐'에 따라 갈림:
  라이브=TAI → 정답 DB=vwlahtguyggrhvslabax, 우리 자산 위치(wrfced) 틀림
  라이브=LEG → leg-runtime이 wrfced를 읽지만 데이터모델이 production_semantic_repository,
              pattern/role/lsm 미사용 → 우리 자산은 LEG도 안 읽음

★ 어느 경우든, pattern_dictionary·role_mapping은 현재 어느 런타임도 읽지 않음.
```

## 미확정 (추측 안 함)
```text
라이브 api.taieng.co.kr 무료진단이 (A)TAI인지 (B)LEG인지.
CANONICAL_PIPELINE=true·LEG_PIPELINE_ENABLED=true·TAI_USE_RUNTIME_ENGINE=false가
실제 어느 라우터로 요청을 보내는지 = main.py 라우터 마운트+프론트 호출 경로 확인 필요(다음).
```

## 정정 기록 (요청)
```text
WO-CHG-009  기존 PASSED(운영 엔진 DB 반영)
            → TARGET INVALID: pattern/role을 wrfced에 넣었으나 (A)TAI DB(vwlaht)도 아니고
              (B)LEG 데이터모델(production_semantic_repository)도 아님. 어느 런타임도 안 읽음. 영향 0.
WO-E2E-001  RUNTIME NOT WIRED 유지
            → 보강: 원인 둘 = (1)코드 pattern/role 소비 경로 없음 (2)자산이 어느 경로 데이터모델에도 불속.
WO-CONFIG-002 CONFIRMED vwlahtguyggrhvslabax
            → 보강: TAI 경로 DB로는 맞음. 라이브 경로 여부는 미확정으로 유지.
```

## 현재 E2E 상태 (정정 반영)
```text
자산 생성·검증                    PASS
잘못된 DB/모델에 자산 적재         CONFIRMED (wrfced, 어느 런타임 모델과도 불일치)
TAI 경로 DB                       vwlahtguyggrhvslabax (law_sector_mapping·engine_isolated)
LEG 경로 DB                       wrfcedzgdrfupenzqhur (production_semantic_repository 337)
Runtime pattern/role 소비 코드     ABSENT
라이브 경로(TAI vs LEG)            UNVERIFIED
전체 E2E                          NOT COMPLETE
```

## 다음 (하나)
```text
main.py 라우터 마운트 + 프론트(taieng.co.kr) 호출 경로로 라이브 진단이 TAI냐 LEG냐 확정.
→ 그 후에야 '정답 DB'와 '자산이 속해야 할 데이터모델'이 정해지고,
  올바른 반영 → Runtime 배선 → After 실행 → 의미검증 순서 성립.
자산 복사·MAPPING-005 재개는 그 전까지 금지 유지.
```

## Exit Criteria 점검
```text
[v] tai-api가 leg-runtime 호출하는지 (LEG 경로에서 호출, 코드 확정)
[v] TAI_USE_RUNTIME_ENGINE/LEG_PIPELINE_ENABLED/CANONICAL_PIPELINE 존재 확인 (분기 최종 라우팅은 미확정으로 명시)
[v] leg-runtime 실제 DB (DATABASE_URL=wrfcedzgdrfupenzqhur)
[v] 최종 진단이 어느 DB의 무엇을 읽는지 (LEG=production_semantic_repository@wrfced)
[v] 추측 0 · 코드/DB 수정 0 · 자산 복사·MAPPING 재개 0
```

## 산출물
```text
leg_runtime_path_confirmation.csv · correction_log.csv
```
