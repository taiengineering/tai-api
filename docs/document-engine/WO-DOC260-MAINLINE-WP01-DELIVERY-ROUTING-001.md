---
title: WO-DOC260-MAINLINE-WP01-DELIVERY-ROUTING-001
wo: WO-DOC260-MAINLINE-WP01-DELIVERY-ROUTING-001
project: TAI Safe DOC260
status: IMPLEMENTATION_CONTRACT_CORRECTED
prerequisite_gate: PRODUCT_SCOPE_FREEZE — OWNER_APPROVED (2026-11-02)
code_change_authorized: NO
created_at: 2026-11-02
contract_verified_at: 2026-11-02
contract_corrected_at: 2026-11-02
source_branch_note: r2_route_policy.py 및 provision_policy 연결은 Draft PR #752 브랜치에만 존재 — main 미반영
next_gate: GPT_DOC260_MAINLINE_WP01_SOURCE_IV
---

# WO-DOC260-MAINLINE-WP01-DELIVERY-ROUTING-001

기존 문서 화면과 확정된 제공 방식의 공통 연결.

---

## 1. 작업 목표

기존 260종 문서 화면을 재개발하지 않고, 확정된 제공 방식을 기존 공통 기능과 연결한다.

고객에게 표시할 동작은 네 가지다:
1. **웹 작성** (A_INTERNAL 63종) — 기존 편집기 사용
2. **공식 원본** (B_OFFICIAL 13종 조건부) — M6 계약 연결 대상 표시
3. **기존 기능 유지** (U_UNRESOLVED 127종) — 기존 접근 유지
4. **신규 기능 제외** (F_SCOPE_OUT 43+E_EXTERNAL 9+기관전용 2+HOLD 3) — 기존 차단 유지

---

## 2. 현재 소스 상태 — 갭 분석 (2026-11-02 실측)

### 2-A. 이미 연결된 기능 (변경 불필요)

| 기능 | 소스 위치 | 상태 |
|------|----------|------|
| 260종 목록 2-페이지 로딩 | `document_forms_service.py:list_document_forms` | 완료 |
| 카탈로그 상세 조회 | `document_engine_api.py:GET /catalog/{doc_id}` | 완료 |
| `provision_policy` 반환 (API) | `document_engine_api.py:811-822` | ⚠ **Draft PR #752 브랜치에만 존재 — main 미반영** |
| `can_create` 계산 (web_edit 연동) | `document_engine_api.py:813` | ⚠ **Draft PR #752 브랜치에만 존재 — WP-01 포함 금지** |
| 웹 편집기 (A_INTERNAL) | `useDocumentFormsEditor.ts` | 완료 |
| 저장·복원·첨부·서명·출력 | 각 composable | 완료 |
| 자동입력 (사업장) | `useDocumentFormsFactory.ts` | 완료 |
| 원본 버튼 (`file_url` 기반) | `index.vue:759,764` | 완료 — `file_url` 존재 시 표시 |
| POST /documents route guard | `document_engine_api.py:227-237` | ⚠ **Draft PR #752 브랜치에만 존재 — WP-01 포함 금지** |

### 2-B. 미연결 갭 — WP-01 대상

| 갭 | 현재 상태 | 필요한 변경 |
|----|----------|------------|
| G0 | `r2_route_policy.py` 및 `runtime.provision_policy` 연결이 Draft PR #752에만 존재 (main 미반영) | BE 읽기 전용 연결 독립 구현 — PR #752 차단 로직 제외 |
| G0-B | B_OFFICIAL 16종 내 CONDITIONAL 13종 / HOLD 3종 구별 불가 (현재 `route_group=B_OFFICIAL`만 존재) | `r2_route_policy.py`에 `official_status` 필드 추가 |
| G1 | `CatalogRuntime` 타입에 `provision_policy` 미정의 | 타입 필드 추가 |
| G2 | `CatalogOpenResult`에 `OPENED_OFFICIAL_ONLY` 미존재 | 유니온 값 추가 |
| G3 | `openCatalogDetail`이 B_OFFICIAL 분기 미처리 | `route_group` 검사 추가 |
| G4 | `useDocumentFormsEditor`가 `provisionPolicy` 미노출 | computed + return 추가 |
| G5 | `index.vue`가 `OPENED_OFFICIAL_ONLY` 결과 미처리 | 핸들러 + 공식 원본 안내 UI 추가 |

**⚠ 계약 정정 (2026-11-02):** `document_engine_api.py` main은 `provision_policy`를 반환하지 않는다. BE 최소 변경이 필요하다. `can_create` 판단은 main 로직(`availability == "READY_FOR_EDIT"`) 유지.

### 2-C. 제공 방식 데이터 경로 확인 (2026-11-02 실측)

**판정 기준: `doc_id` — `doc_format`은 제공 방식 판정에 사용하지 않는다.**

| 단계 | 위치 | 상태 |
|------|------|------|
| 정책 저장소 | `services/document_engine/r2_route_policy.py:_POLICY` | ⚠ **Draft PR #752 브랜치에만 존재 — main 미반영. 데이터는 유효, 연결 독립 구현 필요** |
| Source SHA256 | `r2_route_policy.py:4` | `0a95c6a238796ab90c4be75afa8516906b6cb71f6e34eb75979057ea524971b0` — PRODUCT_SCOPE_FREEZE 기준 매트릭스와 동일 (데이터 신뢰) |
| API 반환 | `document_engine_api.py` (main) | ⚠ **`provision_policy` 미반환 — `runtime_block`에 해당 필드 없음. G0 변경 필요** |
| FE 수신 | `useDocumentFormsList.ts:openCatalogDetail` | G0 BE 변경 후 `payload.runtime.provision_policy.route_group` 접근 가능 — C2 분기 삽입 위치 |

**그룹 카운트 실측 (`policy_count()`):**

| route_group | 실측 건수 | PRODUCT_SCOPE_FREEZE 일치 |
|-------------|----------|--------------------------|
| A_INTERNAL | 63 | ✓ |
| B_OFFICIAL | 16 | ✓ (CONDITIONAL 13 + HOLD 3) |
| U_UNRESOLVED | 129 | ✓ |
| E_EXTERNAL | 9 | ✓ |
| F_SCOPE_OUT | 43 | ✓ |
| **합계** | **260** | ✓ |

**B_OFFICIAL 16종 구별 (정정):** CONDITIONAL 13종과 HOLD 3종은 `official_status` 필드로 구별한다. FE는 `official_status`를 참조하여 CONDITIONAL은 "공식 원본 등록 대기", HOLD는 "Owner 결정 대기"를 표시한다.

| doc_id | official_status |
|--------|----------------|
| CHEM-015/017, FAC-019/020/022/025/026/027/031/032/033/034/035 (13종) | `CONDITIONAL_APPROVED` |
| FAC-024, FAC-029, OSH-065 (3종) | `HOLD` |

**결론 (정정):** BE 2개 파일 + FE 4개 파일 변경 필요. 신규 API 엔드포인트·DB 변경 없음. PR #752 차단 로직 제외.

---

## 3. 기준 자료

- `DOC260_PRODUCT_SCOPE_FREEZE_260.csv` SHA256: `7bffebdaeb2c2350aca9d8a011afead8e2173a66cae6100790d9965975f3b2c6`
- `DOC260_SCOPE_EXCEPTIONS.md` SHA256: `0dee62cccb243790cf0e07c1f617ce79a539f208308b2464703f0b6802eacc6d`

---

## 4. 구현 범위 분류

### 이번 WP-01에서 변경하는 것

| 파일 | 변경 유형 | 변경 이유 |
|------|----------|----------|
| `services/document_engine/r2_route_policy.py` | `official_status` 필드 추가 (G0-B) | B_OFFICIAL CONDITIONAL 13종 / HOLD 3종 구별 |
| `routers/document_engine_api.py` | `provision_policy` 읽기 전용 연결 (G0) | `can_create` 변경 없음 — main 로직 유지. POST 차단 없음 |
| `vue3/src/utils/document-formsFormat.ts` | 타입 필드 추가 (G1) | `provision_policy`를 타입 안전하게 접근하기 위함 |
| `vue3/src/pages/document-forms/useDocumentFormsList.ts` | 분기 추가 (G2, G3) | B_OFFICIAL 진입 시 편집기 대신 공식 원본 경로로 분기 |
| `vue3/src/pages/document-forms/useDocumentFormsEditor.ts` | computed + return 추가 (G4) | 화면에서 `provision_policy` 참조 가능하게 노출 |
| `vue3/src/pages/document-forms/index.vue` | 결과 핸들러 + 안내 UI 추가 (G5) | `OPENED_OFFICIAL_ONLY` 시 공식 원본 안내 표시 |

### 이번 WP-01에서 변경하지 않는 것

| 항목 | 이유 |
|------|------|
| `document_forms_service.py` | `file_url` 이미 `SELECT *` 포함 |
| `can_create` 판단 로직 (main) | `availability == "READY_FOR_EDIT"` 유지 — PR #752 변경 가져오지 않음 |
| POST /documents 생성 경로 (main) | PR #752 차단 로직 가져오지 않음 — 기존 생성 경로 유지 |
| `useDocumentFormsFactory.ts` | 변경 없음 |
| `useDocumentFormsGenerate.ts` | 변경 없음 |
| `useDocumentFormsRestore.ts` | 변경 없음 |
| `useDocumentFormsFileAttachment.ts` | 변경 없음 |
| `useDocumentFormsSignature.ts` | 변경 없음 |
| `useDocumentLifecycle.ts` | 변경 없음 |
| DB 스키마 | 변경 없음 |
| 새 라우터·새 API | 생성 없음 |
| 260개 개별 분기 | 생성 없음 |

---

## 5. 구현 변경 지점 (상세)

### C0. `r2_route_policy.py` — `official_status` 필드 추가 (G0-B)

**파일:** `services/document_engine/r2_route_policy.py`

```python
# 현재 튜플: (route_group, investment_decision)
# 변경 후: (route_group, investment_decision, official_status)
# official_status = "CONDITIONAL_APPROVED" | "HOLD" | None

# B_OFFICIAL CONDITIONAL 13종 — official_status="CONDITIONAL_APPROVED"
'DOC-CHEM-015': ("B_OFFICIAL", "STOP", "CONDITIONAL_APPROVED"),
'DOC-CHEM-017': ("B_OFFICIAL", "STOP", "CONDITIONAL_APPROVED"),
'DOC-FAC-019': ("B_OFFICIAL", "STOP", "CONDITIONAL_APPROVED"),
# ... (FAC-020/022/025/026/027/031/032/033/034/035 동일)

# B_OFFICIAL HOLD 3종 — official_status="HOLD"
'DOC-FAC-024': ("B_OFFICIAL", "STOP", "HOLD"),
'DOC-FAC-029': ("B_OFFICIAL", "STOP", "HOLD"),
'DOC-OSH-065': ("B_OFFICIAL", "STOP", "HOLD"),

# 그 외 모든 항목 — official_status=None (3항목 tuple → 기본값 처리)
```

`get_provision_policy` 반환 dict에 `"official_status"` 필드 추가:
```python
return {
    "doc_id": doc_id,
    "route_group": route_group,
    "investment_decision": investment_decision,
    "official_status": official_status,   # 추가
    "web_edit_allowed": route_group == _WEB_EDIT_ALLOWED_GROUP,
}
```

**변경 행 수:** 16행 수정 (B_OFFICIAL 항목 튜플 확장) + 1행 추가 (반환 dict)

---

### C0b. `document_engine_api.py` — `provision_policy` 읽기 전용 연결 (G0)

**파일:** `routers/document_engine_api.py`

```python
# 현재 main (변경 없음 유지)
from services.document_engine.r2_route_policy import get_provision_policy  # import 추가

# 카탈로그 엔드포인트 내 — can_create 변경 없음
availability = resolved["availability"]
can_create = availability == "READY_FOR_EDIT"   # ← main 로직 그대로 유지

provision_policy = get_provision_policy(doc_id)  # 읽기 전용 조회 추가

runtime_block = {
    "active_schema_id": resolved.get("active_schema_id"),
    "active_schema_status": resolved.get("active_schema_status"),
    "candidate_schema_id": resolved.get("candidate_schema_id"),
    "candidate_schema_status": resolved.get("candidate_schema_status"),
    "availability": availability,
    "can_create": can_create,                    # ← 변경 없음
    "provision_policy": provision_policy,        # 추가
}
```

**포함하지 않는 것 (PR #752 차단 로직):**
- `web_edit_allowed is not False` 조건을 `can_create`에 연결하지 않음
- POST /documents에 `ROUTE_POLICY_BLOCKED` 422 응답 추가하지 않음

**변경 행 수:** import 1행 추가 + provision_policy 조회 1행 추가 + runtime_block 1행 추가 = 3행

---

### C1. `document-formsFormat.ts` — `CatalogRuntime` 타입 확장

**파일:** `vue3/src/utils/document-formsFormat.ts`
**위치:** 현재 `CatalogRuntime` interface (line 216-223)

```typescript
// 현재
export interface CatalogRuntime {
  active_schema_id: string | null
  active_schema_status: string | null
  candidate_schema_id: string | null
  candidate_schema_status: string | null
  availability: 'READY_FOR_EDIT' | 'PREPARING' | 'NO_SCHEMA'
  can_create: boolean
}

// 변경 후 — provision_policy 필드 추가
export interface CatalogRuntime {
  active_schema_id: string | null
  active_schema_status: string | null
  candidate_schema_id: string | null
  candidate_schema_status: string | null
  availability: 'READY_FOR_EDIT' | 'PREPARING' | 'NO_SCHEMA'
  can_create: boolean
  provision_policy?: { route_group: string; web_edit_allowed: boolean | null } | null
}
```

**변경 행 수:** 1행 추가

---

### C2. `useDocumentFormsList.ts` — `OPENED_OFFICIAL_ONLY` 분기 추가

**파일:** `vue3/src/pages/document-forms/useDocumentFormsList.ts`

**변경 1 — CatalogOpenResult 유니온 타입 (line 26-32):**

```typescript
// 현재
export type CatalogOpenResult =
  | 'OPENED_READY'
  | 'OPENED_PREPARING'
  | 'OPENED_NO_SCHEMA'
  | 'BLOCKED_FACTORY'
  | 'ERROR_CATALOG'
  | 'STALE_ABORTED'

// 변경 후 — OPENED_OFFICIAL_ONLY 추가
export type CatalogOpenResult =
  | 'OPENED_READY'
  | 'OPENED_PREPARING'
  | 'OPENED_NO_SCHEMA'
  | 'OPENED_OFFICIAL_ONLY'
  | 'BLOCKED_FACTORY'
  | 'ERROR_CATALOG'
  | 'STALE_ABORTED'
```

**변경 2 — `openCatalogDetail` B_OFFICIAL 분기 (line 257-265 사이):**

```typescript
// setCatalog 호출 이후, availability 검사 이전에 삽입
const routeGroup = payload?.runtime?.provision_policy?.route_group
if (routeGroup === 'B_OFFICIAL') {
  catalogDetailResult.value = 'OPENED_OFFICIAL_ONLY'
  return 'OPENED_OFFICIAL_ONLY'
}
```

**변경 행 수:** 1행 추가 (타입) + 4행 추가 (분기)

---

### C3. `useDocumentFormsEditor.ts` — `provisionPolicy` computed 노출

**파일:** `vue3/src/pages/document-forms/useDocumentFormsEditor.ts`

**변경 1 — computed 추가 (line 175-180 근처):**

```typescript
// 기존 computed들 다음에 추가
const provisionPolicy = computed(() => catalogRaw.value?.runtime?.provision_policy ?? null)
```

**변경 2 — return 객체에 추가 (line ~637):**

```typescript
// 기존 canCreate 다음에 추가
provisionPolicy,
```

**변경 행 수:** 2행 추가

---

### C4. `index.vue` — `OPENED_OFFICIAL_ONLY` 핸들러 + 안내 UI

**파일:** `vue3/src/pages/document-forms/index.vue`

**변경 1 — `openCatalogDetail` 결과 핸들러 (line ~233):**

```typescript
// 현재
else if (result === 'OPENED_READY' || result === 'OPENED_PREPARING' || result === 'OPENED_NO_SCHEMA') {
  await nextTick()
  generate.resetEditRevision()
  lifecycle.resetDoc()
  lifecycle.resetHistory()
  await lifecycle.loadTransitionRules()
}

// 변경 후 — OPENED_OFFICIAL_ONLY 추가
else if (result === 'OPENED_OFFICIAL_ONLY') {
  // 공식 원본 안내 — 편집기 초기화 없음
  await nextTick()
  lifecycle.resetDoc()
}
else if (result === 'OPENED_READY' || result === 'OPENED_PREPARING' || result === 'OPENED_NO_SCHEMA') {
  await nextTick()
  generate.resetEditRevision()
  lifecycle.resetDoc()
  lifecycle.resetHistory()
  await lifecycle.loadTransitionRules()
}
```

**변경 2 — 입력 폼 섹션 내 공식 원본 안내 표시 (form 섹션 최상단):**

```html
<!-- OPENED_OFFICIAL_ONLY: 공식 원본 안내 패널 -->
<VAlert
  v-if="list.catalogDetailResult.value === 'OPENED_OFFICIAL_ONLY'"
  type="info"
  variant="tonal"
  class="mb-4"
>
  이 문서는 공식 원본 제공 대상입니다.
  승인된 공식 파일이 등록된 후 제공됩니다.
</VAlert>
```

**변경 행 수:** 5행 추가 (핸들러) + 10행 추가 (UI)

---

## 6. 구현 이후 완료 기준

1. A_INTERNAL 63종: 기존 편집기 정상 진입 (`OPENED_READY`/`OPENED_PREPARING`)
2. B_OFFICIAL 16종: 편집기 대신 공식 원본 안내 패널 표시 (`OPENED_OFFICIAL_ONLY`)
3. U_UNRESOLVED 127종: 기존 접근 방식 유지 (`KEEP_EXISTING` — 기존 흐름 그대로)
4. 기존 작성 가능 문서가 새로 차단되지 않음
5. 260개 개별 E2E 생성 없음 — 유형별 대표 경로만 검증
6. DB 변경 0건 / 새 API 엔드포인트 0건 / 새 composable 0개 / `can_create` 판단 로직 변경 0건

---

## 7. 기존 접근 보호 원칙 (구현 중 참고)

- `KEEP_EXISTING 127종`: 별도 분기 코드 없음 — 기존 흐름(availability 기반) 그대로 유지
- `BLOCKED 70종`: `web_edit_policy` 값을 기존 문서 생성 API 차단 조건으로 사용 금지
- PR #752 (197종 작성 차단) 로직 적용 금지
- `provision_policy.route_group`으로만 B_OFFICIAL 분기 — 다른 그룹에 새 차단 추가 금지

### 7-A. BLOCKED 계약 (구현 불변 원칙)

`route_group`이 B_OFFICIAL·E_EXTERNAL·F_SCOPE_OUT·U_UNRESOLVED인 문서는 `provision_policy.web_edit_allowed = false`다. 이 값은 **신규 웹편집 생성의 정책 분류**이며, 고객의 기존 접근 경로를 새로 차단하는 실행 명령이 아니다.

| 금지 행위 | 허용 행위 |
|----------|----------|
| `web_edit_allowed=false`를 기존 편집기 진입 차단 조건으로 사용 | `route_group=B_OFFICIAL`일 때만 `OPENED_OFFICIAL_ONLY` 반환 |
| U_UNRESOLVED·E_EXTERNAL·F_SCOPE_OUT에 새 차단 분기 추가 | availability 기반 기존 흐름 유지 |
| `investment_decision=STOP`을 FE 분기 조건으로 사용 | — |

### 7-C. Draft PR #752 격리 원칙 (구현 중 준수)

Draft PR #752(`feat/doc260-r2-route-binding-001`)는 현재 main 미반영 상태이며, WP-01 구현 시 아래 항목을 포함하지 않는다.

| PR #752 항목 | WP-01 처리 |
|-------------|-----------|
| `can_create = schema_ready and (web_edit_allowed is not False)` | **포함 금지** — main의 `can_create = availability == "READY_FOR_EDIT"` 유지 |
| POST /documents `ROUTE_POLICY_BLOCKED` 422 | **포함 금지** — 기존 생성 경로 유지 |
| `r2_route_policy.py` 전체 파일 | **재사용 가능** — 단, official_status 필드 추가 후 독립 커밋 |
| `provision_policy` 읽기 전용 반환 | **독립 구현** — C0b 범위로 분리 구현 |

PR #752 브랜치는 WP-01 완료 이후에도 별도 Owner 검토 없이 병합하지 않는다.

### 7-B. 법령정보센터 링크 vs M6 공식 원본 구별 계약

현재 `index.vue:759`의 "원본" 버튼은 `item.file_url`이 있을 때 표시되며, `law.go.kr/LSW/flDownload.do?flSeq=...` URL을 새 탭으로 여는 **법령정보센터 직접 링크**다.

| 항목 | 법령정보센터 링크 (`file_url`) | M6 공식 원본 (OFFICIAL_DL) |
|------|-------------------------------|---------------------------|
| 데이터 출처 | `document_forms.file_url` (DB 필드) | M6 플랫폼 파일 저장소 (별도 Gate) |
| 현재 상태 | 일부 문서에 이미 존재 | 공개 미승인 (별도 운영 Gate) |
| WP-01 처리 | 기존 버튼 변경 없음 | 공개 금지 — 별도 Gate |
| `OPENED_OFFICIAL_ONLY` UI | 무관 (별도 섹션) | 공개 승인 후 M6 연결 (WP-03 이후) |

`OPENED_OFFICIAL_ONLY` 안내 패널은 "M6 공식 원본이 아직 미등록·미공개"라는 상태를 표시하는 것이며, `file_url` 존재 여부와 무관하다. 두 상태를 혼동하여 `file_url`을 M6 원본 공개 완료의 조건으로 사용하지 않는다.

---

## 8. 실행 및 종료 통제

**현재 상태:** SOURCE_IV_PASS / **NEXT_GATE = OWNER_PR_AND_MERGE_APPROVAL**

정정 이력:
- 2026-11-02 초안: 데이터 경로 Section 2-C + BLOCKED 계약 7-A + file_url vs M6 계약 7-B 추가
- 2026-11-02 GPT IV 정정: r2_route_policy.py 및 provision_policy가 Draft PR #752에만 존재 확인 → Section 2-A 3항목 정정, Section 2-B G0/G0-B 추가, Section 2-C 정정, Section 4 BE 2개 파일 추가, Section 5 C0/C0b 추가, Section 7-C PR #752 격리 원칙 추가
- 2026-11-02 R1 보정: B_OFFICIAL + can_create=true → 기존 편집 경로 유지 (DOC260_SCOPE_EXCEPTIONS 준수)
- 2026-11-02 GPT SOURCE IV PASS: SHA256 일치, 코드 정합성 독립 확인, 10/10 테스트 PASS

최종 커밋:
- tai-api HEAD: `8eab4267` (feat/doc260-wp01-delivery-routing)
- tai-admin HEAD: `468ee883` (feat/doc260-wp01-delivery-routing)
- 증거 ZIP SHA256: `568602d3e73561361de7fbfea56bf38eb32c226c34229458087c829b2fb277d7`

남은 Gate:
- Push / PR 생성 / 병합: **Owner 승인 후 실행**
- 운영 DB 변경 금지 / 배포 금지
- 공식서식 공개 금지
- PR #192·#752 작업 재개 금지

SOURCE IV 완료 후: WP-02 (자동입력 연결 누락 부분) — 기존 자동입력 기능 재개발 없음.

**다음 Gate:** `GPT_DOC260_MAINLINE_WP01_SOURCE_IV`
