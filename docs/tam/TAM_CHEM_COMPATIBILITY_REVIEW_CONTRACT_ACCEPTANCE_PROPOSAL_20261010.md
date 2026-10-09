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
| TAM historical source / fork anchor | `c9c5f2689ef3df030781ba9985750ce9b800f5e4` | PRE-GUARD anchor; all source citations in this document reference this SHA |
| TAM current main / PR base | `393d4c239ae531b10b44961143bab9125c1fc84d` | TAM main advanced between branch creation and PR creation; see drift table below |
| TAM-006 design document | `docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md` at `c9c5f268...` | Read-only source; blob unchanged at `393d4c23` |
| TAM Module Definition | `docs/tam/TAI_TAM_MODULE_DEFINITION_2026-10-10.md` at `c9c5f268...` | Read-only source; blob unchanged at `393d4c23` |

**Non-impacting drift — read-only evidence (RFC-R1-05):**

TAM main advanced from `c9c5f268...` to `393d4c23...` with one commit. GPT independent verification confirmed this commit touched only LEG diagnosis routing/schema/tests; all TAM contract source blobs are identical at both refs:

| File | Blob SHA (verified identical at both refs) |
|------|--------------------------------------------|
| `docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md` | `4c138658b037874722d1deca133323a327d0bdeb` |
| `docs/tam/TAI_TAM_MODULE_DEFINITION_2026-10-10.md` | `9e78d33ad1227255c2545dd85ab126222def6d35` |
| `routers/tam_routes.py` | `d9bf97a1a110c377837a679c958824bd338a6f19` |
| `main.py` | `9e105b86e182f21b180ecbf99d04f76aa9fb3bdd` |

Drift is **non-impacting** on this RFC's contract evidence. SHA-permalink citations below reference `c9c5f268...` (the investigated anchor); the PR base is `393d4c23...`.

Source links (fixed SHA at source anchor):
- CHEM A1 design: https://github.com/taiengineering/tai-chemical/blob/afa58f0388d391881f6f6c3252a549f8390dde9c/docs/foundation/CHEM_MGMT_OBJ07_WP07I_A1_REVIEW_OVERRIDE_DESIGN_V1.md
- TAM-006: https://github.com/taiengineering/tai-api/blob/c9c5f2689ef3df030781ba9985750ce9b800f5e4/docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md
- TAM Module Definition: https://github.com/taiengineering/tai-api/blob/c9c5f2689ef3df030781ba9985750ce9b800f5e4/docs/tam/TAI_TAM_MODULE_DEFINITION_2026-10-10.md

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
| `route_type_hint` | **PROPOSED:** `PROCESS_TYPE` | TAM-006 §4: when PROCESS_TYPE and DOCUMENT_TYPE routes both match, explicit hint required to prevent `AMBIGUOUS_ROUTE` (HTTP 422); compatibility review is a process-level operation semantically independent of storage location | **PROPOSED / TAM OWNER UNDECIDED** — GPT recommendation; Owner may reject |
| `process_type` / `scope_key` | **PROPOSED:** `WMS_COMPATIBILITY_REVIEW` | TAM-006 §4: scope_key scopes within process type; no existing route record for this scope | **PROPOSED / TAM OWNER UNDECIDED** — separate route record creation required; string value not yet accepted |
| `idempotency_key` | **PROPOSED:** Server-generated `CHEM:COMPATIBILITY_REVIEW:{review_id}` | TAM-006 §3.5: `UNIQUE(company_id, consumer_type, idempotency_key)`; same review_id → same key; different payload with same key → TAM returns 409 | **PROPOSED / TAM OWNER UNDECIDED** — format and generation authority not yet accepted |
| `delegation.scope_business_type` | Future candidate: `COMPATIBILITY_REVIEW` | TAM-006: `scope_business_type TEXT` column exists in undeployed delegation design table | DESIGN TARGET ONLY — delegation engine NOT DEPLOYED; no actual delegation behavior asserted |

### 2.2 Route Resolution Notes (per TAM-006 §4)

TAM-006 §4 defines a priority-ordered route lookup with two distinct failure modes:

- **`AMBIGUOUS_ROUTE` (HTTP 422):** When both PROCESS_TYPE and DOCUMENT_TYPE routes exist for a `(company_id, consumer_type)` pair and `route_type_hint` is absent or insufficient to resolve the ambiguity, TAM returns HTTP 422 `AMBIGUOUS_ROUTE` (fail-closed). This is the failure the proposed `route_type_hint=PROCESS_TYPE` is designed to prevent.
- **`NO_APPROVAL_ROUTE_FOUND` (HTTP 422):** When no eligible route record exists at all for the consumer, TAM returns HTTP 422 `NO_APPROVAL_ROUTE_FOUND` (fail-closed). This is a separate failure from ambiguity.

The proposal to use `PROCESS_TYPE` with `scope_key=WMS_COMPATIBILITY_REVIEW` is GPT's recommendation based on the semantic nature of a compatibility review as a process. This is NOT finalized:

- TAM Owner must decide: accept `PROCESS_TYPE`, accept alternative, or reject.
- Until Owner accepts, `route_type_hint` and `scope_key` remain `PROPOSED / OWNER_UNDECIDED`.
- Both `AMBIGUOUS_ROUTE` and `NO_APPROVAL_ROUTE_FOUND` fail-closed behaviors must be preserved.
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
| Physical URL (with prefix) | **NOT IMPLEMENTED** — `tam_routes.py` prefix is `/v1/tam`; only route-management endpoints exist (`GET /v1/tam/routes`, `GET /v1/tam/routes/{route_id}`); the request lifecycle `GET /requests/{id}` is NOT present in `tam_routes.py` | **Proposed:** `GET /v1/tam/requests/{tam_request_id}` — consistent with existing prefix; canonical path must be explicitly decided by TAM Owner | **PROPOSED / TAM OWNER UNDECIDED** |
| Implementation status | NOT IMPLEMENTED AND NOT DEPLOYED — request lifecycle GET does not exist in `tam_routes.py`; `main.py` does not register the TAM router (TAM Module Definition §6: all HTTP endpoints "미등록") | Requires new implementation; absence is a known BLOCKER for A2 activation | NOT DEPLOYED |
| Authentication | TAM server-side consumer authorization required | Company/factory-scoped tenant authorization; cross-tenant information must not be exposed | PROPOSED — TAM Owner must confirm authorization model |

**Note:** A plain HTTP 404 from an unregistered or unavailable route is NOT equivalent to a legitimate `TAM_REQUEST_NOT_FOUND` tenant-scoped response. Chemical MUST distinguish these cases (see §3.3 error contracts). The existence of other routes under `/v1/tam` prefix does NOT prove the request lifecycle endpoint exists or is reachable.

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
| Unregistered route / infrastructure 404 / empty body / malformed JSON | NOT a legitimate TAM_REQUEST_NOT_FOUND | `503 OVERRIDE_TAM_UNAVAILABLE` (fail-closed) | PROPOSED |

**GAP-R2 — Ordered response classification:**

Chemical MUST apply the following ordered classification to every TAM response. A response cannot simultaneously satisfy two levels; the first applicable level determines the outcome:

| Priority | Condition | Proposed CHEM treatment | Notes |
|----------|-----------|------------------------|-------|
| 1 | Transport failure: timeout, 5xx, unregistered endpoint | `503 OVERRIDE_TAM_UNAVAILABLE` (fail-closed) | NOT tenant not-found; see GAP-R4 |
| 2 | TAM reachable but response is malformed: schema mismatch, missing required fields, or APPROVED provenance failures (see GAP-R3) | `503 OVERRIDE_TAM_UNVERIFIED` (fail-closed) | Provenance failures: null completed_at, missing completion_decision_id, mismatched approved_at, missing approved_by |
| 3 | Fully validated response, `status != APPROVED` | `422 OVERRIDE_TAM_NOT_APPROVED` | — |
| 4 | Fully validated response, `status == APPROVED`, all provenance checks pass (GAP-R3), `effective == false` | `422 OVERRIDE_TAM_NOT_EFFECTIVE` | NOT UNVERIFIED — effective=false on a fully valid APPROVED response is a distinct outcome |
| 5 | Fully validated response, `status == APPROVED`, all provenance checks pass (GAP-R3), `effective == true`, valid binding | Eligible for issuance checks | NOT unconditional final approval — BLOCK or REVIEW_REQUIRED must not be silently converted |

Status: **PROPOSED / TAM OWNER UNDECIDED**.

**GAP-R3 — APPROVED provenance completeness (subset of Priority 2 above):**

For a TAM response with `status == APPROVED`, all of the following MUST be present and internally consistent before `effective` is examined. If any check fails, the response is classified as Priority 2 → `503 OVERRIDE_TAM_UNVERIFIED` (fail-closed):

1. `completed_at` is NON-NULL
2. `approved_at == completed_at` (exact equality)
3. `completion_decision_id` is NON-NULL
4. `approved_by` is NON-NULL

Only after all 4 provenance checks pass does the `effective` field determine whether the outcome is Priority 4 (`422 NOT_EFFECTIVE`) or Priority 5 (eligible). This ordering ensures `effective=false` on a provenance-valid APPROVED response is never silently collapsed into an UNVERIFIED error.

Status: **PROPOSED / TAM OWNER UNDECIDED**.

**GAP-R4 — Transport and schema availability:**

- Timeout or 5xx → `503 OVERRIDE_TAM_UNAVAILABLE` (see GAP-R2 Priority 1)
- HTTP 200 with unexpected schema, type mismatch, or authorization contradiction → `503 OVERRIDE_TAM_UNVERIFIED` (see GAP-R2 Priority 2)
- TAM Owner must formally specify: transport protocol, authentication mechanism, structured error envelope format, and whether 404 body is a distinguished JSON structure or plain HTTP 404.

Status: **PROPOSED / TAM OWNER UNDECIDED**.

---

## 4. Subsequent Activation Gate Separation

This section records which C-DEPs are prerequisites for which activation gates. No gate status is changed by this document.

| Gate | C-DEP Requirements | Current Blocker State |
|------|-------------------|----------------------|
| A1 Implementation WO issuance | C-DEP-02 TAM GET contract accepted + C-DEP-03 business_object_type accepted + Owner authorization + GPT design WO | NOT YET — C-DEP-02/03 PENDING |
| A2 (TAM execution activation) | C-DEP-01 TAM request creation; C-DEP-04 TAM decision execution; C-DEP-13 `tam_approval_decisions` NOT DEPLOYED (blocks `approved_by` provenance verification in Production); TAM execution tables/routes deployed in production | BLOCKED — TAM execution tables NOT DEPLOYED |
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
| C-DEP-03-B | `route_type_hint = PROCESS_TYPE` | Use PROCESS_TYPE hint to prevent `AMBIGUOUS_ROUTE` (HTTP 422) when both route types match; fail-closed on no-route | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-03-C | `scope_key = 'WMS_COMPATIBILITY_REVIEW'` | Scope key string value and route record creation | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-03-D | `idempotency_key = 'CHEM:COMPATIBILITY_REVIEW:{review_id}'` | Server-generated key format; same review → same key; 409 on payload mismatch | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-03-E | `factory_id` NON-NULL binding | CHEM must not send NULL factory_id; TAM nullable field requires explicit contract | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-03-F | `evidence_ref` NON-NULL binding | CHEM must not send NULL/empty evidence_ref; TAM nullable field requires explicit contract | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-A | Canonical physical URL | `GET /v1/tam/requests/{tam_request_id}` — NOT yet implemented; TAM Owner must accept path and confirm implementation scope | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-B | 15-field response contract | All fields, sources, nullable semantics, and CHEM binding as specified in §3.2 | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-C | `approved_by = actor_user_id` of completing transition | Not `recorded_by`; not independently derived by Chemical | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-D | `approved_at = completed_at` (exact alias) | Chemical MUST NOT use `decided_at` as `approved_at` | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-E | Tenant-scoped 404 contract (GAP-R1) | Structured `404 TAM_REQUEST_NOT_FOUND`; unregistered route → 503 UNAVAILABLE fail-closed | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-F | Ordered response classification (GAP-R2) | 5-level priority: transport→UNAVAILABLE; malformed/provenance-fail→UNVERIFIED; not-APPROVED→NOT_APPROVED; APPROVED+effective=false→NOT_EFFECTIVE; APPROVED+effective=true→eligible | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-G | APPROVED provenance completeness (GAP-R3) | completed_at/approved_at/completion_decision_id/approved_by all NON-NULL and internally consistent required before effective is checked; any failure → UNVERIFIED 503 | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
| C-DEP-02-H | Transport and schema availability contract (GAP-R4) | Timeout/5xx → UNAVAILABLE; schema mismatch → UNVERIFIED; TAM Owner specifies structured error format | PROPOSED / TAM OWNER ACCEPTANCE PENDING |
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
| AC-06 | APPROVED with missing provenance fields | TAM deployed | TAM response: `status=APPROVED`, `completed_at=NULL` OR `approved_at != completed_at` OR missing `completion_decision_id` OR missing `approved_by` | GAP-R3 provenance check fails → Chemical maps to `503 OVERRIDE_TAM_UNVERIFIED` (Priority 2 fail-closed); effective field is NOT examined | NOT EXECUTED |
| AC-07 | APPROVED, provenance valid, effective=false | TAM deployed; approval effectiveness revoked | TAM response: `status=APPROVED`, all GAP-R3 provenance fields present and consistent, `effective=false` | GAP-R3 passes → `effective=false` → Chemical maps to `422 OVERRIDE_TAM_NOT_EFFECTIVE` (Priority 4); NOT treated as UNVERIFIED | NOT EXECUTED |
| AC-08 | Multi-decision serialization | TAM deployed; PARALLEL_ALL approval type | Completing transition decision is last serialized APPROVED decision | Chemical reads `approved_by` from TAM response; does NOT independently query `ORDER BY decided_at DESC LIMIT 1` | NOT EXECUTED |
| AC-09 | Route ambiguity — hint absent, both route types match | TAM deployed; PROCESS_TYPE and DOCUMENT_TYPE routes both exist for this consumer | Submit without `route_type_hint` | TAM returns HTTP 422 `AMBIGUOUS_ROUTE` (fail-closed); Chemical does not proceed | NOT EXECUTED |
| AC-10 | A1 mock isolation — no production mutation | A1 mock environment | Full A1 compatibility review flow with mock TAM | TAM NOT DEPLOYED → issuance not possible; zero production DB mutations; zero Provider activations | NOT EXECUTED |
| AC-11 | No eligible route exists | TAM deployed; no route record for this consumer | Submit request when no PROCESS_TYPE or DOCUMENT_TYPE route record exists for this (company_id, consumer_type) | TAM returns HTTP 422 `NO_APPROVAL_ROUTE_FOUND` (fail-closed); distinct from AMBIGUOUS_ROUTE (AC-09) | NOT EXECUTED |

---

## 7. Source Evidence and Cross-Reference

### 7.1 TAM-006 Sections Used

| Section | Content | Relevance |
|---------|---------|-----------|
| TAM-006 §3.5 | `tam_approval_requests` schema: `business_object_type TEXT NOT NULL`, `consumer_type CHECK IN ('CHEMICAL','SAFE')`, `factory_id UUID NULL`, `evidence_ref TEXT NULL`, `completed_at` nullable, `UNIQUE(company_id, consumer_type, idempotency_key)` | C-DEP-03 structural basis |
| TAM-006 §3.7 | `tam_approval_decisions`: `actor_user_id`, `decided_at`, `on_behalf_of_user_id` | C-DEP-02 `approved_by`, `on_behalf_of_user_id` source |
| TAM-006 §3.8 | `tam_approval_delegations` — delegation schema; `on_behalf_of_user_id` delegation source | C-DEP-02 `on_behalf_of_user_id` delegation context |
| TAM-006 §3.10 | `tam_approval_effectiveness_revocations` + `effective_approval_valid()` function | C-DEP-02 `effective` field and computation — TAM owns this |
| TAM-006 §4 | Route resolution priority; `route_type_hint` requirement for PROCESS+DOCUMENT conflict → `AMBIGUOUS_ROUTE` (HTTP 422); `NO_APPROVAL_ROUTE_FOUND` (HTTP 422) when no route exists | C-DEP-03 route_type_hint proposal; AC-09/AC-11 fixture basis |
| TAM-006 §9 | API contract: `GET /tam/requests/{id}` in Request Lifecycle group | C-DEP-02 endpoint design target |

Fixed SHA source: https://github.com/taiengineering/tai-api/blob/c9c5f2689ef3df030781ba9985750ce9b800f5e4/docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md

### 7.2 TAM Module Definition Sections Used

| Section | Content | Relevance |
|---------|---------|-----------|
| §3 | Deployed tables list: 7 route/policy tables deployed; `tam_approval_requests`, `tam_approval_decisions` NOT deployed | C-DEP-02 NOT DEPLOYED basis |
| §6 | All HTTP endpoints "미등록" (TAM router NOT registered in `main.py`); `tam_routes.py` implements only route-management endpoints (`GET /v1/tam/routes`, `GET /v1/tam/routes/{route_id}`); request lifecycle `GET /requests/{id}` is NOT implemented in `tam_routes.py` | C-DEP-02 NOT IMPLEMENTED AND NOT DEPLOYED basis |

Fixed SHA source: https://github.com/taiengineering/tai-api/blob/c9c5f2689ef3df030781ba9985750ce9b800f5e4/docs/tam/TAI_TAM_MODULE_DEFINITION_2026-10-10.md

### 7.3 CHEM A1 Design Sections Used

| Section | Content | Relevance |
|---------|---------|-----------|
| §3 | TAM consumer registration fields, review_id as business_object_id | C-DEP-03 §2.1 |
| §4 | Override approval issuance, `evaluation_ref`, factory_id scope | C-DEP-02/03 nullable binding |
| §5 | Revocation idempotency (R1-10) | Gate separation |
| §3.4 | Concurrent review / TAM request policy (R1-09) | Gate separation |
| §7.4 | TAM contract acceptance blockers (R1-13) | C-DEP register |
| §11 | Open blockers register; C-DEP-13 = `tam_approval_decisions NOT DEPLOYED` (blocks `approved_by` provenance verification) | C-DEP-09/10/11/12/13, BLOCKER-003/004 |

Fixed SHA source: https://github.com/taiengineering/tai-chemical/blob/afa58f0388d391881f6f6c3252a549f8390dde9c/docs/foundation/CHEM_MGMT_OBJ07_WP07I_A1_REVIEW_OVERRIDE_DESIGN_V1.md

### 7.4 Git Diff Verification

- `git diff --name-only main...HEAD` on this branch: **1 file** (`docs/tam/TAM_CHEM_COMPATIBILITY_REVIEW_CONTRACT_ACCEPTANCE_PROPOSAL_20261010.md`)
- Branch fork anchor (source investigation basis): `c9c5f2689ef3df030781ba9985750ce9b800f5e4`
- PR base / current TAM main: `393d4c239ae531b10b44961143bab9125c1fc84d` (non-impacting drift; see §1)
- CODE_CHANGE = 0
- SQL_MIGRATION = 0
- DB_WRITE = 0
- DEPLOY = 0
- MERGE = 0

---

## 8. Result Block

```text
CHEM WP-07I TAM C-DEP-02/03 CONTRACT RFC RESULT
CHEM_MAIN_SHA              = afa58f0388d391881f6f6c3252a549f8390dde9c
TAM_MAIN_SHA_SOURCE_ANCHOR = c9c5f2689ef3df030781ba9985750ce9b800f5e4
TAM_MAIN_SHA_PR_BASE       = 393d4c239ae531b10b44961143bab9125c1fc84d
TAM_PR                     = https://github.com/taiengineering/tai-api/pull/587  (OPEN / DRAFT / UNMERGED)
TAM_PR_BASE_SHA            = 393d4c239ae531b10b44961143bab9125c1fc84d
TAM_PR_PRE_HEAD_SHA        = 343a2e820ef09b2a2b1dc4e7cd2a049c899ce50c
TAM_PR_POST_HEAD_SHA       = captured separately in executor receipt
FILE_CHANGED               = docs/tam/TAM_CHEM_COMPATIBILITY_REVIEW_CONTRACT_ACCEPTANCE_PROPOSAL_20261010.md
PRE_DOC_BLOB_SHA           = 9c5e5b00032b0782ed0569ec2db19a229ccae3b2
POST_DOC_BLOB_SHA          = captured separately in executor receipt
C_DEP_02                   = CONTRACT_PROPOSED / TAM_OWNER_ACCEPTANCE_PENDING
C_DEP_03                   = CONTRACT_PROPOSED / TAM_OWNER_ACCEPTANCE_PENDING
CANONICAL_URL              = PROPOSED / OWNER_UNDECIDED
ROUTE_HINT                 = PROPOSED / OWNER_UNDECIDED
IDEMPOTENCY                = PROPOSED / OWNER_UNDECIDED
CODE_CHANGE                = 0
MIGRATION                  = 0
DB_WRITE                   = 0
DEPLOY                     = 0
MERGE                      = 0
GPT_INDEPENDENT_VERIFY     = REQUIRED
OWNER_APPROVAL             = NOT_GRANTED
```
