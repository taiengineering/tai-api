# M004 WEB 48종 API 원본 출처 정합 보고서

> WO: WO-TAI-M004-WEB-48DOC-API-SOURCE-ALIGN-001  
> 작성일: 2026-10-23  
> 교정일: 2026-10-23 (CORR-001 — 필드 수·소스 분포·law_ref 커버리지 수치 교정)  
> 작성자: Claude Code — GPT 독립검증 대기  
> 전제: 신규 API 수집·서식 제작 금지 / ACTIVATION_SQL 변경 없음 / PROD_DB_WRITE=0

---

## CORR-001 교정 이력

| 항목 | 초판 값 | 교정 값 | 교정 근거 |
|---|---|---|---|
| 총 필드 수 | 90 | **245** | SNAPSHOT CSV ast.literal_eval 재파싱 (초판: json.loads 파싱 오류로 과소 산출) |
| required_fields.source 분포 | `'법정'` 전건 | 법정=186/KOSHA=36/고용노동부지침=13/공인기관지침=7/지침=3 | 동일 파싱 |
| law_ref 커버리지 | 기재 없음 | 조문번호 명시=145/186, 법령명만=41/186 | 동일 파싱 + 정규표현식 분류 |

---

## C1. 기존 API 수집 원본 추적

### 수집 API 및 제공기관

| 항목 | 내용 |
|---|---|
| **API 명칭** | 법제처 국가법령정보 공개 API |
| **제공기관** | 법제처 (Ministry of Government Legislation) |
| **엔드포인트** | `law.go.kr` (법령 원문 조회 + 서식 파일 다운로드) |
| **수집 파이프라인** | `routers/law_collector.py` / `scripts/collect_*.py` / `scripts/collect_form_templates.py` |
| **적재 테이블** | `law_master` / `law_article` (법령 원문) / `form_templates` (법정서식 HWP) |

### WEB 48종의 API 수집 결과

| 항목 | 결과 |
|---|---|
| `document_forms.file_url` 등록 | **0/48** — 연결된 원본 파일 없음 |
| `form_templates` 등재 여부 | 해당 없음 — NON_LEGAL이므로 법정서식 번호 없음 |
| 법제처 HWP 다운로드(`flDownload.do?flSeq=`) | **해당 없음** — 5건의 `flSeq` URL은 INSPECTION_SOURCE 15종에 속함 |
| `required_fields.source` 분포 | 법정=186 / KOSHA=36 / 고용노동부지침=13 / 공인기관지침=7 / 지침=3 |
| 법령 원문 수집 여부 | YES — `law_master`/`law_article` DB에 조문 원문 보유 (법제처 API 경유) |

### 핵심 발견 — NON_LEGAL COPY_OK/DIGITAL_OK 서식의 성격

**WEB 48종은 법제처에서 서식 파일(HWP/PDF)을 다운로드한 것이 아니다.**

이 문서들의 `doc_format` 분포:

| doc_format | 건수 | 의미 |
|---|---|---|
| `COPY_OK` | 40 | 법정 형식 없음 — 사업장이 자체 서식 사용 가능 |
| `DIGITAL_OK` | 8 | 전자 서식 허용 — 지정 서식 불필요 |

`COPY_OK`/`DIGITAL_OK`는 법령이 서식 양식을 별도로 지정하지 않고 **기재 항목(내용)만 규정**하는 경우다.  
TAI는 법령 원문 및 각종 지침에서 필수 기재 항목을 분석하여 `required_fields`를 설계했다.

---

## C2. 원본과 문서엔진 정합성

### 실제 연결 경로

```
법제처 국가법령정보 API (법령 원문 조회)          ← 법정 186필드
KOSHA 지침 / 고용노동부지침 / 공인기관지침         ← 비법정 59필드
   ↓
법령·지침 조문 분석 (TAI 내부 — law_ref 기준)
   ↓
TAI 내부 서식 설계
  └ required_fields[].field_key     ← 기재 항목 → 엔진 필드 키
  └ required_fields[].source        ← 출처 유형 (법정/KOSHA/고용노동부지침 등)
  └ required_fields[].law_ref       ← 조문 참조
  └ required_fields[].is_mandatory  ← 필수/선택
   ↓
document_forms.required_fields
  (DOCUMENT_FORMS_260_SNAPSHOT.csv — 2026-10-기준 DB 스냅샷)
   ↓
document_schema_candidate
   ↓
runtime_form_schema
   ↓
runtime_field (field_key, status, required_status)
   ↓
WEB 서식작성 엔진
```

### 필드 정합성 확인 결과

| 검증 항목 | 결과 | 비고 |
|---|---|---|
| 스냅샷 커버리지 | **48/48** | DOCUMENT_FORMS_260_SNAPSHOT.csv에 전건 포함 |
| `FIELD_COUNT_MATCH` | **YES 48/48** | runtime_field 수 = 스냅샷 spec 수 일치 |
| 총 필드 수 | **245건** | WEB48 전체 (문서당 2~10필드) |
| `RUNTIME_FIELD_KEYS_VERIFIED` | **NO 48/48** | P0 field_key 대조 미실시 |
| `FORM_SOURCE_TYPE` | `SNAPSHOT_REQUIRED_FIELDS` (48/48) | 스냅샷이 출처 |
| `FORM_SOURCE_REFERENCE` | `DOCUMENT_FORMS_260_SNAPSHOT.csv` (48/48) | — |

### 소스별 필드 분포

| source | 필드 수 | 비율 | 원본 위치 |
|---|---|---|---|
| `법정` | **186** | 75.9% | 법제처 API → `law_article` DB |
| `KOSHA` | **36** | 14.7% | KOSHA 안전보건지침 — `law_article` DB 미적재 |
| `고용노동부지침` | **13** | 5.3% | 고용노동부 행정지침 — `law_article` DB 미적재 |
| `공인기관지침` | **7** | 2.9% | 공인기관 지침 — `law_article` DB 미적재 |
| `지침` | **3** | 1.2% | 유형 미특정 지침 — `law_article` DB 미적재 |
| **합계** | **245** | 100% | — |

### 법정 필드 law_ref 커버리지

| law_ref 분류 | 필드 수 | 고유 참조값 수 |
|---|---|---|
| 조문번호 명시 (제N조·시행규칙 제N조 등) | **145** | 43개 |
| 법령명만 (조문번호 미포함) | **41** | 14개 |
| **합계 (법정)** | **186** | **57개** |

**조문번호 명시 주요 법령:**  
산안법, 중대재해법·시행령, 안전보건규칙, 건설기술진흥법, 시설물안전법, 전기안전관리법, 화학물질관리법, 석면안전관리법

**법령명만(조문번호 미포함) 예시:**  
`안전보건규칙 거푸집 동바리 관련 조항`, `안전보건규칙 추락방지 관련 조항`, `별표4`, `MSDS 고시` 등

---

## C3. 원본 연결 현황 — 있는 것과 없는 것

### 있는 것 (기존 자료로 확인 가능)

| 자료 | 건수 | 설명 |
|---|---|---|
| `document_forms.required_fields` | 48/48 | 법령·지침 기반 설계 필드 목록. 이것이 설계 근거 원본 |
| `required_fields.law_ref` | 245/245 | 각 필드의 출처 참조 (법정: 조문/법령명, 비법정: 지침명) |
| `law_master`/`law_article` | 법정 186필드 연결 가능 | 법제처 API로 수집된 법령 원문 (law_ref 매핑 대상) |
| `FIELD_COUNT_MATCH=YES` | 48/48 | runtime_field ↔ 스냅샷 수 일치 확인 |

### 없는 것 (별도 확보 불가)

| 자료 | 상태 | 이유 |
|---|---|---|
| 법제처 HWP/PDF 서식 파일 | **해당 없음** | COPY_OK/DIGITAL_OK → 지정 서식 없음 |
| `document_forms.file_url` | **0/48 미연결** | 연결할 원본 파일이 존재하지 않음 |
| KOSHA·지침 59필드 DB 원본 | **미적재** | `law_article`에 KOSHA/행정지침 미수록 — 별도 출처 확인 필요 |
| P0 field_key 대조 근거 | **미실시** | 24건 P0 감사 대상에 WEB48 미포함 |

---

## C4. FORM_CONFORMANCE 검증 경로 재정의

WEB 48종의 `FORM_CONTRACT_UNVERIFIED` 해소 경로는 **INSPECTION_SOURCE 문서의 P0 감사와 다르다.**

| 구분 | INSPECTION_SOURCE (P0 기존) | WEB 48종 (신규 경로) |
|---|---|---|
| 서식 출처 | 법정서식 HWP + 실제 점검 데이터 | 법령 조문·지침 분석 기반 TAI 설계 |
| 검증 방법 | field_key ↔ 형식 항목 1:1 대조 | field_key ↔ 법령/지침 필수기재항목 대조 |
| 근거 문서 | 법제처 HWP (bylseq + flSeq) | `law_article` 조문 + KOSHA/지침 원본 |
| 수행 주체 | TAI (P0 감사) | TAI + LEG(법령 해석) |

**WEB 48종의 FORM_CONFORMANCE 검증 경로:**

- **법정 186필드:** `runtime_field.field_key` 목록이 해당 `law_ref` 조문에서 요구하는 필수 기재항목을 전부 포함하는지 확인 → `law_article` DB 조문 대조
- **비법정 59필드(KOSHA/지침):** 해당 지침 원본에서 요구하는 기재항목과 대조 → `law_article` 외 별도 원본 필요

`NON_LEGAL(법정 지정 양식 없음)`은 `LEG_GATE_REQUIRED=NO`를 자동 의미하지 않는다.  
법령이 서식 양식을 지정하지 않더라도 기재 내용(필수 기재항목)은 여전히 법령·지침에 근거하므로,  
FORM_CONFORMANCE 검증을 위한 법령·지침 해석 범위 승인은 Owner 선결 조건이다.

---

## 완료 보고

```
WO = WO-TAI-M004-WEB-48DOC-API-SOURCE-ALIGN-001
CORR = WO-TAI-M004-WEB-48DOC-API-SOURCE-CORR-001

TARGET_DOCS = 48
API_SOURCE_IDENTIFIED = 법제처 국가법령정보 공개 API (법령 원문 조회)
API_ARCHIVE_LOCATED = law_master / law_article (DB 보유, 법정 186필드 대상)
DOC_ID_SOURCE_LINKED = 48/48 (document_forms.required_fields ← DOCUMENT_FORMS_260_SNAPSHOT.csv)

ORIGINAL_CONTENT_AVAILABLE = 법령 조문 원문 (law_article DB, 법정 law_ref 기준 연결 가능)
METADATA_ONLY = NO (조문 원문 보유. 서식 파일 없음 — 해당 없음)
SOURCE_LINK_MISSING = file_url 48/48 미연결 (연결 대상 파일 존재하지 않음)

REQUIRED_FIELDS_ORIGIN = TAI 내부 설계 (법령·지침 조문 분석 → field_key 정의)
  TOTAL_FIELDS = 245
  SOURCE_LEGAL      = 186 (75.9%)
  SOURCE_KOSHA      = 36  (14.7%)
  SOURCE_MOEL       = 13  (5.3%)   (고용노동부지침)
  SOURCE_AUTHORIZED = 7   (2.9%)   (공인기관지침)
  SOURCE_GUIDELINE  = 3   (1.2%)   (지침)
  FORM_SOURCE_TYPE = SNAPSHOT_REQUIRED_FIELDS (48/48)

LAW_REF_COVERAGE (법정 186필드):
  ARTICLE_SPECIFIED = 145 (조문번호 명시, 43 고유값)
  LAW_NAME_ONLY     = 41  (법령명만, 14 고유값)
  MISSING           = 0

FIELD_COUNT_MATCH = YES (48/48, 총 245필드)
FIELD_KEYS_VERIFIED = NO (48/48) — 법령 조문 대조 미실시

FORM_CONFORMANCE_PASS = 0
FORM_CONFORMANCE_UNVERIFIED = 48
VERIFICATION_PATH_LEGAL    = 법령 조문 대조 (field_key vs law_article 필수기재항목, 186필드)
VERIFICATION_PATH_GUIDELINE = 지침 원본 대조 (field_key vs KOSHA/지침 기재항목, 59필드)

NEW_API_COLLECTION = NO
NEW_FORM_CREATION = NO
ACTIVATION_SQL_CHANGED = NO
PROD_DB_WRITE = 0
DEPLOY = NO

RESULT_COMMIT = PENDING
GPT_IV = PENDING
```

---

## Owner 참고 사항

WEB 48종의 `FORM_CONTRACT_UNVERIFIED` → `FORM_CONFORMANCE_PASS` 전환 경로:

**법정 186필드 (law_article DB 대조):**

1. 각 문서의 `required_fields.law_ref` 조문을 `law_article` DB에서 조회
2. 조문이 규정하는 필수 기재항목 목록 추출
3. `runtime_field.field_key` 목록과 1:1 대조
4. 전건 일치 시 해당 필드 `FORM_CONFORMANCE_PASS` 판정 가능

**비법정 59필드 (KOSHA/고용노동부지침/공인기관지침):**

1. 출처 지침 원본 확보 (KOSHA 안전보건지침, 고용노동부 고시·지침 등)
2. 지침이 요구하는 기재항목 목록 추출
3. `runtime_field.field_key` 목록과 대조

HWP 파일 없이 진행 가능하며, Owner가 법령·지침 해석 범위를 사전 승인하는 것이 선결 조건이다.  
`NON_LEGAL` 분류는 법정 지정 서식이 없음을 의미할 뿐, 법령·지침 내용 검증 생략 근거가 아니다.
