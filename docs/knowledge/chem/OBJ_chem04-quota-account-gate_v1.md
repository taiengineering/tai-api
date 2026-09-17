---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-04-QUOTA-ACCOUNT-001 data.go.kr KOSHA MSDS quota / account gate
version: 1
status: active
owner: taiwang
---

# WO-CHEM-04-QUOTA-ACCOUNT-001 — KOSHA MSDS Quota / Account Gate

## Scope

```text
DELTA ONLY
DOCS ONLY
LIVE API CALL           = 0
DB WRITE                = 0
PRODUCTION INGEST       = 0
CANONICAL MUTATION      = 0
CONTENT ANALYSIS        = 0
IDENTITY ANALYSIS       = 0
HYDRATION DESIGN        = 0
```

Superseded WO (not re-executed):

```text
WO-CHEM-04-OFFICIAL-HYDRATION-DESIGN-001  = CANCELLED / DO NOT EXECUTE
```

## Governance role

```text
GPT           = design / semantic authority / quota target decision
Claude Code   = account/procedure investigation, deterministic quota
                math, application draft, docs
User (Owner)  = external account changes, formal application submit,
                approval
```

## Frozen inputs (reused verbatim, NOT reverified)

```text
official current chemId          = 20,568
secondary identity rows          = 48,963
official ∩ secondary             = 18,478
SECONDARY_COMPLETE               =  9,124
SECONDARY_PARTIAL                =  9,354
SECONDARY_MISSING                =  2,090

STRICT_FULL_OFFICIAL calls       = 329,088
STRUCTURAL_DELTA calls           =  51,940
```

Option-A closure (2026-09-18 KST, PR #359 merged):

```text
POLICY              = OPTION A APPROVED
SECONDARY AUTHORITATIVE = NO
AUTHORITATIVE SOURCE = KOSHA OFFICIAL only
PR #359 merge commit = eaf199602770bf6fbcc524a356673723422dcd07
```

Prior quota measurement (2026-09-14, frozen):

```text
HTTP                    = 429
resultCode              = 22
meaning                 = 일일 트래픽 허용량 초과
root cause              = DAILY SERVICE TRAFFIC LIMIT

auth key format issue   = NO EVIDENCE
parameter issue         = NO EVIDENCE
```

## The four questions this Gate closes

```text
Q1  Current account type?              (Development / Operating)
Q2  Current approved daily traffic?    (n / day)
Q3  Operating-account transition or traffic increase available?
Q4  Is the portal-displayed per-operation cap enforced service-wide or per-endpoint?
```

Note per WO §5: Q4 does NOT block the Gate. If public docs don't
resolve service-wide vs per-endpoint, we return `QUOTA SCOPE =
UNVERIFIED` and proceed with Q1–Q3.

## Account-specific state (Q1 / Q2 / Q3) — Owner-confirmed 2026-09-18

```text
ACCOUNT-SPECIFIC STATE            = CONFIRMED
ACCOUNT TYPE                      = DEVELOPMENT
STATUS                            = APPROVED
VALID                             = 2026-09-17 ~ 2028-09-17

CURRENT APPROVED DAILY TRAFFIC    = 2,000 / day  (portal displayed, per operation)
OPERATING ACCOUNT TRANSITION      = AVAILABLE
TRAFFIC INCREASE                  = AVAILABLE (on operating account)
```

Portal display captured from Owner's `data.go.kr → 마이페이지 →
OpenAPI 활용신청 현황 → 한국산업안전보건공단_MSDS 화학물질정보서비스`:

```text
getChemList001                    = 2,000 / day
getChemDetail011                  = 2,000 / day
getChemDetail021                  = 2,000 / day
...                               = ...
getChemDetail161                  = 2,000 / day
```

Runtime enforcement scope of the portal-displayed value (whether
each operation truly has its own 2,000 bucket, or the number is
displayed per-op but enforced service-wide) is **still**
unverified. It will be measured by the next hydration WO under a
fail-closed policy (see §Runtime measurement plan below).

```text
PORTAL DISPLAY PER OPERATION      = CONFIRMED
RUNTIME ENFORCEMENT SCOPE         = TO BE MEASURED
```

## Q4 — quota scope (service-wide vs per-endpoint)

```text
QUOTA SCOPE                       = UNVERIFIED
```

Basis: `data.go.kr`'s activation-status detail page displays a
per-operation daily traffic number (2,000 / day for the account
that owns the current service key, per the Owner capture in
§Account-specific state). It does not disambiguate whether the
underlying gateway enforces that quota per operation
independently or pools it across the whole service. The prior
measurement (2026-09-14 HTTP 429 / resultCode 22) exhausted the
cap after a mix of calls but did not by itself distinguish
between the two enforcement scopes. Per WO §5, `QUOTA SCOPE =
UNVERIFIED` is accepted and does not block the Gate.

The next hydration WO will resolve this by observation:

```text
Runtime measurement plan
  do NOT pre-stop at 2,000
  DO fail-closed at HTTP 429 or resultCode 22 or 23
  save a checkpoint at the point of first quota-hit
  next quota window: resume from checkpoint
```

Working assumption carried forward (documented, not asserted):

```text
PORTAL DISPLAY (per operation)    = 2,000 / day
SERVICE-WIDE 2,000/day            = TO BE MEASURED
PER-ENDPOINT 2,000/day            = TO BE MEASURED
```

Owner may verify this in the same pass via the "제공기관 문의" /
"이용안내" section of the same activation screen or by direct
inquiry to KOSHA; the Gate does not require it.

## Public procedure evidence (Q3 — non-account scope)

Reference: <https://www.data.go.kr>의 OpenAPI 활용신청 및 트래픽
증가 절차 공지에 명시된 내용을 정리한다. 이는 KOSHA MSDS 서비스에만
특화된 것이 아니라 data.go.kr 전체 공통 규정이다.

```text
개발계정 → 운영계정 전환:
  * 활용사례 등록이 요구된다 (사용중인 서비스 URL, 사용 방식,
    사용자 규모 등을 제출).
  * 심의 후 승인/반려.
  * 승인되면 운영계정으로 전환되고, 트래픽 상한이 개발계정 기본값
    (1,000/일)보다 상향된다.

트래픽 증가 신청:
  * 운영계정에 한하여 "트래픽 증가 신청" 메뉴가 열린다.
  * 신청 시 목표 트래픽(회/일), 증설 사유, 사용 규모 근거,
    데이터 활용 목적을 제출한다.
  * 상한값 및 승인 소요일은 서비스 제공기관(KOSHA) 심의 결과에
    따라 결정되며 공식 문서에 명시된 고정 상한은 확인되지 않는다
    (PUBLIC MAX TRAFFIC = NOT_PUBLISHED).

승인 소요:
  * 서비스 제공기관 심의 기간에 의존하며 공식 표준 SLA는 게시
    되어 있지 않다.
```

Values for the return:

```text
OPERATING ACCOUNT TRANSITION      = AVAILABLE (public procedure exists)
TRAFFIC INCREASE                  = AVAILABLE  (운영계정 조건)
PUBLIC MAX TRAFFIC                = NOT_PUBLISHED
```

The Owner has captured the specific account state on 2026-09-18
(see §Account-specific state above). The account is `DEVELOPMENT`
with 2,000 / operation / day displayed, valid 2026-09-17 through
2028-09-17. Operating-account transition and traffic-increase
requests are documented public procedures and are available as a
**fallback** if runtime hydration throughput on the current
DEVELOPMENT account turns out to be insufficient.

## Deterministic quota target math (§10 / §11)

Input:

```text
FULL_OFFICIAL_CALLS = 329,088
```

Required daily quota to finish full official hydration in N days:

```text
N = 7   →  ceil(329088 /   7)  =  47,013 / day
N = 14  →  ceil(329088 /  14)  =  23,507 / day
N = 30  →  ceil(329088 /  30)  =  10,970 / day
N = 60  →  ceil(329088 /  60)  =   5,485 / day
N = 90  →  ceil(329088 /  90)  =   3,657 / day
```

Reverse — days to complete at hypothetical daily caps:

```text
   5,000 / day  →  ceil(329088 /   5000)  =  66 days
  10,000 / day  →  ceil(329088 /  10000)  =  33 days
  25,000 / day  →  ceil(329088 /  25000)  =  14 days
  50,000 / day  →  ceil(329088 /  50000)  =   7 days
 100,000 / day  →  ceil(329088 / 100000)  =   4 days
```

Note: these numbers describe the STRICT_FULL_OFFICIAL scan.
Structural-delta hydration (51,940 calls) reduces every horizon
above by ~6.3× on the same daily quota. Both call totals are
frozen from prior CHEM-04 evidence and are NOT recomputed here.

## Application draft (§12 / §18)

For direct copy into data.go.kr's 운영계정 전환 or 트래픽 증가
신청 form. Owner may adjust wording; **only Owner submits.**

### 서비스명

TAI Safe — 산업안전관리 SaaS

### 목적 (활용 목적)

한국산업안전보건공단(KOSHA)이 공표하는 공식 MSDS(화학물질정보)를
산업안전관리 SaaS 내에서 사업장 화학물질 안전정보로 제공하기
위함. 대상은 KOSHA 공식 current chemId 세트(약 2만 건)이며, 이는
사업장이 사용하는 화학물질을 안전관리 관점에서 정확히 매칭·표시
하기 위한 필수 데이터임.

### 초기 동기화 대상

```text
공식 current chemId  = 20,568
동기화 대상 endpoint = Detail01 ~ Detail16
초기 총 호출 예상값  = 329,088
```

이는 1회성 초기 동기화이며, 매번 전체를 재수집하지 않음.

### 운영 방식 (초기 이후)

```text
공식 current/revision 변경분 중심의 증분 갱신
전체 재수집 = NO
```

### 요청 사유 (트래픽 증가 근거) — FALLBACK ONLY

이 초안은 **즉시 사용 대상이 아니다.** 현재 계정은 개발계정으로
승인 상태이며 포털 표시상 각 operation당 2,000/day가 부여되어
있다. 우선 신 API로 실제 gateway가 허용하는 만큼 수집을 진행하고,
throughput이 초기 동기화(329,088 calls)에 부족하다고 실측될
경우에만 아래 사유를 사용해 운영계정 전환 / 트래픽 증설을
신청한다.

가상 사유 문구 (신청이 필요할 때만 채택):

> 사업장 안전관리 SaaS로서 KOSHA 공식 MSDS의 초기 대량 동기화가
> 필요함. 개발계정 트래픽으로는 초기 동기화 기간이 사업 요구
> 대비 과도하게 길어지므로, 초기 기간 한정으로 상향된 트래픽을
> 활용하고자 함. 초기 이후 정상 운영에서의 일일 호출량은 훨씬
> 낮음.

### 요청 트래픽 (Owner 결정 — FALLBACK ONLY)

즉시 결정할 필요가 없다. 신 API로 실제 gateway가 허용하는
수집량을 먼저 측정한다. 신청이 필요해질 경우 Owner가 GPT의
quota target 판정 이후에 확정한다. 참고 목표:

```text
30일 완료 목표  →  11,000 / day  (여유 30/day)
14일 완료 목표  →  24,000 / day
 7일 완료 목표  →  48,000 / day
```

과장 금지 원칙 (§12): 현재 사용자 규모, 실제 운용 상황을 이보다
크게 서술하지 않는다.

### 활용사례 등록 항목 (개발 → 운영 전환 시)

- 서비스 URL (프로덕션 도메인, 준비되지 않은 경우 stage URL)
- 서비스 개요 (KOSHA 공식 MSDS를 사업장 안전관리 SaaS 내 화학물질
  안전정보로 제시)
- 데이터 활용 방식 (Detail01–16 공식 응답을 화학물질별 화면에
  표시; 자체 사전 계산 결과가 아니라 KOSHA 공식 값을 그대로 인용)
- 제공대상 규모 (현재 실제 규모를 사실 그대로; 없으면 파일럿 단계로)
- 갱신 주기 (초기 1회 대량 동기화 + 이후 증분 갱신)

## Return values

```text
ACCOUNT TYPE                      = DEVELOPMENT                   (Q1, Owner-confirmed 2026-09-18)
STATUS                            = APPROVED
VALID                             = 2026-09-17 ~ 2028-09-17
CURRENT APPROVED TRAFFIC          = 2,000 / operation / day (portal display)  (Q2)
OPERATING ACCOUNT AVAILABLE       = YES                           (public procedure) (Q3)
TRAFFIC INCREASE AVAILABLE        = YES on operating account      (public procedure) (Q3)
PUBLIC MAX TRAFFIC                = NOT_PUBLISHED
QUOTA SCOPE                       = UNVERIFIED                    (Q4, to be measured)

30-DAY REQUIRED DAILY             = 10,970 / day
14-DAY REQUIRED DAILY             = 23,507 / day
 7-DAY REQUIRED DAILY             = 47,013 / day
```

## Not opened by this Gate

```text
official bulk hydration           = NOT STARTED
production ingest                 = NOT STARTED
new hydration planner             = NOT CREATED
new quota bypass / key rotation   = NOT PERFORMED
external form submission          = NOT PERFORMED
CHEM identity / content re-scan   = NOT PERFORMED
```

## Runtime measurement plan (single source of truth)

The current DEVELOPMENT account is APPROVED with a portal-displayed
`2,000 / operation / day`. Whether the underlying gateway enforces
that as an independent per-operation bucket or pools it across the
service is `RUNTIME QUOTA SCOPE = UNVERIFIED` — this is a
measurement question, not a paperwork question.

The next hydration WO runs against the v1.2 endpoints and
measures the real limit by observation:

```text
Do NOT pre-stop at 2,000.
Do fail-closed at:
  HTTP 429
  resultCode 22
  resultCode 23
  explicit gateway quota error
```

At the first quota-hit: save checkpoint, STOP, resume in the next
quota window. If measured throughput is insufficient for the
initial 329,088-call hydration in a reasonable horizon, THEN the
operating-account / traffic-increase draft above is used as
a **fallback** (Owner submits, not Claude Code).

Forbidden regardless of throughput:

```text
quota bypass
key rotation
parallel service accounts
```

## Verdict

```text
WO-CHEM-04-QUOTA-ACCOUNT-001      = PASS / HYDRATION-RUNTIME-MEASUREMENT-READY

Q1 ACCOUNT TYPE                   = DEVELOPMENT
Q2 CURRENT APPROVED TRAFFIC       = 2,000 / operation / day (portal display)
Q3 OPERATING / TRAFFIC INCREASE   = AVAILABLE (fallback, public procedure)
Q4 RUNTIME QUOTA SCOPE            = UNVERIFIED (to be measured)

QUOTA APPLICATION SUBMISSION      = FALLBACK / NOT IMMEDIATE
LIVE API CALL                     = 0
PRODUCTION INGEST                 = 0
DB WRITE                          = 0
MERGE                             = NOT AUTHORIZED (Claude Code does not merge)

NEXT = merge v1.2 API alignment (PR #380)
       → open WO-CHEM-04-OFFICIAL-HYDRATE-V12-001
         (fail-closed at real 429 / rc22 / rc23, not pre-stopped at 2,000)
       → measure runtime gateway limit and either continue on
         DEVELOPMENT account or, only if throughput is insufficient,
         submit the operating-account / traffic-increase draft above
STOP
```
