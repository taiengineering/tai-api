---
title: TAI Safe Pricing V2 — BE-OBJ04 Commercial Contract Storage V2 Evidence Report
status: EVIDENCE_REPORT
goal: G-mujxylms-0a7566
collected_by: Claude Code (COLLECT role)
collected_date: 2026-09-27
review_required: GPT REVIEW REQUIRED
---

# WO-PRICING-V2-BE-OBJ04 Evidence Report

---

## 1. EXECUTION ANCHOR

```
Branch : docs/pricing-canonical-20260927
Base   : 2484a9d9
```

---

## 2. LIVE DB OBSERVED

Project ref: `vwlahtguyggrhvslabax`

**public.contracts 컬럼 (READ ONLY 수집):**

```
id                  uuid         NOT NULL  DEFAULT gen_random_uuid()
company_id          uuid         NULLABLE
plan_code           text         NULLABLE
status_code         text         NOT NULL  DEFAULT 'ACTIVE'
start_date          date         NULLABLE
end_date            date         NULLABLE
max_factory_count   integer      NULLABLE
max_user_count      integer      NULLABLE
notes               text         NULLABLE
created_at          timestamptz  NULLABLE  DEFAULT now()
created_by          uuid         NULLABLE
updated_at          timestamptz  NULLABLE  DEFAULT now()
updated_by          uuid         NULLABLE
is_active           boolean      NULLABLE  DEFAULT true
contract_no         text         NULLABLE
service_type        text         NULLABLE
contract_amount     numeric      NULLABLE
vat_amount          numeric      NULLABLE
total_amount        numeric      NULLABLE
paid_amount         numeric      NULLABLE  DEFAULT 0
paid_at             timestamptz  NULLABLE
memo                text         NULLABLE
cancelled_at        timestamptz  NULLABLE
suspended_at        timestamptz  NULLABLE
suspended_reason    text         NULLABLE
quote_id            uuid         NULLABLE
addon_codes         text[]       NULLABLE  DEFAULT '{}'
items               jsonb        NULLABLE  DEFAULT '[]'
```

**RLS 상태:**

```
contracts            RLS = ENABLED
subscriptions        RLS = ENABLED
factories            RLS = ENABLED
construction_sites   RLS = ENABLED
```

---

## 3. EXISTING CONTRACTS OBSERVED

**Legacy 컬럼 재사용 여부:**

```
contracts.max_user_count    → Worker Capacity로 재사용: 0
contracts.plan_code         → ProductTier로 재해석: 0
contracts.max_factory_count → Site Scope 대체: 0
```

---

## 4. TARGET STORAGE CONTRACT

```
TARGET TABLES:
  public.saas_contract_commercial_versions  → NOT EXIST (no collision)
  public.saas_contract_site_scopes          → NOT EXIST (no collision)
```

---

## 5. COMMERCIAL VERSION TABLE

**COMMERCIAL_STORAGE_SCHEMA_VERSION:**

```
SAAS_CONTRACT_COMMERCIAL_V2
```

**컬럼:**

```
id                          uuid            NOT NULL  PK
contract_id                 uuid            NOT NULL  FK → contracts(id)
version_no                  integer         NOT NULL  >= 1

commercial_schema_version   text            NOT NULL  = 'SAAS_CONTRACT_COMMERCIAL_V2'

product_tier                text            NOT NULL  MANAGER|FIELD|CUSTOM
pricing_mode                text            NOT NULL  STANDARD|CUSTOM

worker_capacity             integer         NOT NULL  >= 0
term_months                 integer         NOT NULL  1|3|6|9|12

pricing_result_status       text            NOT NULL  READY|CUSTOM_REQUIRED
pricing_policy_version      text            NULLABLE
pricing_snapshot            jsonb           NULLABLE

effective_from              timestamptz     NOT NULL
superseded_at               timestamptz     NULLABLE

created_at                  timestamptz     NOT NULL  DEFAULT now()
created_by                  uuid            NULLABLE
```

**Unique Indexes:**

```
UNIQUE (contract_id, version_no)
UNIQUE (contract_id) WHERE superseded_at IS NULL  ← current version 최대 1개
```

**RLS:**

```
ENABLED
policies = 0
```

---

## 6. SITE SCOPE TABLE

**컬럼:**

```
id                      uuid            NOT NULL  PK
commercial_version_id   uuid            NOT NULL  FK → saas_contract_commercial_versions(id)

entity_type             text            NOT NULL  factory|site
entity_id               uuid            NOT NULL
sector                  text            NOT NULL  INDUSTRY|BUILDING|CONSTRUCTION
base_band_code          text            NULLABLE  (CUSTOM: NULL 허용)

created_at              timestamptz     NOT NULL  DEFAULT now()
```

**가격 컬럼:**

```
base_amount              = 없음  (Frozen pricing_snapshot에만 보관)
normal_site_amount       = 없음
applied_rate_bps         = 없음
final_site_amount        = 없음
```

**Unique Index:**

```
UNIQUE (commercial_version_id, entity_type, entity_id)  ← 동일 사업장 중복 금지
```

**RLS:**

```
ENABLED
policies = 0
```

---

## 7. STANDARD STORAGE RULE

MANAGER/FIELD 저장 조건:

```
pricing_mode             = STANDARD
pricing_result_status    = READY
pricing_policy_version   IS NOT NULL
pricing_snapshot         IS NOT NULL
```

Snapshot은 SaasPricingSnapshotV2.model_validate()를 통과한 READY 스냅샷.

Cross-validation:

```
commercial_version.product_tier       == snapshot.product_tier
commercial_version.pricing_mode       == snapshot.pricing_mode
commercial_version.term_months        == snapshot.term_months
commercial_version.pricing_policy_version == snapshot.policy_version
```

---

## 8. CUSTOM STORAGE RULE

CUSTOM 저장 조건:

```
pricing_mode             = CUSTOM
pricing_result_status    = CUSTOM_REQUIRED
pricing_policy_version   = NULL
pricing_snapshot         = NULL
```

CUSTOM에 가격 JSON 생성 금지. 특히 금지: `{}`, `0`, `{"total_amount":0}`.

TERM_DISCOUNT_UNRESOLVED 저장 금지 — Contract Storage는 READY|CUSTOM_REQUIRED만.

---

## 9. FROZEN SNAPSHOT RULE

Snapshot은 pricing_snapshot JSONB 컬럼에 직렬화하여 보관.

```python
snapshot.model_dump(mode="json")
```

계약 생성 이후 정책이 바뀌어도 이 JSON을 재계산하여 덮어쓰지 않는다.

---

## 10. MAPPER

**STANDARD Mapper:**

```python
build_standard_contract_storage_bundle_v2(
    contract_id, version_no, selection, calculation_result, effective_from, created_by
)
```

- `calculation_result.status != READY` → `SaasContractStorageMapperError`
- `calculation_result.snapshot is None` → `SaasContractStorageMapperError`
- Site Scopes는 반드시 `calculation_result.snapshot.sites`에서 derive
- 입력 objects mutate = 0

**CUSTOM Mapper:**

```python
build_custom_contract_storage_bundle_v2(
    contract_id, version_no, selection, effective_from, site_scopes=None, created_by
)
```

- `selection.product_tier != CUSTOM` → `SaasContractStorageMapperError`
- `pricing_snapshot = None`, `pricing_policy_version = None`
- `site_scopes = []` 허용 (Optional)

---

## 11. DDL PROPOSAL

파일:

```
docs/2026-09-27_TAI_SAFE_PRICING_V2_BE_OBJ04_DDL_PROPOSAL.sql
```

상태:

```
PROPOSAL ONLY
NOT APPLIED
```

내용:

```
CREATE TABLE public.saas_contract_commercial_versions  ← 1
CREATE TABLE public.saas_contract_site_scopes          ← 2
CHECK constraints
FK (ON DELETE RESTRICT)
Indexes
ENABLE ROW LEVEL SECURITY × 2
```

금지 항목 확인:

```
ALTER TABLE contracts  = 0
UPDATE/DELETE/TRUNCATE/DROP = 0
GRANT anon/authenticated   = 0
CREATE POLICY              = 0
Production DDL 적용        = 0
```

---

## 12. TEST RESULT

### 신규 테스트 매트릭스

| ID | 설명 | 결과 |
|---|---|---|
| S01 | MANAGER+STANDARD accepted | PASS |
| S02 | FIELD+STANDARD accepted | PASS |
| S03 | CUSTOM+CUSTOM accepted | PASS |
| S04 | MANAGER+CUSTOM rejected | PASS |
| S05 | FIELD+CUSTOM rejected | PASS |
| S06 | CUSTOM+STANDARD rejected | PASS |
| S07 | MANAGER worker=0 accepted | PASS |
| S08 | MANAGER worker>0 rejected | PASS |
| S09 | FIELD worker>=0 accepted | PASS |
| S10 | CUSTOM worker>=0 accepted | PASS |
| S11 | term=1 accepted | PASS |
| S12 | term=3 accepted | PASS |
| S13 | term=6 accepted | PASS |
| S14 | term=9 accepted | PASS |
| S15 | term=12 accepted | PASS |
| S16 | invalid term rejected | PASS |
| S17 | float term rejected | PASS |
| S18 | bool term rejected | PASS |
| S19 | STANDARD READY snapshot accepted | PASS |
| S20 | STANDARD snapshot=None rejected | PASS |
| S21 | STANDARD policy_version=None rejected | PASS |
| S22 | STANDARD status=CUSTOM_REQUIRED rejected | PASS |
| S23 | tier mismatch rejected | PASS |
| S24 | pricing_mode mismatch rejected | PASS |
| S25 | term mismatch rejected | PASS |
| S26 | policy_version mismatch rejected | PASS |
| S27 | CUSTOM status=CUSTOM_REQUIRED accepted | PASS |
| S28 | CUSTOM snapshot=None accepted | PASS |
| S29 | CUSTOM snapshot present rejected | PASS |
| S30 | CUSTOM policy_version present rejected | PASS |
| S31 | CUSTOM READY rejected | PASS |
| S32 | INDUSTRY/factory accepted | PASS |
| S33 | BUILDING/factory accepted | PASS |
| S34 | CONSTRUCTION/site accepted | PASS |
| S35 | INDUSTRY/site rejected | PASS |
| S36 | BUILDING/site rejected | PASS |
| S37 | CONSTRUCTION/factory rejected | PASS |
| S38 | duplicate site rejected | PASS |
| S39 | STANDARD scope missing snapshot site rejected | PASS |
| S40 | STANDARD extra scope rejected | PASS |
| S41 | sector mismatch rejected | PASS |
| S42 | base_band_code mismatch rejected | PASS |
| S43 | CUSTOM zero site scopes accepted | PASS |
| S44 | CUSTOM optional site scopes accepted | PASS |
| M01 | READY result → storage bundle | PASS |
| M02 | unresolved result rejected | PASS |
| M03 | CUSTOM result rejected by STANDARD mapper | PASS |
| M04 | sites derived from Snapshot | PASS |
| M05 | input objects not mutated | PASS |
| M06 | CUSTOM selection → custom bundle | PASS |
| M07 | custom snapshot always None | PASS |
| M08 | custom policy version always None | PASS |
| D01 | two expected CREATE TABLE | PASS |
| D02 | RLS enabled on both | PASS |
| D03 | version unique constraint/index | PASS |
| D04 | current-version partial unique index | PASS |
| D05 | duplicate site unique constraint | PASS |
| D06 | FK contracts | PASS |
| D07 | no ALTER TABLE contracts | PASS |
| D08 | no UPDATE/DELETE/TRUNCATE/DROP | PASS |
| D09 | no anon/auth policy | PASS |

```
python3 -m pytest -q \
  tests/test_saas_pricing_v2_contract.py \
  tests/test_saas_pricing_policy_v2.py \
  tests/test_saas_pricing_composer_v2.py \
  tests/test_saas_contract_commercial_v2.py

227 passed in 0.26s
```

---

## 13. REGRESSION

```
이전 기준 : 166 PASS
이번 이후 : 227 PASS (166 regression + 61 신규)

FAIL = 0
```

---

## 14. RUNTIME CONSUMER SEARCH

검색 대상:

```
routers/
services/payment_svc.py
services/payment_post_process.py
services/contract_engine_svc.py
services/tier_payment_gate_svc.py
services/pricing_resolver_svc.py
```

검색어:

```
saas_contract_commercial_v2
saas_contract_storage_mapper_v2
```

결과:

```
Runtime consumer = 0
```

---

## 15. PRODUCTION MUTATION

```
INSERT = 0
UPDATE = 0
DELETE = 0
DDL EXECUTION = 0
```

Production Supabase 접근: READ ONLY (contracts 스키마 + target table 존재 여부 확인만).

---

## 16. FILES CHANGED

신규 생성:

```
schemas/saas_contract_commercial_v2.py
services/saas_contract_storage_mapper_v2.py
tests/test_saas_contract_commercial_v2.py
docs/2026-09-27_TAI_SAFE_PRICING_V2_BE_OBJ04_DDL_PROPOSAL.sql
docs/2026-09-27_TAI_SAFE_PRICING_V2_BE_OBJ04_EVIDENCE.md
```

기존 파일 수정:

```
0
```

---

## 17. NOT_FOUND

없음.

---

## 18. UNVERIFIED

없음.

---

```
GPT REVIEW REQUIRED
```
