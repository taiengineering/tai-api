# TAM CHEM COMPATIBILITY REVIEW — Contract Acceptance Proposal
# WP-07I C-DEP-02 / C-DEP-03

**Status: TAM OWNER ACCEPTANCE PENDING / DESIGN-ONLY / NO MERGE**
**Document type: DRAFT CONTRACT PROPOSAL — NOT ACCEPTED, NOT IMPLEMENTED, NOT ACTIVE**
**Date: 2026-10-10**
**Repo: taiengineering/tai-api**
**Authority: TAM Owner acceptance and GPT independent verification required before any implementation WO issuance.**

---

## 0. Overall Object Plan and Stage Status

Full CHEM sequence: OBJ00 → OBJ01 → OBJ02 → OBJ03 → OBJ04 → OBJ05 → OBJ06 → OBJ07 → OBJ08 → OBJ09 → OBJ10 → OBJ11 → OBJ12 → OBJ13 → OBJ14 → OBJ15. Parallel/dependency rules follow Master Plan; this document does not alter sequencing.

| Object | Area | Status |
|--------|------|--------|
| OBJ00 | Governance | Prior baseline retained; not reverified here |
| OBJ01 | Asset Census | Prior baseline retained; not reverified here |
| OBJ02 | MSDS Product Master | Prior baseline retained; not reverified here |
| OBJ03 | Company MSDS / Evidence | Prior baseline retained; not reverified here |
| OBJ04 | Intake / Search / Scan | Prior baseline retained; not reverified here |
| OBJ05 | Chemical WMS Core | Prior baseline retained; not reverified here |
| OBJ06 | Purchase / Receiving | Prior completion history retained; not reverified here |
| OBJ07 | Location / Movement | A0 CLOSED FINAL; A1 Design CLOSED FINAL; A1 Implementation NOT AUTHORIZED; A2 BLOCKED; B NOT STARTED; C/D BLOCKED |
| OBJ08 | Issue / Outbound / Disposal | Prior baseline retained; not reverified here |
| OBJ09 | Inventory / Stock Count | Prior baseline retained; not reverified here |
| OBJ10 | Chemical / LEG | Prior baseline retained; not reverified here |
| OBJ11 | TASK / Evidence | Prior baseline retained; not reverified here |
| OBJ12 | WEB | Prior baseline retained; not reverified here |
| OBJ13 | Field APP | Prior baseline retained; not reverified here |
| OBJ14 | Commercial / Entitlement | Prior baseline retained; not reverified here |
| OBJ15 | E2E / Release | Prior baseline retained; not reverified here |

**Scope of this document:** WP-07I C-DEP-02/03 contract proposal only. Does not affect any other OBJ or Stage completion status.

---

## 1. PRE-GUARD Evidence Anchors

The following SHA values were confirmed read-only before document creation. Any subsequent drift must cause this document to be re-evaluated.

| Artifact | SHA / State | Verification |
|----------|-------------|--------------|
| CHEM `taiengineering/tai-chemical` main | `afa58f0388d391881f6f6c3252a549f8390dde9c` | Confirmed at WO execution time |
| CHEM A1 design blob | `42ce95a607083b243c6b841fde9453d2cb156be5` | Confirmed on main post-merge |
| TAM `taiengineering/tai-api` main | `c9c5f2689ef3df030781ba9985750ce9b800f5e4` | Confirmed at WO execution time; this branch base |
| TAM-006 design document | `docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md` at `c9c5f268...` | Read-only source |
| TAM Module Definition | `docs/tam/TAI_TAM_MODULE_DEFINITION_2026-10-10.md` at `c9c5f268...` | Read-only source |

Source links (fixed SHA):
- CHEM A1 design: https://github.com/taiengineering/tai-chemical/blob/afa58f0388d391881f6f6c3252a549f8390dde9c/docs/foundation/CHEM_MGMT_OBJ07_WP07I_A1_REVIEW_OVERRIDE_DESIGN_V1.md
- TAM-006: https://github.com/taiengineering/tai-api/blob/c9c5f2689ef3df030781ba9985750ce9b800f5e4/docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md
- TAM Module Definition: https://github.com/taiengineering/tai-api/blob/c9c5f2689ef3df030781ba9985750ce9b800f5e4/docs/tam/TAI_TAM_MODULE_DEFINITION_2026-10-10.md

**PRE-GUARD result: PASS** — both main SHAs confirmed identical to baseline at time of document creation.

---

## 2. C-DEP-03 — TAM Consumer Registration Proposal

**Status: PROPOSED / TAM OWNER ACCEPTANCE PENDING**

This section proposes the TAM consumer registration binding for Chemical's `COMPATIBILITY_REVIEW` business object type. All items are proposals for TAM Owner decision; none are accepted or implemented.

### 2.1 Proposed Consumer Registration Fields

| Field | Proposed Value | Structural Basis | Acceptance Status |
|-------|----------------|-----------------|-------------------|
| `consumer_type` | `CHEMICAL` | TAM-006 §3.5: `consumer_type CHECK (consumer_type IN ('CHEMICAL','SAFE'))` — CHEMICAL is structurally valid | VERIFIED STRUCTURAL — TAM Owner acceptance of this specific use still required |
| `business_object_type` | `COMPATIBILITY_REVIEW` | TAM-006 §3.5: `business_object_type TEXT NOT NULL` — no CHECK constraint; value is structurally valid but no existing record | **TAM OWNER EXPLICIT ACCEPTANCE REQUIRED** |
| `business_object_id` | Chemical server-stored `review_id` UUID | CHEM A1 §3: server-generated immutable UUID; client input MUST NOT be trusted directly | PROPOSED — must be server-resolved, not client-supplied |
| `company_id` | Server-authenticated, server-resolved from review scope | CHEM A1 §3: company authenticated server-side | PROPOSED — client-supplied company_id MUST NOT be trusted |
| `factory_id` | `review.factory_id` exactly (NON-NULL in CHEM) | CHEM A1 §4.1: factory_id is required on review creation; TAM-006 §3.5: `factory_id UUID NULL` (TAM schema allows NULL) | PROPOSED — CHEM caller MUST NOT supply NULL; TAM nullable field requires explicit binding contract |
| `evidence_ref` | `review.evaluation_ref` string (NON-NULL in CHEM) | CHEM A1 §4.2: evaluation_ref persisted server-side; TAM-006 §3.5: `evidence_ref TEXT NULL` | PROPOSED — CHEM caller MUST NOT supply empty/null; server-persisted value only |
| `route_type_hint` | **PROPOSED:** `PROCESS_TYPE` | TAM-006 §4: when PROCESS_TYPE and DOCUMENT_TYPE routes both match, explicit hint required to prevent AMBIGUOUS_ROUTE fail; compatibility review is a process-level operation semantically independent of storage location | **PROPOSED / TAM OWNER UNDECIDED** — GPT recommendation; Owner may reject |
| `process_type` / `scope_key` | **PROPOSED:** `WMS_COMPATIBILITY_REVIEW` | TAM-006 §4: scope_key scopes within process type; no existing route record for this scope | **PROPOSED / TAM OWNER UNDECIDED** — separate route record creation required; string value not yet accepted |
| `idempotency_key` | **PROPOSED:** Server-generated `CHEM:COMPATIBILITY_REVIEW:{review_id}` | TAM-006 §3.5: `UNIQUE(company_id, consumer_type, idempotency_key)`; same review_id → same key; different payload with same key → TAM returns 409 | **PROPOSED / TAM OWNER UNDECIDED** — format and generation authority not yet accepted |
| `delegation.scope_business_type` | Future candidate: `COMPATIBILITY_REVIEW` | TAM-006: `scope_business_type TEXT` column exists in undeployed delegation design table | DESIGN TARGET ONLY — delegation engine NOT DEPLOYED; no actual delegation behavior asserted |

### 2.2 Route Resolution Notes (per TAM-006 §4)

TAM-006 §4 defines a priority-ordered route lookup. When both PROCESS_TYPE and DOCUMENT_TYPE routes exist for a `(company_id, consumer_type)` pair, the absence of `route_type_hint` produces `NO_APPROVAL_ROUTE_FOUND` (fail-closed). The proposal to use `PROCESS_TYPE` with `scope_key=WMS_COMPATIBILITY_REVIEW` is GPT's recommendation based on the semantic nature of a compatibility review as a process. This is NOT finalized:

- TAM Owner must decide: accept `PROCESS_TYPE`, accept alternative, or reject.
- Until Owner accepts, `route_type_hint` and `scope_key` remain `PROPOSED / OWNER_UNDECIDED`.
- `NO_APPROVAL_ROUTE_FOUND` fail-closed behavior must be preserved regardless.
- The existing TAM-006 §4 route engine SoT is NOT modified by this proposal.

### 2.3 Idempotency Notes (per TAM-006 §3.5)

TAM-006 §3.5 enforces `UNIQUE(company_id, consumer_type, idempotency_key)`. The proposed key format `CHEM:COMPATIBILITY_REVIEW:{review_id}` ensures:
- Same review, same payload → same existing TAM request returned (no duplicate)
- Same key, different scope/payload → TAM returns 409 conflict (Chemical must treat as error)
- Different review_id → different key → new TAM request

This format is `PROPOSED / OWNER_UNDECIDED`. TAM Owner must accept key format, generation authority (server-side only), and conflict semantics before implementation.

---

## 3. C-DEP-02 — TAM GET Response Contract Proposal

**Status: PROPOSED / TAM OWNER ACCEPTANCE PENDING**

### 3.1 Endpoint

| Aspect | Current State | Proposal | Acceptance Status |
|--------|---------------|----------|-------------------|
| Logical design URL | `GET /tam/requests/{tam_request_id}` | Per TAM-006 §9 and CHEM A1 §4.1 | DESIGN TARGET |
| Physical URL (with prefix) | TAM `tam_routes.py` uses prefix `/v1/tam` | **Proposed:** `GET /v1/tam/requests/{tam_request_id}` | **PROPOSED / TAM OWNER UNDECIDED** — canonical path must be explicitly decided by TAM Owner |
| Implementation status | NOT DEPLOYED | Route exists in `tam_routes.py` but NOT REGISTERED in `main.py` (TAM Module Definition §6: all HTTP endpoints "미등록") | NOT DEPLOYED — absence of this route is a known BLOCKER for A2 activation |
| Authentication | TAM server-side consumer authorization required | Company/factory-scoped tenant authorization; cross-tenant information must not be exposed | PROPOSED — TAM Owner must confirm authorization model |

**Note:** A plain HTTP 404 from an unregistered or unavailable route is NOT equivalent to a legitimate `TAM_REQUEST_NOT_FOUND` tenant-scoped response. Chemical MUST distinguish these cases (see §3.3 error contracts).

### 3.2 Response Fields (15 Fields)

| # | Field | TAM Source | Nullable (TAM schema) | CHEM Binding Requirement | Notes |
|---|-------|------------|----------------------|--------------------------|-------|
| 1 | `request_id` | `tam_approval_requests.request_id` | NOT NULL | Exact match with submitted tam_request_id | — |
| 2 | `company_id` | `tam_approval_requests.company_id` | NOT NULL | Exact match with authenticated company | Cross-tenant BOLA prevention |
| 3 | `factory_id` | `tam_approval_requests.factory_id` | NULL (TAM schema) | Must match `review.factory_id`; CHEM MUST reject NULL | TAM schema allows NULL; CHEM binding requires NON-NULL |
| 4 | `consumer_type` | `tam_approval_requests.consumer_type` | NOT NULL | Must be `CHEMICAL` exactly | — |
| 5 | `business_object_type` | `tam_approval_requests.business_object_type` | NOT NULL | Must be `COMPATIBILITY_REVIEW` exactly | — |
| 6 | `business_object_id` | `tam_approval_requests.business_object_id` | NOT NULL | Must match `review_id` exactly | — |
| 7 | `evidence_ref` | `tam_approval_requests.evidence_ref` | NULL (TAM schema) | Must match server-persisted `review.evaluation_ref`; CHEM MUST reject NULL | TAM schema allows NULL; CHEM binding requires NON-NULL |
| 8 | `status` | `tam_approval_requests.status` | NOT NULL | For approval issuance: APPROVED required | PENDING/IN_PROGRESS/SUPPLEMENT_REQUESTED → NOT_APPROVED |
| 9 | `effective` | Computed by `effective_approval_valid()` (TAM-006 §3.10) | — | `true` required for approval issuance; unreachable must NOT be silently treated as `false` | TAM owns effective computation; Chemical must not recompute |
| 10 | `effectiveness_checked_at` | TAM server evaluation timestamp | — | Must be present in response; CHEM must not use as simple cache key | — |
| 11 | `completed_at` | `tam_approval_requests.completed_at` | NULL (TAM schema) | APPROVED → MUST be NON-NULL; PENDING states allow NULL | APPROVED + NULL = fail-closed 503 UNVERIFIED |
| 12 | `completion_decision_id` | `tam_approval_decisions.decision_id` of the final completing transition | NOT DEPLOYED (table not deployed) | APPROVED → MUST be present and non-null | Source table not yet deployed |
| 13 | `approved_by` | `tam_approval_decisions.actor_user_id` of final completing transition | NOT DEPLOYED | APPROVED → MUST be non-null; is the TAM decision actor, NOT a `recorded_by` field | Must NOT be confused with `on_behalf_of_user_id` |
| 14 | `approved_at` | Alias of `completed_at` | — | APPROVED → MUST equal `completed_at` exactly; Chemical MUST NOT derive from `decided_at` independently | TAM-006 §3.7: `decided_at` is a per-decision timestamp; `approved_at` = `completed_at` of the request |
| 15 | `on_behalf_of_user_id` | `tam_approval_decisions.on_behalf_of_user_id` of completing transition | NULL (delegation optional) | NULL allowed when no delegation; MUST NOT replace `approved_by` | — |

**Multi-decision serialization**: For `SEQUENTIAL`, `PARALLEL_ANY`, or `PARALLEL_ALL` approval types, TAM selects and reports the final serialized completing transition decision. Chemical MUST NOT independently query `ORDER BY decided_at DESC LIMIT 1` to derive `approved_by`. The full decision history is preserved in the TAM ledger.

### 3.3 Error Contracts (4 Proposed GAPs — TAM Owner acceptance required)

**GAP-R1 — Tenant-scoped 404 vs. routing 404:**

| Case | Proposed TAM response | Proposed CHEM treatment | Acceptance |
|------|-----------------------|------------------------|------------|
| Tenant-scoped genuine not-found (valid auth, request does not exist or belongs to other tenant) | Structured `404 TAM_REQUEST_NOT_FOUND` (same response for both cases; no cross-tenant disclosure) | Map to Chemical `403 OVERRIDE_TAM_REQUEST_NOT_FOUND` after confirming structured response | **PROPOSED / TAM OWNER UNDECIDED** |
| Unregistered route / infrastructure 404 / empty body / malformed JSON | NOT a legitimate TAM_REQUEST_NOT_FOUND | `503 OVERRIDE_TAM_UNAVAILABLE` or `503 OVERRIDE_TAM_UNVERIFIED` (fail-closed) | PROPOSED |

**GAP-R2 — effective=false vs. unverifiable:**

| Case | Proposed TAM response | Proposed CHEM treatment | Acceptance |
|------|-----------------------|------------------------|------------|
| APPROVED but effectiveness revoked/expired (TAM-006 §3.10) | Structured 200 with `status=APPROVED`, `effective=false`, full fields present | `422 OVERRIDE_TAM_NOT_EFFECTIVE` | **PROPOSED / TAM OWNER UNDECIDED** |
| TAM unreachable / 5xx | No valid structured response | `503 OVERRIDE_TAM_UNAVAILABLE` (fail-closed) | PROPOSED |
| TAM reachable but response schema mismatch / missing required fields | Malformed 200 | `503 OVERRIDE_TAM_UNVERIFIED` (fail-closed) | PROPOSED |

**GAP-R3 — APPROVED state integrity checks:**

The following conditions MUST all be satisfied for Chemical to treat a TAM response as valid APPROVED:
1. `status == APPROVED`
2. `completed_at` is NON-NULL
3. `approved_at == completed_at` (exact equality)
4. `completion_decision_id` is NON-NULL
5. `approved_by` is NON-NULL
6. `effective == true`

Any violation → `503 OVERRIDE_TAM_UNVERIFIED` (fail-closed). Status: **PROPOSED / TAM OWNER UNDECIDED**.

**GAP-R4 — Transport and schema availability:**

- Timeout or 5xx → `503 OVERRIDE_TAM_UNAVAILABLE`
- HTTP 200 with unexpected schema, type mismatch, or authorization contradiction → `503 OVERRIDE_TAM_UNVERIFIED`
- TAM Owner must formally specify: transport protocol, authentication mechanism, structured error envelope format, and whether 404 body is a distinguished JSON structure or plain HTTP 404.

Status: **PROPOSED / TAM OWNER UNDECIDED**.

---

## 4. Subsequent Activation Gate Separation

This section records which C-DEPs are prerequisites for which activation gates. No gate status is changed by this document.

| Gate | C-DEP Requirements | Current Blocker State |
|------|-------------------|----------------------|
| A1 Implementation WO issuance | C-DEP-02 TAM GET contract accepted + C-DEP-03 business_object_type accepted + Owner authorization + GPT design WO | NOT YET — C-DEP-02/03 PENDING |
| A2 (TAM execution activation) | C-DEP-01 TAM request creation; C-DEP-04 TAM decision execution; C-DEP-13 TAM revocation execution; TAM tables/routes deployed in production | BLOCKED — TAM execution tables NOT DEPLOYED |
| C (C-option / use reservation) | C-DEP-05 atomically serialized use reservation BEFORE WMS Posting; requires A2 complete | NOT DESIGNED — separate BLOCKED Gate |
| B (other WP-07I work) | Separate WO | NOT STARTED |
| D | Separate WO | BLOCKED |

**Open dependencies that remain unresolved by this document:**
- `C-DEP-09`: Operator TTL config authority, clock source, expiry calculation — OWNER_ACCEPTANCE_PENDING; 24h default is semantic target only, not deployed config
- `C-DEP-10`: Multi-line compatibility review clarification — BLOCKED (DS-13)
- `C-DEP-11`: Provider identity stable token format and `evaluation_ref` non-reuse — OPEN
- `C-DEP-12`: Supersession/cancellation policy for concurrent approvals — UNDECIDED
- `BLOCKER-003`: `WmsPutawayService._evaluate_compatibility()` inline constructor (DI fix required for Provider activation, Gate C)
- `BLOCKER-004`: 0 authorized policy rules (Gate C prerequisite)

**Frozen scope:** A0 frozen 5-tuple approval scope is NOT modified by this document. `BLOCK` and `REVIEW_REQUIRED` statuses are NOT converted to OK by this document or any inference from it.

---

## 5. Acceptance Decision Table

All items are `PROPOSED / TAM OWNER ACCEPTANCE PENDING`. This table must be updated to reflect TAM Owner's explicit decision for each item. No item may be marked `ACCEPTED`, `IMPLEMENTED`, `ACTIVE`, or `CLOSED FINAL` without TAM Owner's documented explicit acceptance.

| ID | Topic | Proposed Value / Contract | Status |
|----|-------|--------------------------|--------|
| C-DEP-03-A | `business_object_type = 'COMPATIBILITY_REVIEW'` TAM acceptance | Register as valid business object type in TAM consumer contract | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-03-B | `route_type_hint = PROCESS_TYPE` | Use PROCESS_TYPE hint to resolve route; fail-closed on ambiguity | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-03-C | `scope_key = 'WMS_COMPATIBILITY_REVIEW'` | Scope key string value and route record creation | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-03-D | `idempotency_key = 'CHEM:COMPATIBILITY_REVIEW:{review_id}'` | Server-generated key format; same review → same key; 409 on payload mismatch | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-03-E | `factory_id` NON-NULL binding | CHEM must not send NULL factory_id; TAM nullable field requires explicit contract | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-03-F | `evidence_ref` NON-NULL binding | CHEM must not send NULL/empty evidence_ref; TAM nullable field requires explicit contract | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-A | Canonical physical URL | `GET /v1/tam/requests/{tam_request_id}` or TAM Owner alternative | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-B | 15-field response contract | All fields, sources, nullable semantics, and CHEM binding as specified in §3.2 | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-C | `approved_by = actor_user_id` of completing transition | Not `recorded_by`; not independently derived by Chemical | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-D | `approved_at = completed_at` (exact alias) | Chemical MUST NOT use `decided_at` as `approved_at` | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-E | Tenant-scoped 404 contract (GAP-R1) | Structured `404 TAM_REQUEST_NOT_FOUND`; unregistered route → 503 fail-closed | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-F | `effective=false` vs. unavailable distinction (GAP-R2) | Structured 200 with effective=false ≠ 503 unreachable | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-G | APPROVED integrity check contract (GAP-R3) | All 6 conditions must hold; any violation → UNVERIFIED 503 | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-H | Transport and schema availability contract (GAP-R4) | Timeout/5xx → UNAVAILABLE; schema mismatch → UNVERIFIED | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-09 | Operator TTL source and authority | Owner-confirmed TTL config SoT, clock authority, expiry algorithm | OPEN / OWNER ACCEPTANCE PENDING (separate from C-DEP-02/03) |

---

## 6. Verification Fixtures — Test Specifications (Design Only)

These fixtures are **test specifications** derived from the GPT dossier. They have NOT been executed. No fixture result may be marked PASS until the fixture is actually run against a deployed and authorized system.

| ID | Test Name | Precondition | Action | Expected Result | Execution Status |
|----|-----------|-------------|--------|-----------------|-----------------|
| AC-01 | Idempotency — same review, same payload | TAM deployed; `review_id` exists | Submit TAM request with `CHEM:COMPATIBILITY_REVIEW:{review_id}` twice, same scope | Same TAM request returned both times; no duplicate created | NOT EXECUTED |
| AC-02 | Idempotency conflict — same key, different scope | TAM deployed | Submit with same idempotency_key, different `business_object_id` or `factory_id` | TAM returns 409 conflict; Chemical treats as error | NOT EXECUTED |
| AC-03 | Binding mismatch rejection | TAM deployed | Submit request where any of: company_id, factory_id, evidence_ref, business_object_id, consumer_type, business_object_type does not match review server state | Chemical rejects issuance before TAM submission; or TAM 422/409 causes Chemical fail-closed | NOT EXECUTED |
| AC-04 | Unregistered route 404 handling | TAM route NOT registered | Call `GET /v1/tam/requests/{id}` when route not registered | HTTP 404 (infrastructure); Chemical maps to `503 OVERRIDE_TAM_UNAVAILABLE`, NOT `TAM_REQUEST_NOT_FOUND` | NOT EXECUTED |
| AC-05 | Tenant-scoped structured 404 | TAM deployed; request_id from different tenant | Call `GET /v1/tam/requests/{id}` with cross-tenant ID | TAM returns structured `404 TAM_REQUEST_NOT_FOUND`; no other tenant fields disclosed; Chemical maps to `403 OVERRIDE_TAM_REQUEST_NOT_FOUND` | NOT EXECUTED |
| AC-06 | APPROVED with missing completed_at / decision integrity | TAM deployed | TAM response: `status=APPROVED`, `completed_at=NULL` OR `approved_at != completed_at` OR missing `completion_decision_id` | Chemical maps to `503 OVERRIDE_TAM_UNVERIFIED` (fail-closed) | NOT EXECUTED |
| AC-07 | APPROVED but effective=false | TAM deployed; approval effectiveness revoked | TAM response: `status=APPROVED`, `effective=false`, full fields present | Chemical maps to `422 OVERRIDE_TAM_NOT_EFFECTIVE`; NOT treated as `OVERRIDE_TAM_UNVERIFIED` | NOT EXECUTED |
| AC-08 | Multi-decision serialization | TAM deployed; PARALLEL_ALL approval type | Completing transition decision is last serialized APPROVED decision | Chemical reads `approved_by` from TAM response; does NOT independently query `ORDER BY decided_at DESC LIMIT 1` | NOT EXECUTED |
| AC-09 | Route ambiguity without hint | TAM deployed; PROCESS_TYPE and DOCUMENT_TYPE routes both match | Submit without `route_type_hint` | TAM returns `NO_APPROVAL_ROUTE_FOUND` (fail-closed); Chemical does not proceed | NOT EXECUTED |
| AC-10 | A1 mock isolation — no production mutation | A1 mock environment | Full A1 compatibility review flow with mock TAM | TAM NOT DEPLOYED → issuance not possible; zero production DB mutations; zero Provider activations | NOT EXECUTED |

---

## 7. Source Evidence and Cross-Reference

### 7.1 TAM-006 Sections Used

| Section | Content | Relevance |
|---------|---------|-----------|
| TAM-006 §3.5 | `tam_approval_requests` schema: `business_object_type TEXT NOT NULL`, `consumer_type CHECK IN ('CHEMICAL','SAFE')`, `factory_id UUID NULL`, `evidence_ref TEXT NULL`, `completed_at` nullable, `UNIQUE(company_id, consumer_type, idempotency_key)` | C-DEP-03 structural basis |
| TAM-006 §3.7 | `tam_approval_decisions`: `actor_user_id`, `decided_at`, `on_behalf_of_user_id` | C-DEP-02 `approved_by`, `on_behalf_of_user_id` source |
| TAM-006 §3.8 | `tam_approval_effectiveness_revocations` | C-DEP-02 `effective` field |
| TAM-006 §3.10 | `effective_approval_valid()` function | C-DEP-02 `effective` computation — TAM owns this |
| TAM-006 §4 | Route resolution priority; `route_type_hint` requirement for PROCESS+DOCUMENT conflict; `NO_APPROVAL_ROUTE_FOUND` fail-closed | C-DEP-03 route_type_hint proposal |
| TAM-006 §9 | API contract: `GET /tam/requests/{id}` in Request Lifecycle group | C-DEP-02 endpoint design target |

Fixed SHA source: https://github.com/taiengineering/tai-api/blob/c9c5f2689ef3df030781ba9985750ce9b800f5e4/docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md

### 7.2 TAM Module Definition Sections Used

| Section | Content | Relevance |
|---------|---------|-----------|
| §3 | Deployed tables list: 7 route/policy tables deployed; `tam_approval_requests`, `tam_approval_decisions` NOT deployed | C-DEP-02 NOT DEPLOYED basis |
| §6 | All HTTP endpoints "미등록" (not registered in main.py); GET routes exist in `tam_routes.py` but unregistered | C-DEP-02 NOT DEPLOYED basis |

Fixed SHA source: https://github.com/taiengineering/tai-api/blob/c9c5f2689ef3df030781ba9985750ce9b800f5e4/docs/tam/TAI_TAM_MODULE_DEFINITION_2026-10-10.md

### 7.3 CHEM A1 Design Sections Used

| Section | Content | Relevance |
|---------|---------|-----------|
| §3 | TAM consumer registration fields, review_id as business_object_id | C-DEP-03 §2.1 |
| §4 | Override approval issuance, `evaluation_ref`, factory_id scope | C-DEP-02/03 nullable binding |
| §5 | Revocation idempotency (R1-10) | Gate separation |
| §6.4 | Concurrent review / TAM request policy (R1-09) | Gate separation |
| §7.4 | TAM contract acceptance blockers (R1-13) | C-DEP register |
| §11 | Open blockers register | C-DEP-09/10/11/12, BLOCKER-003/004 |

Fixed SHA source: https://github.com/taiengineering/tai-chemical/blob/afa58f0388d391881f6f6c3252a549f8390dde9c/docs/foundation/CHEM_MGMT_OBJ07_WP07I_A1_REVIEW_OVERRIDE_DESIGN_V1.md

### 7.4 Git Diff Verification

- `git diff --name-only main...HEAD` on this branch: **1 file** (`docs/tam/TAM_CHEM_COMPATIBILITY_REVIEW_CONTRACT_ACCEPTANCE_PROPOSAL_20261010.md`)
- Branch base SHA: `c9c5f2689ef3df030781ba9985750ce9b800f5e4`
- CODE_CHANGE = 0
- SQL_MIGRATION = 0
- DB_WRITE = 0
- DEPLOY = 0
- MERGE = 0

---

## 8. Result Block

```text
CHEM WP-07I TAM C-DEP-02/03 CONTRACT RFC RESULT
CHEM_MAIN_SHA          = afa58f0388d391881f6f6c3252a549f8390dde9c
TAM_MAIN_SHA           = c9c5f2689ef3df030781ba9985750ce9b800f5e4
TAM_PR                 = OPEN / DRAFT / UNMERGED (see PR link)
TAM_PR_BASE_SHA        = c9c5f2689ef3df030781ba9985750ce9b800f5e4
TAM_PR_HEAD_SHA        = (set after PR creation)
FILE_CHANGED           = docs/tam/TAM_CHEM_COMPATIBILITY_REVIEW_CONTRACT_ACCEPTANCE_PROPOSAL_20261010.md
DOC_BLOB_SHA           = (set after commit)
C_DEP_02               = CONTRACT_PROPOSED / TAM_OWNER_ACCEPTANCE_PENDING
C_DEP_03               = CONTRACT_PROPOSED / TAM_OWNER_ACCEPTANCE_PENDING
CANONICAL_URL          = PROPOSED / OWNER_UNDECIDED
ROUTE_HINT             = PROPOSED / OWNER_UNDECIDED
IDEMPOTENCY            = PROPOSED / OWNER_UNDECIDED
CODE_CHANGE            = 0
MIGRATION              = 0
DB_WRITE               = 0
DEPLOY                 = 0
MERGE                  = 0
GPT_INDEPENDENT_VERIFY = REQUIRED
OWNER_APPROVAL         = NOT_GRANTED
```
