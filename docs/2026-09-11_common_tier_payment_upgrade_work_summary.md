# TAI Safe SaaS 공통 티어 게이트 및 추가결제 작업 정리

> WO-COMMON-TIER-PAYMENT-GATE-MODULARIZE-001
> B1 ~ B7-B / RELEASE-A1 ~ A5
>
> 저장 위치(권장): `tai-api/docs/2026-09-11_common_tier_payment_upgrade_work_summary.md`
> 성격: **DOC ONLY** (코드/DB/ENV/결제 변경 0). 모든 SHA·상태는 GitHub/production 실측 기준.

---

## 0. Executive Summary (현재 상태)

```text
Backend 구현              = COMPLETE
Backend production merge  = COMPLETE   (tai-api main = b2082bb)
Backend production deploy = COMPLETE   (Railway SUCCESS, b2082bb)
Backend non-mutating smoke= PASS       (empty-token /tier-upgrade/pay → 403)

Production migration      = COMPLETE   (saas_tier_upgrade_transitions)
PAYMENT_LAUNCH_SECRET     = OPERATOR CONFIRMED  (값 미기록)

Frontend 구현             = COMPLETE
Frontend Draft PR #81     = CREATED (open/draft)
Frontend merge/deploy     = NOT YET
Real payment smoke (A6)   = NOT YET
```

> **결론**: 결제 backend 및 production 준비(merge·deploy·migration·secret·smoke)는 완료되었고, 남은 핵심 작업은 **frontend PR #81 merge/deploy**와 **실제 결제 1건의 controlled smoke test(A6)** 이다.

상태 어휘 구분: `IMPLEMENTED` / `MERGED` / `DEPLOYED` / `PROD CONFIGURED` / `VERIFIED` / `DEFERRED` / `NOT YET MERGED`.

---

## 1. 왜 이 작업을 했는가

핵심 문제:

```text
SaaS 사용자가 등록한 사업장/현장 규모에 따라 필요 요금제가 달라진다.
현재 계약 플랜보다 법령엔진 실행에 필요한 플랜이 높으면,
공식 LEG(법령의무추출) 실행 전에 추가결제가 필요하다.
```

필요 기능 흐름:

```text
현재 플랜 확인 → 사업장 규모 판정 → 필요 요금제 산정 → FIT / UPGRADE_REQUIRED
→ 차액 결제 → 계약/구독 플랜 변경 → 다시 FIT → LEG 실행 가능
```

---

## 2. 가장 중요한 설계 원칙

### 2-1. 기존 결제 기능을 다시 만들지 않고 공유
재사용: `payments` 테이블 · INICIS `prepare` · INICIS `return` callback · `process_card_success`(결제 성공 처리) · `contracts` · `subscriptions` · Cloudflare `_api` proxy.
신규는 tier upgrade에 필요한 **adapter / ledger / gate**만 추가.

### 2-2. Frontend는 금융 권한 없음
Frontend가 결정하지 않는 값: `amount · plan_code · target_plan · sector · company_id · contract_id · VAT · delta`.
모든 금액/플랜/차액 판정은 **backend 정본**.

### 2-3. 공통 gate 공유 (consumer별 복사 0)
`diagnosis-step1`, `construction-extraction` 두 화면이 동일 공통 모듈 사용: `useTierPaymentGate()` + `TierPaymentGateAlert.vue`. consumer별 결제 로직 복사 = 0.

---

## 3. 전체 구조도 (end-to-end)

```text
SaaS 화면 (diagnosis-step1: factoryId / construction-extraction: siteId)
  ↓
GET /payments/tier-gate            (auth, 서버가 계약+실제 규모 읽어 판정)
  ↓
Backend pricing resolver (price_master)
  ↓  현재 계약 plan  vs  필요 plan(criteria band)
  ├─ FIT              → LEG 실행 가능
  └─ UPGRADE_REQUIRED → [추가결제]
        ↓
     POST /payments/tier-upgrade/prepare   (auth, client=대상ID+buyer+return_url만)
        ↓  Backend:
        ├─ tier gate 재평가 → target plan / delta / VAT (전부 서버 결정)
        ├─ (기존) run_inicis_prepare → payments PENDING 1건
        └─ saas_tier_upgrade_transitions PREPARED 1건
        ↓  응답: launch { method=POST, url, token(signed) }
        ↓  Frontend: 임시 form POST (hidden = token 하나)
        ↓
     taieng.co.kr/_api/payments/tier-upgrade/pay   (CF proxy → api.taieng.co.kr)
        ↓  server payment page: token/HMAC/exp 검증 + payment PENDING·UPGRADE·oid·price + transition PREPARED 검증 (READ+VERIFY+RENDER, mutation 0)
        ↓
     INIStdPay (서버 페이지에서 실행)
        ↓
     (기존) POST /payments/inicis/return → process_card_success → on_payment_success_sync
        ↓  payment_type==UPGRADE 선분기
     apply_saas_tier_upgrade:
        ├─ contract  plan_code/금액 = target FULL 절대 SET (start/end 불변)
        ├─ subscription(있으면) plan/amount = target FULL 절대 SET
        └─ transition PREPARED → APPLIED
        ↓
     tier-gate 재확인 → FIT → LEG 실행 가능
```

즉시결제 = **delta(차액+VAT)**. 다음 정기결제/계약·구독 저장 = **target FULL**.

---

## 4. B1 ~ B7-B 작업 이력 (tai-api SHA, 별도 표기 시 tai-admin)

| 단계 | SHA | 내용 |
|---|---|---|
| **B1** Shared pricing resolver | `eeefa04ff56b88923398bf7cd0c364b52e91056b` | `/public/pricing/resolve` 로직을 `pricing_resolver_svc`로 공통화(parity). |
| **B2** Tier gate | `985ba8bd856de291125766f8db33b993fb0f9a7e` | `GET /payments/tier-gate` 신규(read-only). 판정 `FIT`/`UPGRADE_REQUIRED`, 서버 authority(계약+factory/site 규모), 건설=site_id·`contract_amount×1e8`. |
| **B3** Tier upgrade | `9cad23cbc1bd9f2fd7fe197cd6420bd54d998ba3` | server-owned upgrade prepare, delta 결제, transition ledger, contract/subscription target 절대 SET. |
| **B3-C1** Safety | `d8865a75977bdc438cf346887435c921114501d1` | ledger RLS enable · transition insert 실패 시 orphan payment FAILED · APPLY_FAILED 시 정상완료 알림 차단. |
| **B4** LEG execution gate | `0247fd66062191661cf686d56a1d167fed8408db` | industrial/building/construction-leg 실행 전 commercial tier gate(FIT 아니면 402), 엔진 내부 불변. |
| **B4-C1** LEG test adapt | `98b62bc9ed68ccf256d6aef9adc82d744b523d21` | 기존 LEG HTTP 테스트에 FIT gate 전제 추가(TEST-ONLY). ※ B7-A1 커밋도 이 SHA 시점 포함. |
| **B7-A1** Secure provider launch | (B4-C1과 동일 브랜치 진행) `11c4d9965d419917f9b1d9a649c5d33629a189c5` | signed short-lived launch token, 전용 server payment page(`tier_upgrade_pay.html`), token 검증, 기존 INICIS callback 재사용, DB mutation 0. |
| **B7-C1** repeated prepare guard | `770c872e111aadde9f270c66495dab00f0c2e8ff` | 동일 대상 PREPARED 존재 시 재-prepare 차단(`TIER_UPGRADE_ALREADY_PENDING` 409). |
| **B7-C1-a** APPLY_FAILED guard | `d614a9e2d4ebbf95d7034e18274c2fc428dacbb3` | APPLY_FAILED(=결제됨·복구필요) 상태 재결제 차단(`TIER_UPGRADE_REPAIR_REQUIRED` 409). |
| **B5** Frontend common module (tai-admin) | `7f9250b60e2ab6fe18f88cae3e41dcf0b20aae0f` | 공통 `tierPaymentGateContract.ts`·`useTierPaymentGate.ts`·`TierPaymentGateAlert.vue`. |
| **B6** Consumer wiring (tai-admin) | `02c4bea89d024d46ddaa2f0baa3dc963c8c918ee` | diagnosis-step1/construction-extraction 로컬 tier 제거 → 공통 모듈. |
| **B6-C1** sector-aware (tai-admin) | `3b5e4775c207ab8a33decc80b4d7ac771c99f380` | gate를 INDUSTRY/BUILDING(factory)만, CONSTRUCTION/SPECIAL_FACILITY 우회. |
| **B7-B** Frontend launch (tai-admin) | `e5d87144bcea33b219fa993a06effaa47f53c35e` | backend `launch.url` 사용, form POST hidden=`token` 하나, 프론트 INIStdPay 미사용, 금융필드 0, re-entry 가드. |

> 참고: B1~B7-A1/C1/C1-a 9커밋은 tai-api PR #313에 담겨 있고(아래 §5), B5~B7-B는 tai-admin PR #81(§6).

---

## 5. Backend 최종 merge (tai-api)

```text
PR              = tai-api #313
source head     = d614a9e2d4ebbf95d7034e18274c2fc428dacbb3
merge method    = SQUASH
production main  = b2082bbcebf99e7ce79728518c8fb9e38c0b046f
parent          = d3777b6a56834c05718344ba73fc44f3a9cf322c   (old main 위 squash 1개)
commits(squashed)= 9 · changed files = 20
상태            = MERGED · DEPLOYED · PRODUCTION SMOKE PASS
```

Railway `tai-api` production: deployment `a9d16e39` = **SUCCESS**, source SHA `b2082bb`.

---

## 6. Frontend 현재 상태 (tai-admin)

```text
repo   = taiengineering/tai-admin
branch = feat/diagnosis-step1-leg-preflight
HEAD   = e5d87144bcea33b219fa993a06effaa47f53c35e
PR     = #81
state  = OPEN / DRAFT
base   = main @ 48b154f51c59162dc5dfd4e94803aa30129ec6ee
commits= 8 · changed files = 12
frontend merge  = NOT YET
frontend deploy = NOT YET
```

PR #81 변경 12파일: `TierPaymentGateAlert.vue` · `tierPaymentGateContract.ts` · `useTierPaymentGate.ts` · `tierPaymentLaunch.ts` · 공통 test 2 · diagnosis-step1(index/composable/test) · construction-extraction(index/composable/test).

---

## 7. Production DB 변경

신규 테이블 `public.saas_tier_upgrade_transitions` — **production 적용 완료(A1)**.

주요 schema: `payment_id UNIQUE · company_id · contract_id · entity_type · entity_id · sector · from_plan_code · target_plan_code · billing_unit · current/target/delta_supply · delta_vat/total · target_vat/total · status · last_error · applied_at · created/updated_at · subscription_id · subscription_snapshot · target_plan_name`.
status: `PREPARED / APPLIED / APPLY_FAILED`. 제약: PK(id) · UNIQUE(payment_id)+명시 unique index · FK payment_id→payments(id) · FK contract_id→contracts(id) · CHECK(entity_type∈factory/site) · CHECK(status).
보안: **RLS ENABLED · user-facing policy 0**(service-role 전용).
A1 검증 당시: **column count = 25 · row count = 0**.

---

## 8. Production ENV

```text
PAYMENT_LAUNCH_SECRET = OPERATOR CONFIGURED   (필수, ≥32byte, 값은 문서에 절대 기록 안 함)
PAYMENT_LAUNCH_URL / PAYMENT_LAUNCH_TTL_SECONDS = 기본값 사용(미변경)
```

---

## 9. Backend production smoke (비파괴)

```text
POST https://api.taieng.co.kr/payments/tier-upgrade/pay      (empty token) → 403
POST https://taieng.co.kr/_api/payments/tier-upgrade/pay     (empty token) → 403
의미: route deployed · launch config(secret) 통과 · empty token 정상 거절 · CF proxy 연결 정상
side effect: transition rows = 0 · UPGRADE payment rows = 0  (before=after=0)
```

---

## 10. 현재 할 수 있는 것 / 아직 할 수 없는 것

**가능**: ① backend tier-gate production 사용 ② upgrade prepare/launch 코드 사용 ③ production transition ledger ④ signed launch token 검증 ⑤ CF payment launch proxy ⑥ frontend PR #81 merge 준비.
**불가(아직)**: 일반 사용자가 **production frontend에서 새 tier upgrade UI 사용**(PR #81 미merge) · **정상 INICIS 실결제 전체 E2E**(A6 미검증).

---

## 11. 남은 작업

**A5-2**: PR #81 Ready → PRE-MERGE GUARD → squash merge → production deploy 확인.
**A6**: controlled real payment 1건 — `UPGRADE_REQUIRED → 추가결제 → INICIS 결제창 → 결제 성공 → payment SUCCESS → transition APPLIED → contract plan 변경 → subscription plan 변경 → tier-gate FIT → LEG 실행 가능`.

---

## 12. DEFER 항목 (현재 beta blocker 아님)

`G3 동시 prepare race` · `G-repair(APPLY_FAILED 자동복구 도구)` · `launch token replay tracking` · `stale PENDING cleanup` · `browser callback replay hardening`.
원칙: production에서 실제 문제 관찰 시 **별도 WO**로 처리. 이 문서에서 추가 해결방안을 설계하지 않는다.

---

## 13. 주요 안전장치 (현 구현)

Frontend re-entry guard · 추가결제 버튼 disabled/loading · Backend PREPARED 중복 guard · APPLY_FAILED 재결제 guard · server-side pricing/target plan/delta·VAT · signed launch token(short TTL, HMAC-SHA256, `compare_digest`) · payment/transition launch 검증 · RLS transition ledger · 기존 payment callback 재사용 · apply APPLIED no-op(멱등) · contract/subscription 절대값 SET.

---

## 14. 기존 결제 vs 신규 부분

| 영역 | 상태 |
|---|---|
| payments table | 기존 재사용 |
| INICIS prepare (`run_inicis_prepare`) | 기존 재사용 |
| INICIS return callback (`/payments/inicis/return`) | 기존 재사용 |
| `process_card_success` / `on_payment_success_sync` | 기존 재사용 |
| contract | 기존 재사용 |
| subscription | 기존 재사용 |
| Cloudflare `_api` proxy | 기존 재사용 |
| pricing resolver (`/public/pricing/resolve`) | 공통화 |
| tier gate (`/payments/tier-gate`) | 신규 |
| upgrade transition ledger (`saas_tier_upgrade_transitions`) | 신규 |
| signed payment launch (`payment_launch_svc` + `tier_upgrade_pay.html` + `/tier-upgrade/pay`) | 신규 adapter |
| frontend tier gate (`useTierPaymentGate`/`TierPaymentGateAlert`) | 신규 공통 UI |

> 목적: **"결제 시스템 전체를 다시 만든 것이 아니다"** — 기존 결제 인프라 재사용 + tier 판정/차액/ledger/launch/공통 UI만 신규.

---

## 15. 장애 시 확인 순서 (운영 체크리스트)

- **추가결제 버튼이 안 뜸** → `GET /payments/tier-gate` response의 `status·current_plan·required_plan·metric`, 프론트 target binding(factoryId/siteId) 확인.
- **결제창이 안 열림** → `POST /payments/tier-upgrade/prepare` response의 `launch` 존재 · `launch.method==POST` · `launch.url` · `token` 존재. (token 값 자체는 로그/문서 기록 금지.)
- **launch 503** → `PAYMENT_LAUNCH_SECRET` 설정 상태 확인(값 조회/노출 금지).
- **결제됐는데 플랜 변경 안 됨** → `payments.status_code` + `saas_tier_upgrade_transitions.status`(PREPARED/APPLIED/APPLY_FAILED) + `contract.plan_code` + `subscription.plan_code`. **APPLY_FAILED면 새 결제를 다시 생성하지 않는다**(복구 대상).

---

## 16. 절대 하지 말아야 할 것 (운영 주의)

```text
frontend에서 amount 계산 금지 · plan 결정 금지
generic pay.html을 tier upgrade에 재사용하여 second prepare 발생 금지
consumer별 payment logic 복사 금지
APPLY_FAILED에서 재결제 금지
PAYMENT_LAUNCH_SECRET 로그/문서 기록 금지
```

---

## 17. 최종 상태표

```text
B1 PASS · B2 PASS · B3 PASS · B3-C1 PASS · B4 PASS · B4-C1 PASS
B5 PASS · B6 PASS · B6-C1 PASS · B7-A1 PASS · B7-C1 PASS · B7-C1-a PASS · B7-B PASS

RELEASE-A1 PASS            (production migration)
RELEASE-A2 OPERATOR CONFIRMED  (PAYMENT_LAUNCH_SECRET)
RELEASE-A3 PASS            (backend squash merge → main b2082bb)
RELEASE-A4 PASS            (backend deploy + non-mutating smoke)
RELEASE-A5-1 COMPLETE      (frontend Draft PR #81)
PR #81 = OPEN / DRAFT

RELEASE-A5-2 NOT YET       (frontend Ready + squash merge + deploy)
RELEASE-A6   NOT YET       (controlled real payment smoke)
```

---

## 18. 문서 검증 note

- 모든 SHA는 GitHub 실측(PR #313 9커밋·PR #81 8커밋). PR 번호: tai-api #313(merged), tai-admin #81(open/draft).
- production 실측 반영: tai-api main `b2082bb`(deploy SUCCESS) · `saas_tier_upgrade_transitions`(25 cols·RLS·row 0) · smoke 403/403·side-effect 0.
- secret 값 노출 = 0 · 금융정보 하드코딩 = 0 · 미완료(A5-2/A6/frontend merge/deploy)를 COMPLETE로 표기하지 않음.
