---
class: records
type: report
scope: knowledge
project: chem
title: OBJ-CHEM web enumeration source contract and rights gate
version: 1
status: active
owner: taiwang
---

# CHEM-ENUM-GATE-01 — KOSHA Web Enumeration Source Contract & Rights Gate

```text
CHEM-ENUM-GATE-01 = IN_PROGRESS (GPT review before merge)
CHEM-01 = CLOSED / PASS_WITH_INGEST_GATE
CHEM-02 = DONE / CLOSED
CHEM-03 = CLOSED / CONDITIONAL
CHEM-04 = NOT OPENED
```

This work order does **not** reopen CHEM-03. It does **not** open CHEM-04. It answers one question:

```text
May TAI Safe use
MSDSInfo/mgr/hub/chemList.do
as the first/periodic chemId identity enumeration source?
```

It does **not** ask whether TAI may copy web MSDS body text into the product.

---

## 0. Revision guard

```text
CHEM-03 canonical SHA =
bd839888825b0d33f50a4ab1dae049ced3b0a1a2
authorized base / origin/main at branch create =
9a8d169bf6f24ec2505281add8ed3fbe145dcf7e
delta vs CHEM-03 =
1 commit, test(e2e) Appendix3 Frozen112 runner only
CHEM impact =
NO
branch =
research/chem-enum-gate-01
```

---

## Report card

```text
OFFICIAL GUIDE getChemList searchWrd required = YES
OFFICIAL GUIDE getChemList searchCnd required = YES
documented ALL mode                           = NO
documented bulk/index                         = NO
R1 OPENAPI DATA RIGHTS                        = CONDITIONAL
R2 WEBSITE MACHINE ACCESS                     = CONDITIONAL
R3 IDENTITY METADATA REUSE                    = CONDITIONAL
R4 MSDS CONTENT REPUBLICATION                 = CONDITIONAL (not approval target)
WEB ENUMERATION TECHNICALLY POSSIBLE          = YES
chemId visible and deterministic              = YES (sample pages)
WEB_ENUMERATION_GATE                          = CONDITIONAL
external inquiry needed                       = YES
inquiry sent                                  = NO
full crawl                                    = NO
Stage C bounded probe                         = NOT RUN (R2+R3 not CLEAR)
production mutation                           = 0
migration applied                             = NO
FULL_OFFICIAL                                 = BLOCKED
CHEM-04                                       = NOT OPENED
```

---

## 1. Official API Guide frozen facts

Owner-supplied official document (GPT-read, frozen input to this WO; HWP not re-parsed here):

```text
한국산업안전보건공단_물질안전보건자료_오픈API활용가이드.hwp
dataset 15157612
```

### getChemList

```text
function     = 화학물질목록
searchWrd    = REQUIRED
searchCnd    = REQUIRED
searchCnd    = 0 국문명 / 1 CAS / 2 UN / 3 KE / 4 EN
pageNo       = optional
numOfRows    = optional
```

Absent from the official guide (frozen):

```text
ALL search mode
searchCnd=ALL
blank search = all
getAllChemList
dump-all / bulk index / updated-since
```

```text
DOCUMENTED_OPENAPI_FULL_ENUMERATION = NO
```

This matches CHEM-01/03 swagger: `getChemList` + `getChemDetail01`–`16` only. `searchWrd=""` remains `totalCount=0` (CHEM-01; not re-probed).

---

## 2. API enumeration limitation

Canonical hydration architecture is **unchanged**:

```text
identity enumeration
        ↓
chemId  (text, preserve leading zeros, e.g. "000001")
        ↓
getChemDetail01~16
        ↓
TAI catalog
```

OpenAPI cannot supply the first arrow. That is why this Gate exists. CHEM-02 client/schema/hash/snapshot model is frozen and was not edited.

---

## 3. KOSHA web rights evidence

Official pages only.

| # | source | measured |
|---|---|---|
| 1 | `MSDSInfo/main/popup2.do` 이용 동의서 | MSDS는 작성·검토 **참고용**. 산안법 제110조 작성 의무는 제조·수입자. 법적 문제 공단 면책. 동의서 본문은 **자동수집 허가 문구 없음**. |
| 2 | `MSDSInfo/kcic/msdssearchMsds.do` MSDS검색 고지 | 유통 MSDS는 제조·수입·판매자로부터 받을 것. 공단 MSDS는 참고용. **「공단의 MSDS는 상업적 용도 등의 외부적인 용도로 사용하는 경우 저작권법 등 관련법규에 위배될 수 있음」**. 검색 전 이용동의 체크 필요 (`alert` 존재). 「현재 20,568종의 화학물질에 대한 MSDS 서비스 중」= WEB_ADVISORY. |
| 3 | `MSDSInfo/kcic/copyright.do` 저작권정책 | 페이지 본문은 환경부 잔여 문구로 비어 있음. 푸터 **Copyright © 2014 KOSHA. All rights reserved.** |
| 4 | `MSDSInfo/robots.txt` | `Use-Agent : *` / `Allow: /`. site-root `robots.txt` = HTTP 404. **Allow는 크롤 로봇 힌트이지 상업적 자동수집 허가문이 아님.** |
| 5 | index / 사이트 푸터 | Open API 활용신청 문의 = **1566-0025 공공데이터포털**. 기계 연계의 공식 창구는 웹 HTML이 아니라 OpenAPI로 안내됨. |
| 6 | KOSHA 메뉴 오픈 API | `https://www.data.go.kr/data/15157612/openapi.do` |

Do **not** treat “공식 웹페이지다 → 자동수집 가능” as a rights conclusion.

---

## 4. API rights vs web rights distinction

| channel | official machine interface? | license label | commercial/external MSDS warning |
|---|---|---|---|
| data.go.kr `15157612` OpenAPI | YES (`getChemList`, `getChemDetail01-16`) | catalog/portal: **이용허락범위 제한 없음**; 무료 | dataset description still: 참고용, 제조·수입자 의무 |
| KOSHA website HTML (`chemList.do`, MSDS검색) | NO published list API | Copyright All rights reserved | **상업적 용도 등 외부 사용 시 저작권법 위배될 수 있음** |

```text
data.go.kr OpenAPI 이용허락
≠
KOSHA 웹사이트 HTML 전체의 자동수집 허가
```

공공데이터포털 이용정책(`ugs/selectPortalPolicyView.do`)은 공공누리 제0유형(자유이용, 상업적 가능) 등을 설명한다. dataset `15157612` 표시는 **「이용허락범위 제한 없음」**이다. 이 라벨을 제0유형과 동일하다고 **이 Gate에서 단정하지 않는다.** 포털 FAQ는 「공공데이터의 제공 및 이용 활성화에 관한 법률」 시행으로 **공공데이터의 상업적 활용이 가능**하다고 안내한다. 그 안내는 **공표된 공공데이터(여기선 OpenAPI 15157612)**에 대한 것이지, `chemList.do` HTML 크롤 허가로 확장하지 않는다.

---

## 5. Web contract

CHEM-03 reused. This WO inspected **2 pages only** (page 1, last). No 2,057-page traversal. No `pageSize=100000000`. No Stage C parse dump.

```text
endpoint     = /MSDSInfo/mgr/hub/chemList.do
render       = server-rendered HTML
form         = POST, hidden listType=msds, pageIndex
GET          = ?pageIndex=N also returns the same page
session      = not required for this popup in these fetches
agreement    = MSDS검색 화면은 동의 체크 필요. chemList.do 팝업 HTML에는 동의 필드 없음
page size    = 10
advisory     = 총 20568건 / 2057 페이지 (this WO page-1/last headers)
row identity = javascript:selectChem('chemId','casNo','chemName')
CAS          = nullable (last-page chemId 047134 cas empty; matches CHEM-01)
lastDate     = 개정일 column present on list
ordering     = not dense chemId 000001…N (page 1 first = 009098)
```

Live/non-frozen (do not freeze arithmetic):

```text
this WO last page (pageIndex=2057): 7 selectChem rows
GPT CHEM-03 independent recheck: 8 rows
CHEM-03 operator observation: 7 rows
```

`WEB_ADVISORY_COUNT` only. `N` remains UNKNOWN.

Technical enumeration (if rights were CLEAR) would be finite pagination + chemId per visible row on sampled pages. That is **not** a rights grant.

```text
chemId가 HTML에 보인다  ≠  자동수집이 허용된다
```

---

## 6. chemId extraction contract (candidate only — not authorized)

Because `WEB_ENUMERATION_GATE ≠ PASS`, this row is a **future** contract sketch, not an ingest license.

```text
source_id     = KOSHA_MSDS
source_key    = chemId          # text, keep leading zeros
cas_no        = nullable
chemical_name = advisory
last_date     = advisory if present
source_page   = enumeration evidence only
identity      = chemId ONLY
```

If later authorized:

```text
KOSHA WEB LIST  → chemId enumeration only
OFFICIAL OPENAPI → getChemDetail01~16
TAI DB          → internal catalog (PUBLIC/REFERENCE; not manufacturer MSDS)
```

Web MSDS body is never the hydration source.

---

## 7. Bounded technical probe

```text
Stage C executed = NO
reason           = R2 and R3 are not CLEAR
max pages crawled = 0 (contract inspection only: 2 pages)
new OpenAPI calls = 0
local probe script = NOT WRITTEN
rows written to DB/files = 0
```

CHEM-01 already has `chemId=001008` (leading zeros), CAS-null `047134`, exact CAS search. Those were not re-called.

---

## 8. Rights verdict R1–R4

Inference-only `CLEAR` is forbidden. Each verdict cites official text.

### R1 OPENAPI DATA RIGHTS = CONDITIONAL

Question: may TAI collect / store / process `getChemList` and `getChemDetail01-16` responses?

Official for:

- Dataset `15157612` is published as OpenAPI for 「목록 및 내용」.
- 이용허락범위 **제한 없음**, 비용 **무료**.
- KOSHA 사이트가 Open API 활용신청을 공공데이터포털로 안내.
- 공공데이터법 체계에서 공표 공공데이터의 상업적 활용이 가능하다고 포털이 안내.

Official against treating it as unlimited SaaS MSDS:

- 같은 dataset description: 「공단에서 제공하는 화학물질정보는 MSDS 작성과 검토 시 참고용으로만」.
- 웹 MSDS검색 고지: 상업적·외부 용도 시 저작권법 위배될 수 있음 (웹 고지이며 OpenAPI 페이지 문장은 아님. 자동 동일시 금지이나 **병행 고지**는 남음).

Not `CLEAR`. Not `BLOCKED` (OpenAPI is the designated paid-free public dataset). CHEM-01 role freeze (`PUBLIC/REFERENCE`, not Legal Engine / not workplace MSDS substitute) remains required if R1 is later used.

### R2 WEBSITE MACHINE ACCESS = CONDITIONAL

Question: may TAI repeatedly fetch `chemList.do` HTML mechanically?

Official for: none that say “기계적 반복 조회 허용”. `robots.txt` `Allow: /` is not a license.

Official against automatic CLEAR: Copyright All rights reserved; no list operation in OpenAPI guide; MSDS 상업적·외부 이용 경고; 기계 연계는 포털 OpenAPI로 안내.

Not `BLOCKED`: no sentence found that says “chemList.do 수집 금지”. Not `CLEAR`.

### R3 IDENTITY METADATA REUSE = CONDITIONAL

Question: may TAI extract only `chemId` from the web list and use it as OpenAPI lookup key?

Official for: `chemId` is the OpenAPI detail key (guide + swagger). Rows expose `selectChem(chemId,…)`.

Official missing: permission to **harvest the full list HTML** as the identity set. Guide still requires `searchWrd`/`searchCnd` for `getChemList`. Visibility ≠ reuse right.

Not `CLEAR`. Not `BLOCKED`.

### R4 MSDS CONTENT REPUBLICATION = CONDITIONAL (not this Gate’s approval target)

```text
공단의 MSDS는 상업적 용도 등의 외부적인 용도로 사용하는 경우
저작권법 등 관련법규에 위배될 수 있음
```

source: `msdssearchMsds.do`. This Gate **does not approve** republication of MSDS body in TAI Safe.

---

## 9. WEB_ENUMERATION_GATE verdict

```text
WEB_ENUMERATION_GATE = CONDITIONAL
method candidate     = KOSHA_OFFICIAL_WEB_IDENTITY_LIST
R2                   = CONDITIONAL
R3                   = CONDITIONAL
full crawl           = NO
```

Acceptance for FULL identity enumerator (A–J):

| clause | status |
|---|---|
| A official KOSHA source | YES (chemList.do) |
| B machine access right CLEAR | **NO** (CONDITIONAL) |
| C metadata reuse right CLEAR | **NO** (CONDITIONAL) |
| D finite pagination | YES on sampled UI |
| E every visible row has chemId | YES on sampled pages |
| F no guessed identity | YES if using selectChem chemId only |
| G pagination deterministic enough | PARTIAL (same last-page ids in samples; live count/rows drift) |
| H acquisition count recordable | WEB_ADVISORY_COUNT only |
| I omission detection | NO official census |
| J source-change audit during enum | NOT DESIGNED |

Because B and C are not CLEAR, **FULL_OFFICIAL enumeration PASS is forbidden.** Technical possibility is not a PASS.

---

## 10. Unresolved items

```text
1. Does KOSHA allow automated chemId harvest from chemList.do for system-to-system seed/re-enum?
2. Allowed request interval / traffic if yes.
3. Separate official bulk/index still NOT_FOUND (CHEM-03).
4. Mapping of portal 「이용허락범위 제한 없음」 to 공공누리 제0유형 = not asserted here.
5. Whether website MSDS copyright warning applies to OpenAPI-stored reference catalog display.
6. Production quota approval = still PENDING_OWNER_ACTION (out of this WO).
```

---

## 11. Inquiry draft — do not send

수신: 한국산업안전보건공단 디지털계획부 / 시스템 이용 042-869-0319, OpenAPI 1566-0025  
데이터: 15157612 OpenAPI 및 `MSDSInfo/mgr/hub/chemList.do`

목적 (좁게):

```text
KOSHA 화학물질정보 사이트의 MSDS 전체 목록 페이지에서 제공되는
chemId / 물질명 / CAS No. 등의 목록 metadata를
TAI Safe가 시스템 간 연계를 위한 OpenAPI 조회 식별자 목록으로
자동 수집하여 사용하는 것이 허용되는지 확인 요청
```

**MSDS 본문 재배포 허가 요청과 섞지 않음.**

```text
1. chemList.do 목록의 chemId 자동열거 허용 여부
2. 최초 약 2만 건 identity seed 목적의 사용 가능 여부
3. 정기 변경감지 목적 재열거 가능 여부
4. 허용되는 호출 간격/traffic 기준
5. 별도의 bulk/index 제공 방식 존재 여부
```

`inquiry sent = NO`

Quota application is **not** this WO’s blocker and is **not** submitted. Order remains:

```text
enumeration PASS → production traffic application → migration/ingest
```

---

## 12. Production boundary

SELECT-only `vwlahtguyggrhvslabax` (this WO):

```text
factory_materials       = 0
master_dangerous_goods  = 49
Graph active edges      = 11,776
Graph evidence          = 11,776
chemical Graph edges    = 0
kosha_msds_chemicals    = NULL (not applied)
```

```text
production DB write          = 0
production migration         = NO
production ingest            = NO
FULL_OFFICIAL snapshot       = NO
public chemical API          = NO
factory-material linking     = NO
Graph chemical enable        = NO
Legal Engine linkage         = NO
OBJ-RISK                     = NOT STARTED
CHEM-04                      = NOT OPENED
CHEM-02 code                 = UNCHANGED
```

Existing tests (no CHEM code change):

```text
python3 -m pytest tests/test_kosha_msds_catalog.py -q --tb=line
```

---

## STOP

```text
WEB_ENUMERATION_GATE = CONDITIONAL
FULL_OFFICIAL        = BLOCKED
next Owner action    = send or refuse the inquiry draft
CHEM-04              = NOT OPENED until this Gate is PASS
```
