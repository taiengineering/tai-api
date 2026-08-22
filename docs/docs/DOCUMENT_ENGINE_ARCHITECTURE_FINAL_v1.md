# DOCUMENT_ENGINE_ARCHITECTURE_FINAL_v1

> 작성일: 2026-08-23
> 상태: **ARCHITECTURE BASELINE / APPROVED**
> 선행: DOCUMENT_ENGINE_ARCHITECTURE_DECISIONS_v1.md (의사결정 이력, 유지)
> 성격: 실측 조사 후 재정의된 최종 architecture baseline

```text
PRODUCTION MUTATION = 0
CODE MUTATION       = 0
DB MUTATION         = 0
```

---

## 1. 조사 배경

`WP-RETENTION-01`(safety_inspection_results 보존정책)이 다음 질문에서 막혔다.

> 확정된 문서가 원본 점검 결과 없이 살아남을 수 있는가?

이 질문에 답하지 못하면 `safety_inspection_results` 를 HOT 에서 내릴 수 없고, 따라서 물리설계(파티션 키)도 정할 수 없다.

그래서 문서엔진을 먼저 조사했다. 조사 결과는 **예상과 크게 달랐다.**

---

## 2. Current 3-path Architecture (실측)

문서 생성 경로가 **세 개이며 서로 연결되지 않는다.**

### PATH 1 — activation → PENDING queue → dead end

```text
POST /anonymous-diagnosis          (익명 무료진단, 인증 없음)
  → _create_anonymous_diagnosis_impl()
  → anonymous_diagnosis_results INSERT
  → Document Auto Activation Hook (TASK 23)
      watch_engine.document.activate_documents_for_workflow(
          flow_key   = "law_diagnosis",
          trace_id   = f"diag_{token}",
          tenant_id  = "anonymous",
          actor_id   = "anonymous")
  → runtime_document_activation INSERT
  → generated_document INSERT (status = PENDING)
  → [소비자 없음] ← 여기서 영구 정지
```

### PATH 2 — runtime lifecycle (거의 미사용)

```text
services/document_engine_svc.py

create_document()   → runtime_document_data INSERT (DRAFT, runtime_data_json={})
update_document()   → runtime_data_json 통째 교체 (field_key 검증)
change_status()     → runtime_state_transition_rule 기반 전이
_approval()         → runtime_document_approval 에 snapshot 저장
generate_document() → generated_document INSERT (status="GENERATED")
```

`generate_document()` 는 **PDF 를 만들지 않는다.** 렌더링 호출도 storage upload 도 없고 DB 기록만 남긴다.

### PATH 3 — 즉시 렌더 (유일하게 실제 동작)

```text
routers/document_generate.py (WO-3)

POST /documents/{doc_type}/preview   → HTMLResponse 즉시 반환
POST /documents/{doc_type}/generate  → StreamingResponse(PDF) 즉시 반환
```

`inspection_fetcher` 로 원본을 재조립해 PDF 를 만들어 바로 내려준다.
**DB 저장 0 / storage 저장 0 → 휘발한다.**

---

## 3. 실사용 Row Counts (2026-08-23 실측)

| 테이블 | 행수 | 판정 |
|---|---|---|
| `runtime_document_activation` | **1,540** | 문서 필요 발생 registry — 활성 |
| `generated_document` | **1,543** | 출력 시도 registry |
| `runtime_document_data` | **1** | 문서 실데이터 — 사실상 없음 |
| `runtime_document_approval` | **0** | 승인 기록 없음 |
| `runtime_document_review` | **0** | — |
| `runtime_document_archive` | **0** | — |
| `evidence_vault_link` | **0** | 증거 링크 없음 |
| `runtime_lifecycle_audit_log` | **2** | 사실상 없음 |
| `documents` | **0** | 미사용 |
| `runtime_form_schema` | 323 | 스키마 마스터 |
| `document_type_mapping` | 30 | 매핑 마스터 |
| `document_type_registry` | 8 | 유형 마스터 |

### Storage 객체

```text
form-outputs        0 객체     ← PDF 가 하나도 없다
inspections         0 객체
inspection-images   0 객체
final-reports       0 객체
form-templates      0 객체
form-originals     97 객체 (2026-05-11 마지막)
```

```text
DB ↔ OBJECT LINK = BROKEN
```

`generated_document` 1,543행 중 `storage_path` / `download_url` 이 **전건 NULL** 이다.

---

## 4. PENDING Producer / Missing Consumer

### status 분포

| status | 건수 | 비율 | 기간 |
|---|---|---|---|
| **PENDING** | **1,526** | 98.9% | 2026-05-15 ~ 08-01 |
| GENERATED | 9 | 0.6% | 2026-05-14 ~ 05-16 |
| FAILED | 4 | — | 2026-05-16 |
| TEMPLATE_MISSING | 4 | — | 2026-05-16 |

### Producer 특정

```text
flow_key   = law_diagnosis        1,521건
tenant_id  = anonymous
actor_id   = anonymous
form_code  = STD-INSPECT-001
traces     = 1,521 (진단 1건당 문서 1건, 1:1)
```

무료 진단의 Document Activation Hook 이 producer 이며 **현재도 동작한다.**

### Consumer 부재 증거

```text
generate_document()      status="GENERATED" 로 직접 INSERT — PENDING 미조회
document_generate.py     DB 미접근
pg_cron                  generated_document 관련 job 0
cron_job_master (32건)   문서 처리 job 0
DB trigger               generated_document 대상 0
DB function              generated_document 참조 0
status DEFAULT           'GENERATED' → PENDING 은 명시적 지정
```

```text
PENDING CAUSE = B. ACTIVE PRODUCER / CONSUMER MISSING
```

`generated_document.status = 'GENERATED'` 를 **문서 생성 완료의 증거로 사용하면 안 된다.** GENERATED 9건조차 실제 객체가 없다.

---

## 5. `runtime_document_data` 재정의

### 실측 판정

```text
D. INCOMPLETE HYBRID
```

`runtime_data_json` · `evidence_links` · `version` · `parent_document_id` · `archived_at` 컬럼은 snapshot store 의도를 보여주나, 실사용 1행에 `runtime_data_json` 조차 비어 있어 **어느 역할도 수행하지 않는다.**

### 재정의

```text
runtime_document_data = WORKING DOCUMENT STATE
```

담당 범위:

```text
현재 편집 중인 값
override
draft state
status
working metadata
```

**법적 확정본 저장소로 사용하지 않는다.**

---

## 6. Snapshot Reality

`_approval()` 에 snapshot 로직이 **코드로는 존재한다.**

```python
sb.table("runtime_document_approval").insert({
    "runtime_snapshot":      doc_data.get("runtime_data_json"),
    "evidence_snapshot":     doc_data.get("evidence_links"),
    "source_trace_snapshot": {},          # 항상 비어 있음
    "rollback_available":    True,
})
```

| 항목 | 상태 |
|---|---|
| `runtime_data_json` 복사 | O |
| `evidence_links` 복사 | O |
| `source_trace_snapshot` | **항상 `{}`** — provenance 없음 |
| rendered body | 없음 |
| template_version | 없음 |
| checksum | 없음 |

```text
APPROVAL SNAPSHOT (코드)  = PARTIAL
APPROVAL SNAPSHOT (실행)  = NONE   (approval 0행)
EVIDENCE INDEPENDENCE     = NO     (vault_link 0행)
```

`_audit()` · `_approval()` 은 모두 `except Exception: pass` 로 실패를 은폐한다.

---

## 7. Edit Model 불일치

```text
CURRENT  = FULL CURRENT STATE OVERWRITE
TARGET   = DELTA / OVERRIDE  (D-03)
```

`update_document()` 가 `runtime_data_json` 을 통째로 교체한다.
`version` 은 생성 시 1 고정이며 증가 로직이 없고, `parent_document_id` 를 쓰는 코드가 없다.

**기존 기획 D-03(edit = delta/voucher)과 현재 구현이 불일치한다.**

---

## 8. Reprint Drift Risk = **HIGH**

`inspection_fetcher.fetch()` 가 재출력 때마다 읽는 대상:

| source | mutable | reprint 재조회 | 변경 시 과거 출력 변동 |
|---|---|---|---|
| `safety_inspection_results` | append-only | YES | 항목 추가 시 변동 |
| `safety_inspections` | UPDATE 있음 | YES | 상태 표시 변동 |
| `equipment_assets` | `updated_at` 有 | YES | **자산명·코드·위치 변동** |
| `factories` | `updated_at` 有 | YES | **사업장명·주소·관리자 변동** |
| `companies` | `updated_at` 有 | YES | **회사명·로고·대표자 변동** |
| `users` | `updated_at` 有 | YES | **점검자 이름 변동** |
| `runtime_form_schema`/template | `updated_at` 有 | YES | 레이아웃 변동 |
| `document_type_mapping` | `updated_at` 有 | 간접 | 매핑 변동 |

```text
REPRINT DRIFT RISK = HIGH
```

**모든 source 가 mutable 이고 전부 재조회된다.**
담당자 이름이 바뀌거나 사업장을 개명하면 **과거 점검 문서의 내용이 소급 변경된다.** 법적 증거로서 치명적이다.

---

## 9. document_type Mapping 현황

### 계약

```text
CURRENT MAPPING AXIS = doc_id (법정 서식 코드)
CURRENT TARGET       = doc_type 8종
                       INSP · CHK · EQUIP · TBM · PPE · EDU · APPT · CONLOG
FALLBACK             = 없음
DETERMINISTIC        = NO
```

### 스키마

```text
document_type_mapping  = doc_id, doc_type, doc_detail, source_note, created_at, updated_at
document_type_registry = doc_type, type_label, template_file, fetcher_key,
                         evidence_source, fetcher_status, note
```

`active` flag · `priority` · `fallback` 컬럼이 **없다.**
`source_note` 는 전건 `"문서명기준"` — 수동 분류다.

### 핵심 문제

```text
inspection → document_type 자동 결정 경로가 존재하지 않는다.
doc_type 은 URL path 로 호출자가 지정한다.
  POST /documents/{doc_type}/generate
```

`INSP` 매핑이 4건 있으나 `inspection_id → doc_id` 역방향 경로가 없다.
`doc_detail` 은 EQUIP 에만 채워져 있다(FIRE/ELEC/ELEV/CRANE/BOILER 등 12종).

---

## 10. Option A / B / C 비교

| 항목 | A. Activation+Snapshot | **B. Lazy+Snapshot** | C. Dedicated Pipeline |
|---|---|---|---|
| 변경량 | 中 | **中** | 高 |
| 기존 코드 재사용 | 高(명목) | **中(실질)** | 低 |
| migration risk | 中 | **低** | 高 |
| reprint independence | O | **O** | O |
| retention 호환 | O | **O** | O |
| auditability | 中 | **中** | 高 |
| complexity | 中 | **中** | 高 |

**A 의 문제**: "기존 lifecycle 유지"를 전제하나 `runtime_document_data` 가 1행이라 **유지할 lifecycle 의 실체가 없다.**

**C 의 문제**: activation(1,540)을 살리지만 PENDING consumer 도 없는 상태에서 전체 파이프라인을 신설하는 것은 사실상 새 문서 플랫폼 구축이다. 현 단계에서 과하다.

---

## 11. 최종 선택 — B. Lazy Source + Confirmed Snapshot

```text
DECISION = APPROVED
```

### 근거

1. **PATH 3 가 이미 동작하는 유일한 렌더러**다. lazy assemble 은 구현되어 있어 DRAFT 단계를 그대로 쓸 수 있다.
2. `runtime_document_data` 는 1행이라 A 의 "기존 lifecycle 유지"에 실체가 없다.
3. **`_approval()` 에 snapshot 코드가 이미 있다.** B 는 이를 완성하는 방향이라 처음부터 만들지 않는다.
4. C 는 현 단계에서 위험 대비 이득이 맞지 않는다.

### Architecture Contract

```text
SOURCE
inspection / checklist / factory / company / user / template
        ↓
LAZY ASSEMBLY
        ↓
DRAFT / PREVIEW
        ↓
EDIT OVERRIDE / DELTA
        ↓
EXPLICIT CONFIRM
        ↓
IMMUTABLE CONFIRMED SNAPSHOT
        ↓
PRINT / REPRINT / PDF
```

### 핵심 원칙

```text
DRAFT       = source 를 실시간 조회해서 조립
CONFIRMED   = source 와 독립된 immutable snapshot
REPRINT     = confirmed snapshot 을 우선 사용
PDF         = confirmed snapshot 에서 생성
SOURCE DATA = confirmed 문서 재출력의 필수 의존성에서 제거
```

**확정 전에는 lazy, 확정 후에는 sealed snapshot.**

---

## 12. Confirmed Snapshot Contract

### MUST

```text
document_type
document/version id
template identifier
template version

rendered field values
source evidence values
source evidence identifiers

company snapshot
factory snapshot
equipment snapshot
inspector/user snapshot

legal provenance
source trace

approval metadata
confirmed_at
confirmed_by

document version
snapshot schema version

checksum / hash
```

특히 다음이 나중에 바뀌어도 **과거 문서가 변하지 않아야 한다.**

```text
이름 · 회사명 · 사업장 주소 · 설비명 · 점검자 · template
```

`REPRINT DRIFT RISK = HIGH` 이므로 이는 선택사항이 아니다.

### SHOULD

```text
rendered HTML
evidence link metadata
signature metadata
PDF object reference
```

### 현재 `_approval()` snapshot 의 결함 (보강 대상)

```text
source_trace_snapshot = {}   → 법적 provenance 채워야 함
rendered body 없음           → 확정 시점 렌더 결과 저장 필요
template_version 없음        → drift 방지 필수
checksum 없음                → 무결성 증명 필수
```

현재 `_approval()` 구현은 **참고 구현으로만 보고, 최종 snapshot contract 로 승인하지 않는다.**

---

## 13. PDF / Object Contract

```text
snapshot = canonical evidence/document state
PDF      = derived immutable output
```

PDF binary 를 snapshot JSON 에 넣지 않는다.

`generated_document` 는 향후 최소 다음을 갖추고 **실제 object 존재와 일치**해야 완료로 본다.

```text
snapshot_id
storage_path
checksum
generated_at
generator_version
```

```text
generated_document = OUTPUT JOB / INDEX ATTEMPT
                   = CURRENTLY BROKEN / INCOMPLETE
```

---

## 14. Retention Consequence

```text
Can confirmed document survive without safety_inspection_results?

CURRENT   = NO
TARGET B  = YES
```

B 가 구현되면:

```text
confirmed document        → source result HOT 의존 제거
safety_inspection_results → HOT → COLD/archive 이동 가능
```

단 다음이 남아 있으므로:

```text
HOT/COLD separation = CONDITIONALLY FEASIBLE
```

조건:

```text
1. confirmed snapshot 이 rendered body + source values 를 포함할 것
2. 확정되지 않은 DRAFT 의 source 는 HOT 유지 필요
3. provenance 확보 시 의무별 차등 archive 가능
4. structured archive destination 신설 필요 (현재 NOT AVAILABLE)
```

---

## 15. 3-path 통합 목표 (이번 WP 에서 구현하지 않음)

```text
activation (optional)
      ↓
lazy source assembly
      ↓
working state
      ↓
confirm
      ↓
confirmed snapshot
      ↓
render / output
      ↓
PDF / object
```

---

## 16. Superseded Decisions

| 결정 | 판정 |
|---|---|
| D-02 lazy document assembly | **KEEP** |
| D-03 edit = delta/voucher | **KEEP AS TARGET** (현재 구현 불일치) |
| D-04 storage = edit delta + confirmed snapshot | **KEEP** |
| D-05 explicit final/confirm sealing | **KEEP** |
| **D-09 runtime_document_data legacy 격리** | **REJECT / SUPERSEDED** |

`runtime_document_data` 는 legacy 로 격리할 테이블이 아니라 **working-state 역할로 재사용 가능한 미완 구조**다.

---

## 17. Unresolved Issues

```text
ISSUE-DOC-ENGINE-INCOMPLETE-01
  activation 1,540 / generated 1,543(PENDING 98.9%) /
  runtime_document_data 1 / approval 0 / archive 0 / storage object 0
  = document lifecycle pipeline incomplete & disconnected

ISSUE-DOC-DUAL-PATH-01
  실제로는 3-path. activation queue / runtime lifecycle / direct render
  가 서로 연결되지 않음

ISSUE-DOC-AUDIT-SILENT-FAIL-01
  _audit() / _approval() 이 except: pass 로 실패 은폐

ISSUE-DOC-REPRINT-DRIFT-01
  모든 source 가 mutable + 전부 재조회 → 과거 문서 소급 변경 가능
  REPRINT DRIFT RISK = HIGH

ISSUE-DOC-TYPE-NONDETERMINISTIC-01
  inspection → document_type 자동 결정 없음. 호출자가 {doc_type} 지정.
  deterministic mapping contract 를 별도 WP 에서 정의 필요

ISSUE-GENDOC-STORAGE-PATH-NULL-01
  generated_document 1,543행 전건 storage_path NULL
  생성된 PDF 를 다시 찾을 수 없음
```

### Dependency (다른 WP 소유)

```text
ISSUE-SIR-PROVENANCE-BROKEN-01
  safety_inspection_results → 법령 의무 역추적 경로가 FK 없이 연결
  sir.inspection_set_item_id 62.5% NULL / FK 2곳 부재
  sets.legal_rule_code 2.4%
  → WP-SIR-PROVENANCE-01 소유
  → confirmed snapshot 의 legal provenance 항목에 영향
```

### 조사 중 배제된 것

```text
evidence_normalized (283,175행) / evidence_token (237,892행)
= UNRELATED
  컬럼(part_id, source_span_start/end, canonical_token)이
  법령 조문 토큰 정규화 구조.
  문서엔진의 evidence 가 아니며 문서 lifecycle 과 무관.
```

---

## 18. 종료 판정

```text
WP-DOCUMENT-ARCH-01 = PASS / CLOSED

ARCHITECTURE                 = B. LAZY SOURCE + CONFIRMED SNAPSHOT
CURRENT DOCUMENT INDEPENDENCE = NO
TARGET DOCUMENT INDEPENDENCE  = YES
REPRINT DRIFT CURRENT         = HIGH
RUNTIME_DOCUMENT_DATA         = WORKING STATE
CONFIRMED SNAPSHOT            = NEW CANONICAL SEALED STATE
PDF                           = DERIVED OUTPUT
PENDING CAUSE                 = ACTIVE PRODUCER / CONSUMER MISSING

PRODUCTION MUTATION           = 0
```

---

## 19. 다음 단계

```text
WP-DOCUMENT-ARCH-02
Confirmed Snapshot Contract & Storage Design
```

snapshot 의 물리 구조와 sealing contract 를 먼저 설계한 뒤 코드/DB 작업으로 넘어간다.
**이번 문서는 구현 지시가 아니다.**
