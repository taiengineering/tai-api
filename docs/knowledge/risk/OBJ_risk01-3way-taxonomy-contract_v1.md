---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-01 3-way construction taxonomy and risk context contract
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-01 — 3-Way Construction Taxonomy & Risk Context Contract

Cursor recommends. GPT/Owner decides. This WO does not create a TAI taxonomy, ingest production data, or open RISK-02.

```text
WAVE 4
OBJ-CSI   = DONE / CLOSED
OBJ-CHEM  = IN_PROGRESS / TEMPORARY HOLD
            quota reset 후 별도 재개
OBJ-RISK  = IN_PROGRESS
RISK-01   = PASS CANDIDATE (CHG1 provenance freeze)
```

```text
KOSHA MSDS API call     = 0
CHEM PR mutation        = 0
production mutation     = 0
Legal Engine mutation   = 0
Graph mutation          = 0
LLM mapping             = 0
fuzzy auto-accept       = 0
```

---

## Decision questions (first page)

```text
Q1. A/B/C는 동일 코드체계인가?
    NO

Q2. KOSHA 626 taxonomy는 필요한가?
    USEFUL_BRIDGE

Q3. 국가 공종분류는 TAI canonical master로 적합한가?
    REFERENCE_ONLY
    (§37 enum) REFERENCE_CLASSIFICATION

Q4. 위험요소프로파일 자체 taxonomy만으로 충분한가?
    PARTIAL

Q5. TAI canonical process/task taxonomy를 별도로 두어야 하는가?
    YES

Q6. 세 source를 deterministic하게 어느 정도 연결할 수 있는가?
    A→B exact 0.00% / hierarchical 0.00%
    B→A exact 0.00% (공종명) / 5.75% (세부공정명→A name)
    A→C exact 0.87% / hierarchical 0.00%
    C→A exact 37.50% (name-only 공종중) / hierarchical 0.00%
    B→C exact 0.00% / hierarchical 0.00%
    C→B exact 0.00% / hierarchical 0.00%
```

권장 모델: **MODEL D** (TAI canonical process/task 별도, A/B/C는 source mapping).

```text
MODEL D ARCHITECTURE = APPROVED   (WO-RISK-01-CHG1; taxonomy not reopened)
RISK-01              = PASS CANDIDATE
                       pending GPT independent verification of C file provenance
```

---

## 0. Revision guard

```text
repo     = taiengineering/tai-api
branch   = feature/risk01-3way-taxonomy
base     = origin/main @ 8bc144ff
measured = 2026-09-14
```

CHEM branch `feature/chem04-content-local-audit` and PR #359 were not opened, merged, or mutated.

---

## 0.1 Legal boundary (frozen)

```text
TAI Legal Engine = APPLICABILITY / OBLIGATION
OBJ-RISK         = EXPLANATION / DISCOVERY / EXECUTION / REFERENCE
```

금지 (구현하지 않음, 이번 WO에서 설계로도 채택하지 않음):

```text
위험요소프로파일 → 법적 의무 자동생성
위험요소프로파일 → 법령 적용판정
위험요소프로파일 → 법적 위반판정
SOURCE H/M/L     → TAI LEGAL RISK SCORE
```

OBJ-RISK 최종 목적 (이번 WO 미구현):

```text
TAI 사업장 → TAI 공정 → TAI 작업 → 위험요소 Context → 원인 / 피해 / 예방·저감대책
```

Public SEO: `41,239` 또는 `47,559` risk rows를 페이지로 펼치지 않는다. SaaS Context / Graph = PRIMARY.

---

## 1. Q1–Q6 판정 근거 요약

동일 문자열이 보여도 같은 Object가 아니다. Native path exact는 전 방향 0%다.

| 관계 | exact (name) | hierarchical (native path) | 의미 |
| --- | ---: | ---: | --- |
| A→B 공종명 | 0.00% | 0.00% | A 코드 노드명과 KOSHA 공종명이 일치하지 않음 |
| B→A 공종명 | 0.00% | 0.00% | 동일 |
| B→A 세부공정명 | 5.75% | 0.00% | 626행 중 36행. unique 명칭은 6개뿐이며 1:N 가능 |
| A→C 공종중 | 0.87% | 0.00% | A 1722노드 중 15건 이름 일치, 그중 2건은 A 쪽 1:N |
| C→A 공종중 | 37.50% | 0.00% | 48개 (대,중) pair 중 18. unique 명칭 15/39 |
| B↔C 공종/작업 | 0.00% | 0.00% | 공사종류×공종명×세부공정 vs 공종대×공종중×작업프로세스 불일치 |

C 공종중 명칭 일치 15건은 코드 공유가 아니다. A는 W 코드, C는 공종 코드 없음. `명칭 ≠ 코드`.

---

# A source contract

## A. Official identity

```text
informal name used in chat     = 건설표준코드   (NOT official; not used as identity)
official system name           = 건설정보분류체계
official facet measured        = 공종분류 (W, Works)
authority                      = 국토교통부
operator                       = 한국건설기술연구원 / 건설사업정보시스템 CALSPIA
official intro URL             = https://www.calspia.go.kr/portal/intro/introStandard04.do
last listed 고시 on CALSPIA    = 국토부고시 제2015-850호
                                (2015: 건설정보분류체계 적용기준 개정)
measured instrument            = 건설사업정보운용지침【별표】
                                건설정보분류체계 구성 및 활용
                                (제3조, 제4조 및 제5조 관련)
annex PDF producer             = 법제처 국가법령정보센터
annex PDF CreationDate         = 2025-07-01
other facets (REFERENCE ONLY)  = F 시설물 / S 공간 / E 부위 / R 자원(자재·장비·인력)
세분류                         = 한국건설기술연구원 매뉴얼 참조 (이번 WO 미측정)
machine-readable dump          = NOT FOUND (no data.go.kr 공종분류 file, no W API)
download/API                   = PDF annex only
```

CALSPIA 소개 페이지 예시 `W2102:아스팔트 콘크리트 포장`은 별표에서 `32 포장및도로공사 > 321 아스콘포장` 계열로 측정됐다. 소개 페이지 예시 코드와 별표 코드가 한 줄로 같다고 단정하지 않는다.

### Not Source A

```text
CODIL 공종분류
  URL = https://www.codil.or.kr/viewConWrkDtlSch.do?gubun=std
  = 건설공사기준 문서 browse taxonomy
  = REFERENCE ONLY, not CIC W

조달청 표준공사코드
  = different procurement system
  = not used as A
```

CODIL 페이지 본문 재수집은 이번 세션에서 timeout. 사용자 확인(CODIL이 별도 공종분류를 씀) + URL은 기록. CODIL 트리를 A 후보에 넣지 않음.

## A. Schema / tree (measured)

Native structure from annex table and listing:

```text
W code 2-digit  = 대분류 (root)
W code 3-digit  = 중분류 (parent = first 2)
W code 4-digit  = 소분류 (parent = first 3)
세분류/세세분류 = KICT 매뉴얼 (absent from this annex)
```

PDF text extract (`pypdf`) of the 별표:

```text
A nodes                 = 1722
A roots                 = 62
A leaves (4-digit)      = 1287
native code             = YES
native code unique      = YES
native code hierarchical= YES
name distinct           = 1687
name collision groups   = 31
```

명칭 충돌 예: `도로`, `공사용가설도로`가 서로 다른 W 코드에 반복. **A 안에서도 명칭 ≠ 코드.**

Root 샘플:

```text
01 공사일반사항및공사비
02 가설건물 시설물(간접가설공사)
03 본공사성가설공사
11 측량
13 지반조사
21 토공사
23 말뚝공사
25 철근콘크리트공사
27 강구조물공사
32 포장및도로공사
```

Path 예:

```text
21 > (중) > (소)
32 > 아스콘포장 > 표층아스콘   (code 3215)
```

추출 한계 (은폐하지 않음): PDF 텍스트가 표 머리글을 이름에 붙인 행이 있다. 예: `도로배수구조물 - - 대․중․소 분류대․중․소 분류`. 임의 정제하지 않음. 공란(빈 코드 슬롯)만 skip.

```text
A snapshot filename = cic_annex_works.txt   (PDF bytes, .txt suffix)
A bytes             = 1053146
A SHA256            = bef821019cd32ad9512f865d179852652d1f7aa9536be41b68c6e403fe0baa29
```

## A. Rights

법령/행정규칙 별표. data.go.kr `이용허락범위 제한 없음` 라이선스가 아님.

```text
LICENSE              = CONDITIONAL
METADATA INGEST      = ALLOWED
NORMALIZED STORAGE   = UNKNOWN
ORIGINAL FILE STORAGE= ALLOWED   (local working copy; not git)
CUSTOMER DISPLAY     = CONDITIONAL
REDISTRIBUTION       = CONDITIONAL
```

## A. Current / version

```text
current policy = CALSPIA listed 고시 2015-850; measured annex PDF dated 2025-07-01
version policy = 고시/지침 개정 시. 세분류는 KICT 매뉴얼
refresh        = 비정기 개정. file snapshot = latest accepted 별표 PDF
```

---

# B source contract

## B. Official identity

```text
B                         = KOSHA 건설업 공종·세부공정
provider                  = 한국산업안전보건공단
dataset id                = 15087828
official URL              = https://www.data.go.kr/data/15087828/fileData.do
portal filename           = 한국산업안전보건공단_건설업 공종별 세부공정 목록_20210910
local filename            = kosha_construction_process.csv
purpose (portal)          = 위험성평가 체크리스트용 건설업 공종별 세부공정
registered                = 2021-09-10
modified                  = 2025-06-24
update cycle              = 수시 (1회성 데이터)
next register             = (blank)
portal 전체 행            = 626
license                   = 이용허락범위 제한 없음
cost                      = 무료
```

## B. File measurement

```text
encoding           = cp949
delimiter          = comma (csv.reader)
headers exact      = 번호,공사종류,공종명,세부공정명
bytes              = 24795
SHA256             = 8e98fbb66d9e152a03425338d27fc738172cdf6dd5d46a36e7a5a06d80012b91
physical_lines     = 627
parsed rows        = 626
malformed rows     = 0
blank rows         = 0
exact duplicate groups = 0
unique rows        = 626
COUNT_MATCH vs portal 전체 행 626 = YES
```

## B. Schema / tree

```text
공사종류 → 공종명 → 세부공정명
native code present      = NO
native code unique       = N/A
native code hierarchical = NO
B roots (공사종류)       = 6
B mids (공사종류,공종명) = 161
B unique 세부공정명      = 169
B rows                   = 626
```

Roots (facility/project types, not CIC W 대분류):

```text
아파트
빌딩
터널
지하철
교량 및 도로
댐
```

Row counts: 지하철 127, 아파트 116, 빌딩 112, 교량 및 도로 109, 터널 86, 댐 76.

`번호`는 행 순번. 공종/세부공정 코드가 아니다.

## B. Rights

```text
LICENSE              = CLEAR          (portal: 이용허락범위 제한 없음)
METADATA INGEST      = ALLOWED
NORMALIZED STORAGE   = ALLOWED
ORIGINAL FILE STORAGE= ALLOWED        (local; not git)
CUSTOMER DISPLAY     = CONDITIONAL    (출처 표시)
REDISTRIBUTION       = CONDITIONAL    (portal 이용조건 + 출처)
```

## B. Current / version

```text
current policy = latest accepted official CSV = 20210910 filename
version policy = 1회성. 포털 수정일 2025-06-24가 파일 내용 갱신을 증명하지 않음
refresh        = 수시(1회성). 차기 등록일 없음
```

---

# C source contract

## C. Official identity

```text
C                         = 국토안전관리원 위험요소프로파일
provider                  = 국토안전관리원
dataset id                = 15090644
official URL              = https://www.data.go.kr/data/15090644/fileData.do
portal filename NOW       = 국토안전관리원_위험요소프로파일_20260814
local filename            = kalis_risk_profile.csv
관리부서                  = AI전략실
보유근거                  = 설계안전성 검토결과 제출 시 설계 시 도출한 위험요소 프로파일 제출
수집방법                  = 건설공사 안전관리 종합 정보망
registered                = 2021-09-29
modified                  = 2026-08-19
update cycle              = 연간
next register             = 2027-08-27
license                   = 이용허락범위 제한 없음
cost                      = 무료
```

설명문 약 47,000건. 포털 `전체 행` 필드 = 41239. 레거시 baseline 설명 건수 = 55546. **보정하지 않음.**

## C. File measurement

```text
encoding           = cp949
headers            = 19 fields (exact list below)
bytes              = 10914674
SHA256             = 399dbe64dcf1b5d1445fd51e968070dd26e0a40583f8e0afc5e9219839c958c8
physical_lines     = 47563
parsed rows        = 47559
malformed rows     = 0
blank rows         = 0
exact duplicate groups = 5730
exact duplicate extra  = 16863
unique 19-field rows   = 30696
```

Quoted newlines가 있으므로 `splitlines()` 후 컬럼 split은 금지. `csv.reader`로만 파싱.

## SOURCE C CURRENT FILE PROVENANCE

WO-RISK-01-CHG1. Taxonomy 재분석 없음. MODEL D 재검토 없음.

원본 수신 (RISK-01, 2026-09-14 KST):

```text
download source host              = www.data.go.kr
download URL                      = https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000007619214&fileDetailSn=1&insertDataPrcus=N
official download identifier      = atchFileId=FILE_000000007619214
                                    fileDetailSn=1
                                    insertDataPrcus=N
dataset page                      = https://www.data.go.kr/data/15090644/fileData.do
downloaded_at (local mtime)       = 2026-09-14T23:18:44+09:00
local filename                    = artifacts/risk01/source_c/kalis_risk_profile.csv
local bytes                       = 10914674
local SHA256                      = 399dbe64dcf1b5d1445fd51e968070dd26e0a40583f8e0afc5e9219839c958c8
parsed rows                       = 47559
```

당시 curl은 HTTP 헤더를 파일로 남기지 않았다. CHG1에서 **동일 URL을 재요청**해 헤더를 고정하고, 바이트를 로컬 스냅샷과 대조했다.

CHG1 re-download (2026-09-14 14:42:22 GMT):

```text
http_code              = 200
redirects              = 0
url_effective          = https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000007619214&fileDetailSn=1&insertDataPrcus=N
remote_ip              = 27.101.236.55
Content-Type           = application/octet-stream; charset=UTF-8
Content-Length         = 10914674
Content-Disposition    = attachment; filename="2026%EB%85%84 %EC%9C%84%ED%97%98%EC%9A%94%EC%86%8C %ED%94%84%EB%A1%9C%ED%8C%8C%EC%9D%BC.csv"
Content-Disposition decoded = 2026년 위험요소 프로파일.csv
Last-Modified          = (not provided)
ETag                   = (not provided)
re-download SHA256     = 399dbe64dcf1b5d1445fd51e968070dd26e0a40583f8e0afc5e9219839c958c8
SHA256 match vs local  = YES
```

동일 시각 HTML `atchFileId` = `FILE_000000007619214` (페이지에 다른 첨부 id 없음).

```text
FILE AUTHENTICITY CLASS = OFFICIAL_DOWNLOAD_WITH_STALE_PORTAL_METADATA
SOURCE C FILE AUTHENTICITY = PASS
```

판정 이유: 바이트가 `data.go.kr` 공식 `fileDownload.do`에서 HTTP 200으로 내려왔고, 로컬 47559행 스냅샷과 SHA256이 같다. HTTP 파일명은 `2026년 위험요소 프로파일.csv`이고 포털 `파일데이터명`은 `..._20260814`이다. 둘 다 공식 표기이며 어느 쪽으로도 덮어쓰지 않는다.

## PORTAL METADATA DRIFT

포털 숫자와 파일 행수를 맞추기 위해 삭제·합성하지 않는다. 세 층을 분리한다.

### 1. OFFICIAL FILE OBSERVATION (bytes)

```text
portal 파일데이터명 (HTML, CHG1) = 국토안전관리원_위험요소프로파일_20260814
HTTP Content-Disposition name  = 2026년 위험요소 프로파일.csv
rows                           = 47559
SHA256                         = 399dbe64dcf1b5d1445fd51e968070dd26e0a40583f8e0afc5e9219839c958c8
bytes                          = 10914674
```

### 2. PORTAL CATALOG METADATA (GPT independent review, preserved)

GPT가 CHG1 시점에 확인한 공개 catalog/페이지 스냅샷. **삭제하지 않음. 47559로 덮어쓰지 않음.**

```text
portal filename    = 국토안전관리원_위험요소프로파일_20250923
portal rows        = 41239
portal prose count = 55546
portal modified    = 2025-11-20
portal next update = 2026-09-25
catalog JSON cited = https://www.data.go.kr/catalog/15090644/fileData.json
                     alternateName=..._20250923
                     dateModified=2025-11-20
```

### 3. PORTAL / CATALOG remeasure (CHG1, 2026-09-14 14:42 GMT)

현재 공개 HTML + catalog JSON. GPT 스냅샷을 대체하지 않고 **추가 실측**이다.

```text
HTML title / 파일데이터명     = 국토안전관리원_위험요소프로파일_20260814
HTML 전체 행                 = 41239
HTML 설명문                  = 약 47,000건
HTML 수정일                  = 2026-08-19
HTML 차기 등록 예정일        = 2027-08-27
HTML 20250923 문자열         = 0
catalog alternateName        = 국토안전관리원_위험요소프로파일_20260814
catalog dateModified         = 2026-08-19
catalog description count    = 약 47,000건
catalog 55546 / 41239 / 20250923 / 2025-11-20 = ABSENT in current JSON
```

결과:

```text
OFFICIAL FILE OBSERVATION = 20260814 / 47559
PORTAL CATALOG METADATA   = 20250923 / 41239 / prose 55546
CURRENT HTML ROW FIELD    = 41239
CURRENT HTML/JSON NAME    = 20260814
METADATA DRIFT            = YES
CAUSE                     = UNKNOWN
```

파일 원본이 먼저 교체되고 catalog JSON의 `alternateName`/`dateModified`가 뒤늦게 `_20260814` / `2026-08-19`로 따라온 상태와 양립한다. `전체 행=41239`와 GPT가 본 `_20250923` 레코드는 그대로 보존한다.

## C. 41,239 vs 55,546 vs file

```text
PORTAL_DESCRIPTION_COUNT (legacy baseline) = 55546
PORTAL_DESCRIPTION_APPROX (current prose)  = 약 47,000
PORTAL_FILE_ROWS_FIELD                     = 41239
CURRENT_FILE_ROWS                          = 47559
COUNT_MATCH                                = NO
SOURCE_METADATA_DRIFT                      = YES
CAUSE                                      = UNKNOWN
```

약 47,000은 파일 47,559에 가깝지만 공식 필드 41239와는 불일치. 원인 미증명. 숫자를 맞추기 위해 행을 삭제/합성하지 않음.

## C. Actual headers → TAI concept candidates

추측 컬럼을 만들지 않음. 존재하는 19필드만 매핑.

| SOURCE FIELD | TAI CONCEPT CANDIDATE |
| --- | --- |
| 시설물분류(대/중/소) | facility |
| 공종분류(대) | construction_type / work_type |
| 공종분류(중) | work_type |
| 위험발생객체분류(대/중) | object / hazard object |
| 위험발생위치분류(대/중/소) | location |
| 위험발생위치코드(중) | location native code (**not** work code) |
| 작업프로세스명 | process / task |
| 물적피해 | property_damage |
| 인적피해 | human_damage |
| 사고원인 | cause |
| 사고가능성 | likelihood (source native ≠ TAI legal score) |
| 사고심각성 | severity (source native ≠ TAI legal score) |
| 설계단계 | design_control |
| 시공단계 | construction_control |

존재하지 않는 concept (이번 파일 기준):

```text
construction_type native code = NO
work_type native code         = NO
process native code           = NO
subprocess column             = NO
accident_type column          = NO   (사고원인/피해와 별개 컬럼 없음)
```

## C. Schema / tree

Native work taxonomy in this file:

```text
공종분류(대) → 공종분류(중) → 작업프로세스명
```

시설물 대/중/소와 위치 대/중/소는 병행 축. 공종 트리에 병합하지 않음.

```text
C work_big_n              = 7
C work_mid (대,중) pairs  = 48
C work_mid name distinct  = 39
C task (대,중,작업)       = 761
native work code          = NO
native location mid code  = YES (115 distinct, 47559/47559 nonempty)
```

공종대 분포 (row count, 보정 없음):

```text
토목     23922
건축     18899
기타      2741
산업설비  1069
기계설비   523
전기설비   382
통신설비    23
```

같은 공종중 명칭이 서로 다른 공종대 아래 반복된다 (`가설공사`, `철근콘크리트공사`, `지반조사`, `해체 및 철거공사`). Parent path 없이 명칭만으로 C 노드 identity를 정하면 안 된다.

## C. H/M/L (native only)

포털 설명은 H/M/L 문자. 파일 값은 `H(4)`, `M(3)` 형태. **TAI 점수로 변환하지 않음.**

사고가능성 letter: M=33351, H=6211, L=7997. NULL=0, OTHER=0.

사고심각성 letter: M=23925, H=21142, L=2492. NULL=0, OTHER=0.

상위 native 값 (가능성): `M(3)` 18429, `M(2)` 14724, `L(2)` 7253, `H(4)` 3615.

```text
SOURCE H/M/L ≠ TAI LEGAL RISK SCORE
```

## C. Risk profile identity

```text
native row id column     = NO
deterministic identity   = SHA256(all 19 fields joined by U+241F)
hashed_distinct          = 30696
hashed_singleton_rows    = 24966
hashed_collision_groups  = 5730
hashed_duplicate_extra   = 16863
hashed_null              = 0
```

5730 collision group은 **동일 19필드 행의 완전 복제**다. 서로 다른 내용이 같은 해시로 충돌한 것이 아님.

WO §23 조합 (공종대/중, 작업프로세스, 객체대/중, 위치대/중/소, 사고원인, 설계단계, 시공단계):

```text
combo distinct                = 20953
combo groups with repeats     = 4722
combo extra copies            = 26606
semantic-looking duplicates   = NOT_AUTO_CLASSIFIED (no merge)
```

19필드 unique(30696) > combo unique(20953): 시설물·피해·H/M/L만 다른 반복이 있다. 자동 병합 금지.

## C. Rights

```text
LICENSE              = CLEAR          (portal: 이용허락범위 제한 없음)
METADATA INGEST      = ALLOWED
NORMALIZED STORAGE   = ALLOWED
ORIGINAL FILE STORAGE= ALLOWED        (local; not git)
CUSTOMER DISPLAY     = CONDITIONAL    (출처 표시; SEO dump 금지)
REDISTRIBUTION       = CONDITIONAL
```

## C. Current / version

```text
current policy = latest accepted official file = _20260814
version policy = 연간 파일 스냅샷
refresh        = next register 2027-08-27
```

---

# 3-way mapping

허용 정규화만 사용: trim, Unicode NFC, whitespace, known separators (`/·ㆍ・,`). LLM/embedding/fuzzy auto-accept = 0.

비교 key:

```text
name exact     = normalized node name
path exact     = parent path + node name (native hierarchy)
```

Path exact가 0%이므로 같은 문자열 `토공사`도 parent context가 다르면 동일 Object가 아니다.

## Coverage matrix (공종/mid primary)

| | exact % | hierarchical % | ambiguous % | unmatched % |
| --- | ---: | ---: | ---: | ---: |
| A → B | 0.00 | 0.00 | 0.00 | 100.00 |
| B → A | 0.00 | 0.00 | 0.00 | 100.00 |
| A → C | 0.87 | 0.00 | 0.12 | 99.13 |
| C → A | 37.50 | 0.00 | 0.00 | 62.50 |
| B → C | 0.00 | 0.00 | 0.00 | 100.00 |
| C → B | 0.00 | 0.00 | 0.00 | 100.00 |

Secondary leaf/task name layer:

```text
A → B leaf name     exact 0.35%  ambiguous 0.35% (6 A names, each 1:N into B)
B leaf → A name     exact 5.75%  1:1 on those 36 rows; unique names = 6
A → C task          exact 0.00%
C task → A          exact 0.00%
B leaf → C task     exact 0.00%
C task → B leaf     exact 0.00%
```

분류: 이름 일치는 `POSSIBLE_RELATED` 또는 계층 무시 시 과대 `EXACT_EQUIVALENT`가 된다. 이번 WO는 path exact가 0이므로 **canonical mapping으로 승격하지 않음.** C→A 37.5%는 `POSSIBLE_RELATED` (name-only).

## Exact name matches (not codes)

C 공종중 명칭이 A 노드명과 난 것 (15 unique names, 18 pairs):

```text
강구조물공사
교량공사
금속공사
도장공사
말뚝공사
목공사
미장공사
방수공사
수장공사
조경공사
조적공사
지반조사
철근콘크리트공사
터널공사
토공사
```

B 세부공정명 ∩ A 노드명 (6 unique):

```text
리프트
발파
윈치
콘크리트양생
콘크리트타설
타워크레인
```

이들은 장비/활동 명칭 충돌 가능성이 있고, 공종 identity가 아니다.

## Unmatched samples (human review; not auto-mapped)

B 공종명 unmatched in A/C (sample):

```text
PSC교량작업
가설도로작업
가설전기작업
가체절작업
강교설치작업
갱폼작업
거푸집작업
기초파일작업
발파작업
```

C 공종중 unmatched in A (sample):

```text
가설공사
건축 토공사
관공사
기계설비공사
도로 및 포장공사
철골공사
창호 및 유리공사
타일 및 돌공사
```

B는 `~작업` 안전 현장 용어. C는 `~공사` 공종 묶음. A는 W 정보분류 명칭. 세 명명 규칙이 갈린다.

---

# Canonical model recommendation

우선순위 (WO §34):

1. 공식 identity 안정성
2. 현장 process/task 표현력
3. 위험요소프로파일 연결성
4. SaaS 작업 context 적합성
5. 유지보수 가능성
6. 제조업 등 건설 외 확장성

## MODEL A — 국가 공종분류 = canonical

장점: W 코드가 있고 계층적이다. 국가 정보분류.

단점: 안전 작업 grain이 아니다. B 공종명 exact 0%. C 작업프로세스 exact 0%. 건설 전용. 고시 2015 계열 + PDF 추출. TAI 전체 process master로 고정하면 제조업 확장이 막힌다.

유지보수: 고시/별표 재추출. 세분류 매뉴얼 별도.

판정: **REFERENCE_CLASSIFICATION**. Master 아님.

## MODEL B — KOSHA 626 = canonical safety taxonomy

장점: 산안법 위험성평가 체크리스트 용어. `공사종류→공종→세부공정`이 현장 작업에 가깝다.

단점: native code 없음. C와 exact 0%. 6개 공사종류(아파트/빌딩/터널…)는 시설 유형. 1회성 파일. 건설 전용 626행.

판정: **USEFUL_BRIDGE**, master 아님.

## MODEL C — 위험요소프로파일 taxonomy = canonical

장점: OBJ-RISK가 실제로 공급해야 할 객체/위치/원인/피해/저감대책이 이미 붙어 있다. 작업프로세스 761.

단점: 공종 코드 없음. 명칭 비유일. exact duplicate 5730 groups. 행수 메타데이터 drift. 건설 CSI/설계안전성 검토 출처. 공종 트리가 너무 얕다(대 7, 중 48). 제조 확장 불가. H/M/L을 법 점수로 쓰면 Legal Engine 오염.

판정: **risk-context source**, process/task master로는 **PARTIAL**.

## MODEL D — TAI canonical 별도 + A/B/C mapping (권장)

```text
tai_process_id
tai_task_id
      ↑ mapping_type / mapping_confidence / mapping_status
source_system + source_code + source_path
```

장점: 세 source identity를 섞지 않음. 건설 자료로 시작하되 제조 확장을 막지 않음. C row는 risk profile object로 유지. A 코드·B 세부공정은 mapping. Legal Engine과 분리 유지.

단점: 내부 taxonomy 설계/거버넌스 비용. RISK-02 이후 작업.

이번 WO에서 taxonomy를 복사해 TAI라고 부르지 않는다. 위 필드는 설계 후보다.

**권장: MODEL D.**

---

# PASS / BLOCK

```text
SOURCE A official identity    = RESOLVED
SOURCE B official identity    = RESOLVED
SOURCE C official identity    = RESOLVED
A/B/C rights                  = RESOLVED as CONDITIONAL or CLEAR+CONDITIONAL display
A schema/tree                 = MEASURED (PDF extract artifacts preserved)
B schema/tree                 = MEASURED
C schema/tree                 = MEASURED
A↔B coverage                  = MEASURED
A↔C coverage                  = MEASURED
B↔C coverage                  = MEASURED
ambiguous/unmatched           = REPORTED
C row-count drift             = PRESERVED
risk profile identity         = RESOLVED (content-hash; native id absent)
canonical recommendation      = COMPLETE (Cursor recommend / Owner decide)
production mutation           = 0
Legal Engine mutation         = 0
Graph mutation                = 0
```

낮은 mapping coverage는 BLOCK이 아니다. TAI canonical 별도 필요의 증거다.

Hard BLOCK 해당 없음 (공식 identity 확인, 원문 미수정, Legal/production 미오염).

---

# Artifacts (gitignored)

```text
artifacts/risk01/
  source_a/   cic_annex_works.txt (PDF) + cic_annex_extracted.txt
  source_b/   kosha_construction_process.csv
  source_c/   kalis_risk_profile.csv
  schema/     a_works.jsonl b_nodes.jsonl c_work.jsonl c_tasks.jsonl c_field_map.json
  mapping/    coverage_matrix.json unmatched_samples.json
  identity/   c_row_hash.json
  reports/    summary.json
  manifests/  source_snapshots.json
```

대량 원문은 git commit 금지.

분석 도구: `tools/risk01/analyze_3way.py` (deterministic). 테스트: `tests/test_risk01_3way.py`.
