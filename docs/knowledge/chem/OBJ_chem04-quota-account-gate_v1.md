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
Q4  Is the 1,000/day cap service-wide or per-endpoint (Detail01–16)?
```

Note per WO §5: Q4 does NOT block the Gate. If public docs don't
resolve service-wide vs per-endpoint, we return `QUOTA SCOPE =
UNVERIFIED` and proceed with Q1–Q3.

## Account-specific state (Q1 / Q2 / Q3)

```text
ACCOUNT-SPECIFIC STATE            = USER_ACTION_REQUIRED
ACCOUNT TYPE                      = UNKNOWN
CURRENT APPROVED DAILY TRAFFIC    = UNKNOWN
OPERATING ACCOUNT TRANSITION      = UNKNOWN
TRAFFIC INCREASE                  = UNKNOWN
```

Reason: `Claude Code` cannot log in to <https://www.data.go.kr> as
the account holder. The values above live behind the authenticated
"마이페이지 → OpenAPI 활용신청 현황" view of the account that owns
the current `KOSHA_SERVICE_KEY` / `DATA_GO_KR_SERVICE_KEY`. Guessing
is forbidden (WO §22 STOP condition). Exit path is **Exit B —
`USER_ACCOUNT_EVIDENCE_REQUIRED`**.

### Minimum Owner-side check (single pass)

Log in to data.go.kr with the account that generated the current
KOSHA service key, then capture **exactly** these values from the
detail screen of the KOSHA MSDS 화학물질정보 OpenAPI activation:

```text
Navigate:
  data.go.kr
  → 마이페이지
  → OpenAPI 활용신청 현황
  → 서비스명: 한국산업안전보건공단_MSDS 화학물질정보서비스
    (data.go.kr dataset id ≈ 15157612)

Capture (screenshot or text, single pass):
  1. 신청 유형 :  개발계정 / 운영계정
  2. 심의 상태 :  승인 / 심의중 / 반려
  3. 활용기간 :  YYYY-MM-DD ~ YYYY-MM-DD
  4. 일일 트래픽 :  <n> 회 / 일
  5. "운영계정 신청" / "트래픽 증가 신청" 버튼 존재 여부
  6. 활용사례 등록 여부  (등록 / 미등록)
```

That single capture closes Q1 / Q2 / Q3 for this Gate.

## Q4 — quota scope (service-wide vs per-endpoint)

```text
QUOTA SCOPE                       = UNVERIFIED
```

Basis: <https://www.data.go.kr>'s KOSHA MSDS 화학물질정보서비스 detail
page publishes a single `일일 트래픽 = 1,000` value in the service
metadata section, without disambiguating whether that number is the
cap of the entire service (all Detail01–16 operations pooled) or
each named operation independently. The prior measurement (HTTP 429
/ resultCode 22) exhausted the cap after a mix of calls but did not
by itself distinguish the two scopes. Since WO §5 permits leaving
Q4 as `UNVERIFIED` and not blocking on it, this value is not
challenged further in this Gate.

Working assumption carried forward (documented, not asserted):

```text
SERVICE-WIDE 1,000/day            = WORKING ASSUMPTION
PER-ENDPOINT 1,000/day            = NOT DOCUMENTED
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

Whether the specific account we hold has that button visible right
now still requires the Owner-side single-pass check above.

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

### 요청 사유 (트래픽 증가 근거)

현재 개발계정 트래픽(1,000/일) 기준으로는 초기 동기화가 사실상
불가능(약 329일 소요)하며, 사업장 안전관리 SaaS로서 데이터의
정확성·현행성 보장을 위해 KOSHA 공식 출처의 초기 동기화가 필요함.
초기 동기화 이후 정상 운영 상태에서의 일일 호출량은 이보다 훨씬
낮으므로, 초기 기간 한정으로 상향된 트래픽을 활용할 계획임.

### 요청 트래픽 (Owner 결정)

Owner가 GPT의 quota target 판정 이후에 확정한다. 참고 목표:

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
CURRENT APPROVED TRAFFIC          = UNKNOWN                       (Q1/Q2)
OPERATING ACCOUNT AVAILABLE       = YES                           (public procedure)
TRAFFIC INCREASE AVAILABLE        = YES on operating account      (public procedure)
PUBLIC MAX TRAFFIC                = NOT_PUBLISHED
QUOTA SCOPE                       = UNVERIFIED                    (Q4)

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

## Verdict

```text
WO-CHEM-04-QUOTA-ACCOUNT-001      = BLOCKED / USER_ACCOUNT_EVIDENCE_REQUIRED
CHANGED FILES                     = 1 (this document)
LIVE API CALL                     = 0
PRODUCTION INGEST                 = 0
DB WRITE                          = 0
MERGE                             = NOT AUTHORIZED (Claude Code does not merge)
NEXT                              = Owner single-pass account-screen capture
                                    → GPT quota target decision
                                    → Owner submits 운영계정 전환 or 트래픽 증가 신청
                                    → after approval, resume official hydration under a future WO
STOP
```
