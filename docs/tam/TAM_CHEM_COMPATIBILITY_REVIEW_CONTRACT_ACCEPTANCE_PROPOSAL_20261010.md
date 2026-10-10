# TAM CHEM COMPATIBILITY REVIEW — Contract Acceptance Proposal
# WP-07I C-DEP-02 / C-DEP-03

**Status: TAM OWNER DECISION RECEIVED — DESIGN CONTRACT ACCEPTED (13 ITEMS) / C-DEP-02-H MODIFIED/DEFERRED — LIVE WIRE SPEC NOT ACCEPTED / A1 IMPLEMENTATION NOT AUTHORIZED / NO MERGE**
**Document type: DRAFT CONTRACT PROPOSAL — DESIGN CONTRACT ACCEPTED BY OWNER; NOT IMPLEMENTED, NOT ACTIVE; PR UNMERGED**
**Date: 2026-10-10**
**Repo: taiengineering/tai-api**
**Authority: TAM Owner has accepted the design contract (13 items, 2026-10-10 KST). C-DEP-02-H live wire spec deferred for A1 mock only. GPT independent verification of this receipt is required. A1 implementation and PR merge require separate authorization.**

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

**Status: DESIGN CONTRACT ACCEPTED BY TAM OWNER — C-DEP-03-A THROUGH C-DEP-03-F ACCEPTED / DESIGN ONLY / A1 MOCK-ONLY / NOT IMPLEMENTED**

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
- **`NO_APPROVAL_ROUTE_FOUND` (HTTP 422):** When no eligible route record exists at any level — instance, PROCESS_TYPE, DOCUMENT_TYPE, FACTORY_DEFAULT, or COMPANY_DEFAULT — TAM returns HTTP 422 `NO_APPROVAL_ROUTE_FOUND` (fail-closed). Factory/company default routes, if present and eligible, are consulted before this failure fires.

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

**Status: CONDITIONAL DESIGN ACCEPTANCE — C-DEP-02-A THROUGH C-DEP-02-G ACCEPTED / C-DEP-02-H MODIFIED/DEFERRED — LIVE WIRE SPEC NOT ACCEPTED; A1 MOCK ONLY**

### 3.1 Endpoint

| Aspect | Current State | Proposal | Acceptance Status |
|--------|---------------|----------|-------------------|
| Logical design URL | `GET /tam/requests/{tam_request_id}` | Per TAM-006 §9 and CHEM A1 §4.1 | DESIGN TARGET |
| Physical URL (with prefix) | **NOT IMPLEMENTED** — `tam_routes.py` prefix is `/v1/tam`; only route-management endpoints exist (`GET /v1/tam/routes`, `GET /v1/tam/routes/{route_id}`); the request lifecycle `GET /requests/{id}` is NOT present in `tam_routes.py` | **Proposed:** `GET /v1/tam/requests/{tam_request_id}` — consistent with existing prefix; canonical path must be explicitly decided by TAM Owner | **PROPOSED / TAM OWNER UNDECIDED** |
| Implementation status | NOT IMPLEMENTED AND NOT DEPLOYED — request lifecycle GET does not exist in `tam_routes.py`; `main.py` does not register the TAM router (TAM Module Definition §6: all HTTP endpoints "미등록") | Requires new implementation; absence is a known BLOCKER for A2 activation | NOT DEPLOYED |
| Authentication | TAM server-side consumer authorization required | Company/factory-scoped tenant authorization; cross-tenant information must not be exposed | PROPOSED — TAM Owner must confirm authorization model |

**Note:** A plain HTTP 404 from an unregistered or unavailable route is NOT equivalent to a legitimate `TAM_REQUEST_NOT_FOUND` tenant-scoped response. Chemical MUST distinguish these cases (see §3.3). The existence of other routes under `/v1/tam` prefix does NOT prove the request lifecycle endpoint exists or is reachable.

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

### 3.3 Response Handling Contracts (GAP-R1 through GAP-R4 — TAM Owner acceptance required)

Chemical processes each TAM GET response through a deterministic sequential dispatch. Steps are applied in order; the first matching condition terminates processing. All proposed error codes are OWNER UNDECIDED until TAM Owner accepts.

**GAP-R1 — Dispatch: transport, structured error envelope, and 200 branch (RFC-R2-01)**

**Step A — Transport / routing failure (evaluated before HTTP body is parsed):**

If any of the following occurs, Chemical treats the response as `503 OVERRIDE_TAM_UNAVAILABLE` (fail-closed). This is NOT tenant not-found:
- TCP/TLS connection failure, timeout
- HTTP 5xx from any layer
- Unregistered route / infrastructure HTTP 404 with no TAM error envelope (empty body, non-JSON, HTML page)

**Step B — TAM structured error envelope check (HTTP non-200 with parsed JSON body):**

TAM Owner must formally specify the authenticated structured error envelope format and exact error codes. Until accepted, the following is PROPOSED:

| Non-200 HTTP response | Proposed CHEM treatment |
|----------------------|------------------------|
| HTTP 404 with recognized TAM envelope `TAM_REQUEST_NOT_FOUND` (authenticated, tenant-scoped) | `403 OVERRIDE_TAM_REQUEST_NOT_FOUND` — no cross-tenant disclosure |
| HTTP 4xx (including 401, 403) or other non-200 **without** a recognized TAM error envelope | `503 OVERRIDE_TAM_UNVERIFIED` (fail-closed) — never classify as tenant not-found or verified approval without an authenticated envelope |
| Any non-200 with unrecognized/unknown TAM error code | `503 OVERRIDE_TAM_UNVERIFIED` (fail-closed) |

Status: **PROPOSED / TAM OWNER UNDECIDED** — TAM Owner must define the authenticated structured error envelope and designate which HTTP status + error code combinations are trusted.

**Step C — HTTP 200 branch:**

Proceed to GAP-R2 (binding verification), then GAP-R3 (APPROVED provenance and effectiveness).

**GAP-R2 — Six-field binding verification on HTTP 200 response (RFC-R2-02)**

After HTTP 200 is received, Chemical applies the following ordered verification. Caller authentication and tenant scope are confirmed first:

1. **Authenticate caller and resolve Chemical server-side tenant scope** — unauthorized callers are denied before any binding fields are examined; no tenant information is disclosed to unauthorized callers.
2. **Schema / type validation** — verify all 15 response fields are present with correct types. Any missing required field or type error → `503 OVERRIDE_TAM_UNVERIFIED` (malformed; not a binding mismatch).
3. **Six-field binding match** — compare all 6 binding fields from the TAM response against server-stored Chemical review values:

| Binding field | TAM response value | Must match (server-stored) |
|---------------|--------------------|---------------------------|
| `company_id` | TAM response `company_id` | Authenticated Chemical tenant company |
| `factory_id` | TAM response `factory_id` | `review.factory_id` (server-stored, NON-NULL) |
| `consumer_type` | TAM response `consumer_type` | `CHEMICAL` (exactly) |
| `business_object_type` | TAM response `business_object_type` | `COMPATIBILITY_REVIEW` (exactly) |
| `business_object_id` | TAM response `business_object_id` | `review.review_id` (server-stored UUID) |
| `evidence_ref` | TAM response `evidence_ref` | `review.evaluation_ref` (server-stored, NON-NULL) |

- **Confirmed value mismatch on a syntactically valid, typed field** → `409 OVERRIDE_BINDING_MISMATCH`; no approval INSERT proceeds (per CHEM A1 §3.3, §6.4)
- **Missing / NULL / ill-typed field** → `503 OVERRIDE_TAM_UNVERIFIED` (malformed — not a binding mismatch)

4. Only after all 6 binding fields match, proceed to GAP-R3.

Status: **PROPOSED / TAM OWNER UNDECIDED**.

**GAP-R3 — APPROVED provenance completeness and effectiveness ordering**

After binding verification passes, Chemical applies the following ordered classification to the `status` and provenance fields:

| Priority | Condition | Proposed CHEM treatment |
|----------|-----------|------------------------|
| 1 | `status != APPROVED` | `422 OVERRIDE_TAM_NOT_APPROVED` |
| 2 | `status == APPROVED`, any provenance check fails (see criteria below) | `503 OVERRIDE_TAM_UNVERIFIED` (fail-closed) |
| 3 | `status == APPROVED`, all provenance valid, `effective == false` | `422 OVERRIDE_TAM_NOT_EFFECTIVE` — distinct from UNVERIFIED |
| 4 | `status == APPROVED`, all provenance valid, `effective == true`, binding verified | Eligible for issuance checks — `BLOCK` or `REVIEW_REQUIRED` must NOT be silently converted to OK |

APPROVED provenance criteria — all must hold; any single failure → Priority 2:
1. `completed_at` is NON-NULL
2. `approved_at == completed_at` (exact equality)
3. `completion_decision_id` is NON-NULL
4. `approved_by` is NON-NULL

Status: **PROPOSED / TAM OWNER UNDECIDED**.

**GAP-R4 — TAM Owner structured error and transport specification**

TAM Owner must formally specify the following before the GAP-R1 Step B dispatch table can be treated as authoritative:
- Transport protocol and authentication mechanism
- Authenticated structured error envelope format (schema, required fields, error code enumeration)
- Which HTTP status codes carry a trusted TAM error envelope vs. infrastructure errors
- Whether HTTP 404 body is a distinguished JSON structure or plain HTTP 404

Until this specification is accepted, the dispatch in GAP-R1 Step B remains PROPOSED.

Status: **PROPOSED / TAM OWNER UNDECIDED**.

---

## 4. Subsequent Activation Gate Separation

This section records which C-DEPs are prerequisites for which activation gates. No gate status is changed by this document.

| Gate | C-DEP Requirements | Current Blocker State |
|------|-------------------|----------------------|
| A1 Implementation WO issuance | C-DEP-02 TAM GET contract accepted + C-DEP-03 business_object_type accepted + Owner authorization + GPT design WO | NOT YET — C-DEP-02/03 design contract accepted; A1 implementation WO not yet issued |
| A2 (TAM execution activation) | C-DEP-01: `tam_approval_requests` AND `tam_approval_decisions` tables deployed; C-DEP-04: `GET /tam/requests/{id}` endpoint live deployment; C-DEP-13: `tam_approval_decisions` NOT DEPLOYED (blocks `approved_by` provenance verification in Production); TAM execution tables/routes deployed in production | BLOCKED — TAM execution tables NOT DEPLOYED |
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

Items C-DEP-03-A through C-DEP-02-G have been accepted by TAM Owner as design contract (2026-10-10 KST, Option 1). C-DEP-02-H is MODIFIED/DEFERRED for A1 mock-only scope. C-DEP-09 remains open. No item may be marked `IMPLEMENTED`, `ACTIVE`, or `CLOSED FINAL` without further authorization. Acceptance applies to design contract scope only; no production deployment, merge, or implementation authorization.

| ID | Topic | Proposed Value / Contract | Status |
|----|-------|--------------------------|--------|
| C-DEP-03-A | `business_object_type = 'COMPATIBILITY_REVIEW'` TAM acceptance | Register as valid business object type in TAM consumer contract | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-03-B | `route_type_hint = PROCESS_TYPE` | Use PROCESS_TYPE hint to prevent `AMBIGUOUS_ROUTE` (HTTP 422) when both route types match; fail-closed on no-route | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-03-C | `scope_key = 'WMS_COMPATIBILITY_REVIEW'` | Scope key string value and route record creation | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-03-D | `idempotency_key = 'CHEM:COMPATIBILITY_REVIEW:{review_id}'` | Server-generated key format; same review → same key; 409 on payload mismatch | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-03-E | `factory_id` NON-NULL binding | CHEM must not send NULL factory_id; TAM nullable field requires explicit contract | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-03-F | `evidence_ref` NON-NULL binding | CHEM must not send NULL/empty evidence_ref; TAM nullable field requires explicit contract | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-02-A | Canonical physical URL | `GET /v1/tam/requests/{tam_request_id}` — NOT yet implemented; TAM Owner must accept path and confirm implementation scope | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-02-B | 15-field response contract | All fields, sources, nullable semantics, and CHEM binding as specified in §3.2 | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-02-C | `approved_by = actor_user_id` of completing transition | Not `recorded_by`; not independently derived by Chemical | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-02-D | `approved_at = completed_at` (exact alias) | Chemical MUST NOT use `decided_at` as `approved_at` | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-02-E | Response dispatch contract (GAP-R1) | Transport failure → UNAVAILABLE; authenticated structured 404 TAM_REQUEST_NOT_FOUND → CHEM 403; unknown/unverifiable non-200 → UNVERIFIED; 200 → binding then provenance | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-02-F | Six-field binding verification (GAP-R2) | Confirmed value mismatch on valid fields → 409 BINDING_MISMATCH; missing/malformed → 503 UNVERIFIED; auth before binding; no cross-tenant disclosure | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-02-G | APPROVED provenance and effectiveness ordering (GAP-R3) | status!=APPROVED → NOT_APPROVED; APPROVED+provenance-fail → UNVERIFIED; APPROVED+valid+effective=false → NOT_EFFECTIVE; APPROVED+valid+effective=true → eligible | ACCEPTED BY TAM OWNER — DESIGN CONTRACT / A1 MOCK-ONLY |
| C-DEP-02-H | TAM structured error format specification (GAP-R4) | TAM Owner must specify: transport protocol, auth mechanism, error envelope schema, error code enumeration, 404 body format | MODIFIED / DEFERRED — LIVE WIRE SPEC NOT ACCEPTED; A1 MOCK ONLY |
| C-DEP-09 | Operator TTL source and authority | Owner-confirmed TTL config SoT, clock authority, expiry algorithm | OPEN / OWNER ACCEPTANCE PENDING (separate from C-DEP-02/03) |

---

## 6. Verification Fixtures — Test Specifications (Design Only)

These fixtures are **test specifications** derived from the GPT dossier and R2 repairs. They have NOT been executed. No fixture result may be marked PASS until the fixture is actually run against a deployed and authorized system.

| ID | Test Name | Precondition | Action | Expected Result | Execution Status |
|----|-----------|-------------|--------|-----------------|-----------------|
| AC-01 | Idempotency — same review, same payload | TAM deployed; `review_id` exists | Submit TAM request with `CHEM:COMPATIBILITY_REVIEW:{review_id}` twice, same scope | Same TAM request returned both times; no duplicate created | NOT EXECUTED |
| AC-02 | Idempotency conflict — same key, different scope | TAM deployed | Submit with same idempotency_key, different `business_object_id` or `factory_id` | TAM returns 409 conflict; Chemical treats as error | NOT EXECUTED |
| AC-03a | Pre-send client field guard | Any state | Client-supplied binding field values (company_id, factory_id, etc.) provided in request payload | Chemical ignores/rejects client-supplied binding values; all binding fields resolved server-side from authenticated review before TAM submission; no TAM call made with untrusted client fields | NOT EXECUTED |
| AC-03b | Post-TAM-response binding mismatch | TAM deployed; TAM returns syntactically valid 200 with binding value mismatch | Chemical calls `GET /v1/tam/requests/{id}`; TAM returns HTTP 200 with valid schema but one or more binding values differ from server-stored review values | GAP-R2 binding check fails after TAM response received, before Chemical approval INSERT; `409 OVERRIDE_BINDING_MISMATCH`; zero Chemical approval rows inserted | NOT EXECUTED |
| AC-04 | Unregistered route / infrastructure 404 | TAM route NOT registered | Call `GET /v1/tam/requests/{id}` when route not registered; response is plain HTTP 404 or empty body | GAP-R1 Step A: HTTP 404 without TAM envelope → `503 OVERRIDE_TAM_UNAVAILABLE`; NOT classified as `TAM_REQUEST_NOT_FOUND` | NOT EXECUTED |
| AC-05 | Tenant-scoped structured 404 | TAM deployed; request_id from different tenant | Call `GET /v1/tam/requests/{id}` with cross-tenant ID | GAP-R1 Step B: TAM returns structured `404 TAM_REQUEST_NOT_FOUND` with authenticated envelope; Chemical maps to `403 OVERRIDE_TAM_REQUEST_NOT_FOUND`; no other tenant fields disclosed | NOT EXECUTED |
| AC-06 | APPROVED with missing provenance fields | TAM deployed | TAM response: HTTP 200, `status=APPROVED`, `completed_at=NULL` OR `approved_at != completed_at` OR missing `completion_decision_id` OR missing `approved_by` | GAP-R2 binding passes → GAP-R3 Priority 2: provenance check fails → `503 OVERRIDE_TAM_UNVERIFIED` (fail-closed); effective field is NOT examined | NOT EXECUTED |
| AC-07 | APPROVED, provenance valid, effective=false | TAM deployed; approval effectiveness revoked | TAM response: HTTP 200, `status=APPROVED`, all GAP-R3 provenance fields present and consistent, `effective=false` | GAP-R2 binding passes → GAP-R3 Priority 3: all provenance valid, `effective=false` → `422 OVERRIDE_TAM_NOT_EFFECTIVE`; NOT treated as UNVERIFIED | NOT EXECUTED |
| AC-08 | Multi-decision serialization | TAM deployed; PARALLEL_ALL approval type | Completing transition decision is last serialized APPROVED decision | Chemical reads `approved_by` from TAM response; does NOT independently query `ORDER BY decided_at DESC LIMIT 1` | NOT EXECUTED |
| AC-09 | Route ambiguity — hint absent, both route types match | TAM deployed; PROCESS_TYPE and DOCUMENT_TYPE routes both exist for this consumer | Submit without `route_type_hint` | TAM returns HTTP 422 `AMBIGUOUS_ROUTE` (fail-closed); Chemical does not proceed | NOT EXECUTED |
| AC-10 | A1 mock isolation — no production mutation | A1 mock environment | Full A1 compatibility review flow with mock TAM | TAM NOT DEPLOYED → issuance not possible; zero production DB mutations; zero Provider activations | NOT EXECUTED |
| AC-11 | No eligible route exists — all route levels absent | TAM deployed; no instance_route, PROCESS_TYPE, DOCUMENT_TYPE, FACTORY_DEFAULT, or COMPANY_DEFAULT route record exists for this `(company_id, consumer_type)` combination; all route levels explicitly absent | Submit TAM request for COMPATIBILITY_REVIEW | TAM returns HTTP 422 `NO_APPROVAL_ROUTE_FOUND` (fail-closed); distinct from `AMBIGUOUS_ROUTE` (AC-09) which requires two competing routes to exist | NOT EXECUTED |
| AC-12 | Factory-default fallback route resolves — no specific routes, factory default present | TAM deployed; PROCESS_TYPE + DOCUMENT_TYPE routes absent for this consumer; but FACTORY_DEFAULT route eligible for `company_id` | Submit TAM request without `route_type_hint` | TAM resolves via FACTORY_DEFAULT route; `NO_APPROVAL_ROUTE_FOUND` is NOT returned; request proceeds normally | NOT EXECUTED |

---

## 7. Source Evidence, Cross-Reference, and Change Log

### 7.1 TAM-006 Sections Used

| Section | Content | Relevance |
|---------|---------|-----------|
| TAM-006 §3.5 | `tam_approval_requests` schema: `business_object_type TEXT NOT NULL`, `consumer_type CHECK IN ('CHEMICAL','SAFE')`, `factory_id UUID NULL`, `evidence_ref TEXT NULL`, `completed_at` nullable, `UNIQUE(company_id, consumer_type, idempotency_key)` | C-DEP-03 structural basis |
| TAM-006 §3.7 | `tam_approval_decisions`: `actor_user_id`, `decided_at`, `on_behalf_of_user_id` | C-DEP-02 `approved_by`, `on_behalf_of_user_id` source |
| TAM-006 §3.8 | `tam_approval_delegations` — delegation schema; `on_behalf_of_user_id` delegation source | C-DEP-02 `on_behalf_of_user_id` delegation context |
| TAM-006 §3.10 | `tam_approval_effectiveness_revocations` + `effective_approval_valid()` function | C-DEP-02 `effective` field and computation — TAM owns this |
| TAM-006 §4 | Route resolution priority: instance → PROCESS_TYPE → DOCUMENT_TYPE → FACTORY_DEFAULT → COMPANY_DEFAULT; `route_type_hint` requirement for PROCESS+DOCUMENT conflict → `AMBIGUOUS_ROUTE` (HTTP 422); `NO_APPROVAL_ROUTE_FOUND` (HTTP 422) when no eligible route at any level | C-DEP-03 route_type_hint proposal; AC-09/AC-11/AC-12 fixture basis |
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
| §3.3 | Server-side verification of all 6 binding fields before approval INSERT | GAP-R2 binding verification basis |
| §3.4 | Concurrent review / TAM request policy (R1-09) | Gate separation |
| §4 | Override approval issuance, `evaluation_ref`, factory_id scope | C-DEP-02/03 nullable binding |
| §5 | Revocation idempotency (R1-10) | Gate separation |
| §6.4 | API error code table: `409 OVERRIDE_BINDING_MISMATCH` for confirmed binding mismatch | GAP-R2 binding mismatch error code source |
| §7.4 | TAM contract acceptance blockers (R1-13) | C-DEP register |
| §11 | Open blockers register; C-DEP-01 = `tam_approval_requests` + `tam_approval_decisions` tables deployment; C-DEP-04 = `GET /tam/requests/{id}` endpoint live deployment; C-DEP-13 = `tam_approval_decisions` NOT DEPLOYED (blocks `approved_by` provenance verification) | C-DEP-01/04/13 exact gate definitions; C-DEP-09/10/11/12, BLOCKER-003/004 |

Fixed SHA source: https://github.com/taiengineering/tai-chemical/blob/afa58f0388d391881f6f6c3252a549f8390dde9c/docs/foundation/CHEM_MGMT_OBJ07_WP07I_A1_REVIEW_OVERRIDE_DESIGN_V1.md

### 7.4 Git Diff Verification

- `git diff --name-only main...HEAD` on this branch: **1 file** (`docs/tam/TAM_CHEM_COMPATIBILITY_REVIEW_CONTRACT_ACCEPTANCE_PROPOSAL_20261010.md`)
- Branch fork anchor (source investigation basis): `c9c5f2689ef3df030781ba9985750ce9b800f5e4`
- PR base / current TAM main: `393d4c239ae531b10b44961143bab9125c1fc84d` (non-impacting drift; see §1)
- CODE_CHANGE = 0 | SQL_MIGRATION = 0 | DB_WRITE = 0 | DEPLOY = 0 | MERGE = 0

### 7.5 R2 Change Log

| ID | Section(s) changed | Change summary |
|----|--------------------|---------------|
| RFC-R2-01 | §3.3 GAP-R1, §5 C-DEP-02-E | Replaced flat 5-level table with sequential Step A/B/C dispatch; structured 404 envelope handled in Step B (before 200 validation); unknown/unverifiable non-200 → UNVERIFIED fail-closed |
| RFC-R2-02 | §3.3 GAP-R2, §5 C-DEP-02-F, §6 AC-03b | Added six-field binding verification step on HTTP 200 response; confirmed mismatch on valid fields → 409 BINDING_MISMATCH; missing/malformed → 503 UNVERIFIED; auth before binding |
| RFC-R2-03 | §2.2, §6 AC-11, AC-12 | AC-11 precondition updated to assert all route levels absent (instance/process/document/factory-default/company-default); AC-12 added for factory-default positive resolution case |
| RFC-R2-04 | §4 A2 row, §7.3 §11 | C-DEP-01 = `tam_approval_requests` + `tam_approval_decisions` tables; C-DEP-04 = `GET /tam/requests/{id}` endpoint live deployment (not "decision execution"); C-DEP-13 preserved |
| RFC-R2-05 | §6 AC-03a, AC-03b | AC-03 split into pre-send client guard (AC-03a) and post-TAM-response binding mismatch check (AC-03b); timing of each check made explicit |

### 7.6 Owner Decision Receipt Change Log

| ID | Section(s) changed | Change summary |
|----|--------------------|---------------|
| RFC-R3-OD | Header status, §2 status, §3 status, §4 A1 gate note, §5 acceptance table, §8 (new Owner Receipt), §9 Result Block | Owner Option 1 Decision Receipt recorded (2026-10-10 KST): 13 items ACCEPTED (design contract, A1 mock-only), C-DEP-02-H MODIFIED/DEFERRED; pre-edit HEAD `c1e939f69762204e7d736274caba41914e1efcfc` / blob `8f22ad07b790f3f774370a911fc96d06e68f6fb3` anchored; GPT independent verification required |

---

## 8. Owner Option 1 Decision Receipt — 2026-10-10 KST

**Receipt type:** TAM Owner design contract acceptance — documentation record
**Decision date:** 2026-10-10 KST
**Decision source:** Owner-provided conversation: selected '1' in Claude Code (Option 1 from GPT Owner Decision Packet)
**Scope:** Design contract acceptance ONLY — not implementation authorization, not PR merge, not production deployment

### 8.1 Owner Verbatim Acceptance Text

> TAM Owner 자격으로 PR #587의 C-DEP-03-A~F 및 C-DEP-02-A~G 총 13개 계약 항목을 이 결정서의 값과 제약에 따라 ACCEPT합니다. C-DEP-02-H는 A1 mock-only 범위에서 MODIFY/DEFER하며, 실 HTTP 호출·승인발급·TAM 연동 활성화 전 별도 계약 확정과 독립검증을 요구합니다. 이는 계약 설계 수용에 한정되며 PR 병합·A1 구현·DB 변경·배포·A2/C 활성화는 승인하지 않습니다.

### 8.2 Design Document Accepted

- **PR:** `https://github.com/taiengineering/tai-api/pull/587` (OPEN / DRAFT / UNMERGED at time of decision)
- **PR HEAD at time of Owner decision (R2):** `c1e939f69762204e7d736274caba41914e1efcfc`
- **Document blob at time of Owner decision (R2):** `8f22ad07b790f3f774370a911fc96d06e68f6fb3`
- **Document:** `docs/tam/TAM_CHEM_COMPATIBILITY_REVIEW_CONTRACT_ACCEPTANCE_PROPOSAL_20261010.md`

### 8.3 14-Row Decision Mapping

| Row | Owner Decision | Accepted design value / constraint |
|-----|---------------|-------------------------------------|
| C-DEP-03-A | ACCEPT | `consumer_type=CHEMICAL`, `business_object_type=COMPATIBILITY_REVIEW`; contract only |
| C-DEP-03-B | ACCEPT | `route_type_hint=PROCESS_TYPE`; absent competing hint → `AMBIGUOUS_ROUTE` where appropriate |
| C-DEP-03-C | ACCEPT | `scope_key=WMS_COMPATIBILITY_REVIEW`; no route record creation |
| C-DEP-03-D | ACCEPT | Server-generated `CHEM:COMPATIBILITY_REVIEW:{review_id}`; payload conflict 409 |
| C-DEP-03-E | ACCEPT | Server-resolved `factory_id`, non-null in CHEM binding |
| C-DEP-03-F | ACCEPT | Server-stored, non-empty `evidence_ref=review.evaluation_ref` |
| C-DEP-02-A | ACCEPT | Design target `GET /v1/tam/requests/{tam_request_id}` only; not implemented |
| C-DEP-02-B | ACCEPT | 15 semantic response fields; outer JSON success envelope H-deferred |
| C-DEP-02-C | ACCEPT | `approved_by` from completing `tam_approval_decisions.actor_user_id` |
| C-DEP-02-D | ACCEPT | `approved_at = tam_approval_requests.completed_at`, not `decided_at` |
| C-DEP-02-E | ACCEPT | Error-classification semantics only: trusted tenant 404 vs unregistered route 404; wire/envelope trust H-deferred |
| C-DEP-02-F | ACCEPT | Six-field binding verification; valid mismatch 409; malformed 503; before CHEM approval INSERT |
| C-DEP-02-G | ACCEPT | Non-APPROVED 422; malformed provenance 503; valid APPROVED but `effective=false` → 422 |
| C-DEP-02-H | MODIFY / DEFER — A1 MOCK ONLY | NOT ACCEPTED FOR LIVE TRANSPORT. Caller credentials, auth, exact JSON wire envelope, authenticated 404, TLS/retries/timeout and authorization rules require separate design, Owner decision and GPT verification before real HTTP/activation |

### 8.4 Scope Limits

- This acceptance covers **design contract only** as described in this document at R2 HEAD `c1e939f69762204e7d736274caba41914e1efcfc`
- **PR #587 must remain DRAFT/UNMERGED** until separate Owner merge authorization
- **A1 implementation is NOT AUTHORIZED** — requires separate GPT WO + Owner authorization after GPT independent receipt verification
- **C-DEP-02-H live wire spec is NOT ACCEPTED** — no real TAM HTTP call, no approval issuance, no transport implementation until full H spec is accepted
- **A2/C/D remain BLOCKED**; B not started
- **CODE_CHANGE = 0, SQL_MIGRATION = 0, DB_WRITE = 0, DEPLOY = 0, TAM_ACTIVATION = 0, PROVIDER_ACTIVATION = 0, MERGE = 0**
- C-DEP-09 remains OPEN / OWNER ACCEPTANCE PENDING (separate from this 14-row decision)

### 8.5 Required Next Steps

1. **GPT independent verification** of this receipt document and commit (GPT_POST_RECEIPT_VERIFY = REQUIRED)
2. Separate Owner authorization to merge PR #587 (if desired)
3. Separate GPT WO + Owner authorization for A1 dormant/mock-only implementation (after receipt verified)
4. Full C-DEP-02-H spec + acceptance + GPT verification before any live TAM transport implementation or A2 activation

---

## 9. Result Block

```text
CHEM WP-07I TAM C-DEP-02/03 OWNER DECISION RECEIPT RESULT
CHEM_MAIN_SHA              = afa58f0388d391881f6f6c3252a549f8390dde9c
TAM_MAIN_SHA_SOURCE_ANCHOR = c9c5f2689ef3df030781ba9985750ce9b800f5e4
TAM_MAIN_SHA_PR_BASE       = 393d4c239ae531b10b44961143bab9125c1fc84d
TAM_PR                     = https://github.com/taiengineering/tai-api/pull/587  (OPEN / DRAFT / UNMERGED)
TAM_PR_BASE_SHA            = 393d4c239ae531b10b44961143bab9125c1fc84d
TAM_PR_R1_HEAD_SHA         = a92ef8da97587d286aa8bfd6aec0ea41197ba920
TAM_PR_R2_HEAD_SHA         = c1e939f69762204e7d736274caba41914e1efcfc  (PRE-EDIT HEAD)
TAM_PR_R2_DOC_BLOB         = 8f22ad07b790f3f774370a911fc96d06e68f6fb3  (PRE-EDIT BLOB)
FILE_CHANGED               = docs/tam/TAM_CHEM_COMPATIBILITY_REVIEW_CONTRACT_ACCEPTANCE_PROPOSAL_20261010.md
OWNER_DECISION             = Option 1 — 2026-10-10 KST (Owner-provided conversation transcript)
C_DEP_03_A_TO_F            = 6 ACCEPTED (DESIGN CONTRACT / A1 MOCK-ONLY)
C_DEP_02_A_TO_G            = 7 ACCEPTED (DESIGN CONTRACT / A1 MOCK-ONLY)
C_DEP_02_H                 = MODIFY / DEFER (LIVE WIRE BLOCKED)
C_DEP_09                   = OPEN / OWNER ACCEPTANCE PENDING
POST_HEAD                  = recorded separately in executor evidence receipt
POST_DOC_BLOB              = recorded separately in executor evidence receipt
CODE_CHANGE                = 0
MIGRATION                  = 0
DB_WRITE                   = 0
DEPLOY                     = 0
MERGE                      = 0
TAM_ACTIVATION             = 0
PROVIDER_ACTIVATION        = 0
A1_IMPLEMENTATION          = NOT AUTHORIZED
GPT_INDEPENDENT_VERIFY     = REQUIRED
GPT_POST_RECEIPT_VERIFY    = REQUIRED
```
