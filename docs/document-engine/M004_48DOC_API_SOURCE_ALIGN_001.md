# M004 WEB 48종 API 원본 출처 정합 보고서

> WO: WO-TAI-M004-WEB-48DOC-API-SOURCE-ALIGN-001  
> 작성일: 2026-10-23  
> 작성자: Claude Code — GPT 독립검증 대기  
> 전제: 신규 API 수집·서식 제작 금지 / ACTIVATION_SQL 변경 없음 / PROD_DB_WRITE=0

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
| `required_fields.source` | `'법정'` (48/48 문서 전 필드) — 법령 조문 근거 |
| 법령 원문 수집 여부 | YES — `law_master`/`law_article` DB에 조문 원문 보유 |

### 핵심 발견 — NON_LEGAL COPY_OK/DIGITAL_OK 서식의 성격

**WEB 48종은 법제처에서 서식 파일(HWP/PDF)을 다운로드한 것이 아니다.**

이 문서들의 `doc_format` 분포:

| doc_format | 건수 | 의미 |
|---|---|---|
| `COPY_OK` | 40 | 법정 형식 없음 — 사업장이 자체 서식 사용 가능 |
| `DIGITAL_OK` | 8 | 전자 서식 허용 — 지정 서식 불필요 |

`COPY_OK`/`DIGITAL_OK`는 법령이 서식 양식을 별도로 지정하지 않고 **기재 항목(내용)만 규정**하는 경우다.  
TAI는 법령 원문에서 필수 기재 항목을 분석하여 `required_fields`를 설계했다.

---

## C2. 원본과 문서엔진 정합성

### 실제 연결 경로

```
법제처 국가법령정보 API (법령 원문 조회)
   ↓
법령 조문 분석 (TAI 내부 — law_ref 기준)
   ↓
TAI 내부 서식 설계
  └ required_fields[].field_key     ← 기재 항목 → 엔진 필드 키
  └ required_fields[].source='법정' ← 법령 근거
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
| 총 필드 수 | **90건** | WEB48 전체 (문서당 2~10필드) |
| `RUNTIME_FIELD_KEYS_VERIFIED` | **NO 48/48** | P0 field_key 대조 미실시 |
| `FORM_SOURCE_TYPE` | `SNAPSHOT_REQUIRED_FIELDS` (48/48) | 스냅샷이 출처 |
| `FORM_SOURCE_REFERENCE` | `DOCUMENT_FORMS_260_SNAPSHOT.csv` (48/48) | — |

### 법령별 분포

| law_ref | 건수 |
|---|---|
| 산안법 (산업안전보건법, 조문 미지정) | 9 |
| 산안법 제38조 | 8 |
| 건설기술진흥법 | 6 |
| 산안법 제25조, 제57조, 제63조, 제64조 등 | 각 1~2건 |
| 소방시설법, 시설물안전법, 고압가스안전관리법, 전기안전관리법 등 | 각 1~2건 |

---

## C3. 원본 연결 현황 — 있는 것과 없는 것

### 있는 것 (기존 자료로 확인 가능)

| 자료 | 건수 | 설명 |
|---|---|---|
| `document_forms.required_fields` | 48/48 | 법령 기반 설계 필드 목록. 이것이 설계 근거 원본 |
| `required_fields.law_ref` | 48/48 | 각 필드의 법령 조문 참조 |
| `law_master`/`law_article` | 연결 가능 | 법제처 API로 수집된 법령 원문 (law_ref 매핑 가능) |
| `FIELD_COUNT_MATCH=YES` | 48/48 | runtime_field ↔ 스냅샷 수 일치 확인 |

### 없는 것 (별도 확보 불가)

| 자료 | 상태 | 이유 |
|---|---|---|
| 법제처 HWP/PDF 서식 파일 | **해당 없음** | COPY_OK/DIGITAL_OK → 지정 서식 없음 |
| `document_forms.file_url` | **0/48 미연결** | 연결할 원본 파일이 존재하지 않음 |
| P0 field_key 대조 근거 | **미실시** | 24건 P0 감사 대상에 WEB48 미포함 |

---

## C4. FORM_CONFORMANCE 검증 경로 재정의

WEB 48종의 `FORM_CONTRACT_UNVERIFIED` 해소 경로는 **INSPECTION_SOURCE 문서의 P0 감사와 다르다.**

| 구분 | INSPECTION_SOURCE (P0 기존) | WEB 48종 (신규 경로) |
|---|---|---|
| 서식 출처 | 법정서식 HWP + 실제 점검 데이터 | 법령 조문 분석 기반 TAI 설계 |
| 검증 방법 | field_key ↔ 형식 항목 1:1 대조 | field_key ↔ 법령 필수기재항목 대조 |
| 근거 문서 | 법제처 HWP (bylseq + flSeq) | `law_article` 조문 (law_ref → law_mst_no) |
| 수행 주체 | TAI (P0 감사) | TAI + LEG(법령 해석) |

**따라서 WEB 48종의 FORM_CONFORMANCE 검증은:**  
`runtime_field.field_key` 목록이 해당 `law_ref` 조문에서 요구하는 필수 기재항목을 전부 포함하는지 확인하는 **법령 대조 작업**이다.

이 작업은 기존 P0 감사와 같이 `law_article` DB 조문과의 대조로 수행 가능하며, HWP 파일 없이 진행된다.

---

## 완료 보고

```
WO = WO-TAI-M004-WEB-48DOC-API-SOURCE-ALIGN-001

TARGET_DOCS = 48
API_SOURCE_IDENTIFIED = 법제처 국가법령정보 공개 API (법령 원문 조회)
API_ARCHIVE_LOCATED = law_master / law_article (DB 보유)
DOC_ID_SOURCE_LINKED = 48/48 (document_forms.required_fields ← DOCUMENT_FORMS_260_SNAPSHOT.csv)

ORIGINAL_CONTENT_AVAILABLE = 법령 조문 원문 (law_article DB, law_ref 기준 연결 가능)
METADATA_ONLY = NO (조문 원문 보유. 서식 파일 없음 — 해당 없음)
SOURCE_LINK_MISSING = file_url 48/48 미연결 (연결 대상 파일 존재하지 않음)

REQUIRED_FIELDS_ORIGIN = TAI 내부 설계 (법령 조문 분석 → field_key 정의)
  source = '법정' (48/48 문서 전 required_fields)
  FORM_SOURCE_TYPE = SNAPSHOT_REQUIRED_FIELDS (48/48)

FIELD_COUNT_MATCH = YES (48/48, 총 90필드)
FIELD_KEYS_VERIFIED = NO (48/48) — 법령 조문 대조 미실시

FORM_CONFORMANCE_PASS = 0
FORM_CONFORMANCE_UNVERIFIED = 48
VERIFICATION_PATH = 법령 조문 대조 (field_key vs law_article 필수기재항목)

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

1. 각 문서의 `required_fields.law_ref` 조문을 `law_article` DB에서 조회
2. 조문이 규정하는 필수 기재항목 목록 추출
3. `runtime_field.field_key` 목록과 1:1 대조
4. 전건 일치 시 `FORM_CONFORMANCE_PASS` 판정 가능

이 작업은 HWP 파일 없이 `law_article` DB만으로 수행 가능하며,  
Owner가 해당 법령 조문 해석 범위를 사전 승인하는 것이 선결 조건이다.

전체 90필드의 대조 가능 여부는 `law_article`에서 해당 `law_ref` 조문이 확보됐는지에 달려 있다.
