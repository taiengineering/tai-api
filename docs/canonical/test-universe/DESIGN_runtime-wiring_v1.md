---
wo: WO-WIRING-001
class: plans
type: design
scope: canonical
project: test-universe
title: Runtime Integration Design (Read Only)
version: 1
status: active
owner: taiwang
---

# RUNTIME INTEGRATION DESIGN (READ ONLY) — WO-WIRING-001

> RUNTIME NOT WIRED(WO-E2E-001) 확인 후, 코드 수정 전 배선 설계만 확정. **코드·DB·Pattern/Role 수정 0.** 관측·연결 설계만.
> 엔진 코드 taiengineering/tai-api @ 0b262a31.

## 판정: DESIGN_BLOCKED

## STEP 1 — Runtime Flow Mapping
```text
POST /anonymous-diagnosis  [routers/anonymous_diagnosis.py]
 → _create_anonymous_diagnosis_impl()
   → _build_step1_body()      입력→DiagnoseStep1Body (사업장 sector는 site_kind로 결정)
        SECTOR_BY_KIND: construction→CONSTRUCTION · manufacturing→MANUFACTURING
                        · building→BUILDING · other→SPECIAL_FACILITY
   → _run_step1_via_service()
        → prepare_step1_body_for_compiler()  [services/anonymous_factory_service.py]
        → run_anonymous_diagnosis(supabase, step1_body, ALLOWED_SECTORS)  ★핵심 진단
   → _partial_from_full() → _build_standard_output()  [services/diagnosis_helpers.py]
   → anonymous_diagnosis_results 저장 → 응답

거름망: services/legal_engine_policy.py
  sieve_clause(clause, facility_sector, supabase)
    망1 'sector'        : clause_sector(의미절)가 사업장섹터 안 맞으면 DROP
    망2 'applicability' : executor(수범자) 적용대상 판정
  load_rules() : legal_sieve_rule 테이블에서 규칙 로드(캐시 TTL 300s), 실패 시 _FALLBACK
```

## STEP 2 — Injection Point Discovery (후보 전량)
```text
IP-A _build_step1_body 이전(입력)   : 사업장 sector 결정 지점. 법령 Role과 무관 → 부적합.
IP-B run_anonymous_diagnosis 내부   : 법령 후보에 pattern_dictionary로 Role 태깅. 코드 변경.
IP-C sieve_clause 'sector'망        : Role을 거름 보조신호로. 단 설계상 의미절 단위가 정석 → 층 충돌.
IP-D legal_sieve_rule 테이블(데이터) : 엔진은 '코드수정 없이 행추가'로 규칙 확장. 코드변경 0 가능. ★유력.
IP-E _build_standard_output(출력)   : Role 표시만. 판정 영향 없음.
```

## STEP 3 — Dependency Analysis
```text
현재 사용:
  law_master · law_article : 법령/조문 원천
  law_sector_mapping       : 법 단위 sector 매칭표
     ★ 설계주석: sector 거름의 1차 소스로 쓰지 '않음'("법 단위 매칭표는 거칠다").
        실질 sector 결정은 의미절 단위(clause_sector) 거름망.
  legal_sieve_rule         : 거름망 규칙(sector망·applicability망). 실질 sector 판단.

pattern_dictionary/role_mapping 추가 시 영향:
  IP-B → run_anonymous_diagnosis 수정
  IP-C → sieve_clause/load_rules 수정
  IP-D → 영향 함수 0 (데이터 행 추가만)
```

## STEP 4 — Runtime Gap
```text
pattern_dictionary : 읽는 코드 없음 (WO-E2E-001)
role_mapping       : 조회 없음 (WO-E2E-001)
Injection Point    : IP-D(데이터) 유력 / IP-B(코드) 대안

★ 중대 Gap (R-01):
  pattern_dictionary → Role(규율대상/시설) 산출
  엔진 sector 거름  → clause_sector(의미절: BUILDING/CONSTRUCTION/INDUSTRIAL)
  Role→sector 변환 규칙 부재. 층이 다름 → 곧바로 연결 불가.
```

## STEP 5 — Wiring Plan (순서만)
```text
Evidence(법령 원문)
   ↓
Pattern Matching (pattern_dictionary 문형 매칭)
   ↓
Role Assignment (role_mapping: 규율대상/시설)
   ↓
[간극] Role→Sector 변환 규칙  ← 현재 없음
   ↓
Sector Decision (기존 sieve_clause 거름망)
   ↓
Output
```

## STEP 6 — Risk Review
```text
기존 API 영향 : IP-D면 0 · IP-B/C면 run_anonymous_diagnosis 경로 변경 위험
Regression    : sector 거름이 이미 의미절 단위로 정교. Role(법령단위) 주입 시 교란 위험 HIGH
Caching       : load_rules TTL 300s. 새 테이블 캐시 전략 필요
Performance   : 법령별 13문형 매칭 추가 → 진단당 연산 증가
Fallback      : 엔진은 테이블 미독 시 _FALLBACK. 동일 패턴 적용 가능
Rollback      : IP-D면 행 삭제로 즉시 · 코드변경이면 배포 롤백
★ 최대 리스크: Role층(법령단위) ≠ sector층(의미절단위). 무시 배선 시 정교한 거름망 오염.
```

## STEP 7 — 판정: DESIGN_BLOCKED
```text
사유: 배선 '지점'은 찾음(IP-D 유력)이나, 흘려보낼 '내용'(Role→sector)이 미정의.
 - Pattern→Role까지 자산 준비됨(pattern_dictionary·role_mapping).
 - Role→Sector 변환 규칙 부재(R-01, HIGH).
 - 엔진 실제 sector 결정은 의미절 거름망 ↔ Pattern Dictionary는 법령단위 Role.
 → IMPLEMENT로 넘기면 Discovery(Role→sector 정의)가 구현에 섞임.
READY_FOR_IMPLEMENTATION 아님.
```

## 다음 (권고, 분리)
```text
선행 필요: WO-DESIGN-002 (Role→Sector 변환 규칙 정의, 설계·검증)
  - Role(규율대상/시설) → clause_sector 또는 facility_sector 매핑 근거 확립
  - 그 후 WO-WIRING-002 (변환 확정 후 배선 재설계) → WO-IMPLEMENT-001 (구현)
현재 배선 설계는 Role→Sector 정의 완료 시 IP-D(legal_sieve_rule 행추가) 방향 유력.
```

## Exit Criteria 점검
```text
[v] Runtime Flow Mapping (함수·파일·호출관계)
[v] Injection Point Discovery (IP-A~E)
[v] Dependency Analysis (law_* 사용처·영향 함수)
[v] Runtime Gap (읽는 코드 없음·Injection Point·Role≠sector)
[v] Wiring Plan (순서, 간극 명시)
[v] Risk Review (API·Regression·Caching·Perf·Fallback·Rollback)
[v] 판정 (DESIGN_BLOCKED)
[v] 코드·DB·Pattern/Role 수정 0
```

## 상태
```text
DB 적재·검증        ✓ WO-CHG-009
런타임 E2E          ✓ WO-E2E-001 → RUNTIME NOT WIRED
런타임 배선 설계     ✓ WO-WIRING-001 → DESIGN_BLOCKED ← 현재
선행(분리)          : Role→Sector 변환 정의(R-01) → 배선 재설계 → 구현
```
