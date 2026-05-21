# 45CM — Contract Federated Semantic Engine Architecture

**Work Order v1**  
**Date:** 2026-05-21  
**Organization:** 45cminc  
**Scope:** 12 Phases · 9 Deliverables

---

## Document Overview

This work order defines the restructuring of the 45CM platform from a shared-runtime monolith to a **Contract Federated Semantic Engine Architecture**. The current Runtime/Engine documents, designed around a shared runtime model, will be fully reorganized under the federation contract paradigm.

The document covers 12 phases spanning repository structure, contract layer definition, semantic boundaries, signal standards, projection reconstruction, database federation, deployment federation, and migration planning.

---

## Core Philosophy

### Foundational Principle

> **45CM = Contract Federated Semantic Runtime Ecosystem**

### Engine Internal: Semantic Runtime

✅ **ALLOWED:** Rich semantic runtime inside each engine

Each engine operates on human-meaning-based semantics within its own boundary:

- Legal semantics (법령 의미)
- Marketing semantics (마케팅 의미)
- CRM semantics (CRM 의미)
- Monitoring semantics (관제 의미)

### Engine External: Machine Federation Contract

✅ **ALLOWED:** Machine contract signals only between engines  
❌ **FORBIDDEN:** Human language between engines  
❌ **FORBIDDEN:** Business-meaning interpretation between engines  
❌ **FORBIDDEN:** Shared runtime between engines

### Human Language Generation

Natural language is generated exclusively in the **Projection / Monitoring Layer**. Engines never produce or consume human-readable text across boundaries.

### Architecture Flow

```
Independent Semantic Engines
        ↓
Machine Federation Contract
        ↓
Projection Reconstruction
        ↓
Human Operational Feed
```

---

## Absolute Rules

### Forbidden: Shared Runtime

| Forbidden Construct | Reason |
|---------------------|--------|
| runtime_task | Cross-engine task ownership |
| runtime_schedule | Cross-engine scheduling |
| runtime_instance | Cross-engine instance sharing |
| shared assignment | Cross-engine work assignment |
| shared workflow | Cross-engine workflow orchestration |
| shared evidence | Cross-engine evidence store |

### Forbidden: Semantic Federation

❌ Cross-engine semantic translation  
❌ Engine-to-engine meaning interpretation

### Forbidden: Human Language Federation

❌ Natural language in inter-engine communication

### Allowed: Machine Contract Federation

✅ Typed, minimal, machine-readable signals between engines

```json
{ "signal": "ACTION_REQUIRED", "severity": 4, "source_engine": "legal" }
```

---

## Phase 1 — Repository Federation Structure

### 1.1 Target Structure (45cminc org)

| Repository | Type | Purpose |
|-----------|------|--------|
| **federation-contracts** | Contract Layer | All inter-engine contract documents |
| **projection-engine** | Engine | Semantic reconstruction for human feed |
| **monitoring-engine** | Engine | Federation signal aggregation + projection |
| **legal-runtime-engine** | Engine | Legal domain semantic runtime |
| **marketing-runtime-engine** | Engine | Marketing domain semantic runtime |
| **crm-runtime-engine** | Engine | CRM domain semantic runtime |
| **qa-runtime-engine** | Engine | QA domain semantic runtime |
| **identity-engine** | Engine | User/tenant identity management |
| **permission-engine** | Engine | Access control + authorization |
| **billing-engine** | Engine | Billing + subscription management |
| **analytics-engine** | Engine | Analytics aggregation |
| **notification-engine** | Engine | Notification dispatch |
| **ui-shell** | Surface | Unified application shell |
| **ui-design-system** | Surface | Shared design tokens + components |

### 1.2 Current → Target Repo Mapping

| Current Repo | → | Target Repo | Notes |
|-------------|---|------------|-------|
| taieng | → | legal-runtime-engine | 45cm code stripped |
| 45cm / 45cm-mkt | → | marketing-runtime-engine | 45cm repo is canonical |
| 45cm-ops | → | monitoring-engine | Docs migration |
| tai-admin | → | ui-shell / projection-engine | Role split TBD |

---

## Phase 2 — Federation Contract Layer

### 2.1 Purpose

Remove all shared implementation. Retain only shared contracts (specifications). The `federation-contracts` repository becomes the single source of truth for all inter-engine communication rules.

### 2.2 Contract Documents

| Document | Purpose |
|----------|--------|
| engine-input-contract.md | Standard input format every engine must accept |
| engine-output-contract.md | Standard output format every engine must produce |
| federation-signal-contract.md | Machine signal vocabulary + severity levels |
| semantic-boundary-contract.md | Semantic isolation rules between engines |
| projection-contract.md | Projection reconstruction specification |
| routing-contract.md | Federation routing + dispatch rules |
| trace-contract.md | Distributed trace propagation format |
| identity-contract.md | User/tenant identity grammar |

---

## Phase 3 — Semantic Boundary

### 3.1 Purpose

Prevent semantic contamination across engine boundaries.

### 3.2 Rules

✅ **Engine Internal:** Rich semantic runtime (domain-specific types, logic, validation)  
❌ **Engine External:** Only low-semantic machine signals permitted  
❌ **Cross-engine semantic translation** of any kind

Example: The legal engine understands "법령 위반" internally, but externally it only emits:

```json
{ "signal": "ACTION_REQUIRED", "severity": 4, "source_engine": "legal" }
```

The receiving engine never interprets what "ACTION_REQUIRED from legal" means in legal terms.

---

## Phase 4 — Federation Signal Specification

### 4.1 Permitted Signal Vocabulary

| Signal | Meaning |
|--------|---------|
| **INFO** | Informational event, no action needed |
| **WARNING** | Potential issue, attention recommended |
| **CRITICAL** | Severe issue, immediate attention required |
| **ACTION_REQUIRED** | Human action needed from receiving context |
| **APPROVAL_REQUIRED** | Human approval gate |
| **BLOCKED** | Process blocked, cannot proceed |
| **HEALTHY** | Normal operation confirmed |

### 4.2 Forbidden Signals

❌ Semantic-heavy signals:
- `legal.overdue.training` (leaks legal domain semantics)
- `marketing.channel.dead` (leaks marketing domain semantics)
- `crm.customer.churning` (leaks CRM domain semantics)

---

## Phase 5 — Projection Reconstruction

### 5.1 Principle

Human language generation occurs exclusively in the `projection-engine`.

### 5.2 Flow

```
Engine emits machine signal
    ↓
Federation routes signal to projection-engine
    ↓
Projection reconstructs human-readable meaning
    ↓
Human sees operational feed entry
```

❌ Human semantic exchange between engines  
✅ Projection-engine as sole human language generator

---

## Phase 6 — Monitoring/Projection Role

### 6.1 Definition

The monitoring engine is redefined as a **Semantic Reconstruction Engine**.

### 6.2 Flow

```
Machine Federation Signals (from all engines)
    ↓
Semantic Reconstruction (monitoring-engine)
    ↓
Human Operational Projection
```

### 6.3 Boundaries

❌ Runtime ownership  
❌ Cross-engine mutation  
✅ Signal aggregation + semantic reconstruction + projection

---

## Phase 7 — Engine Runtime Boundary

### 7.1 Ownership Matrix

| Resource | Rule |
|----------|------|
| **Runtime** | Engine owns its own process, scheduler, queue processor |
| **Database** | Engine owns dedicated DB schema/project (no cross-engine queries) |
| **API** | Engine exposes its own API endpoints |
| **Queue** | Engine owns its own message queue / BullMQ instance |
| **Storage** | Engine owns its own file/object storage namespace |
| **Deployment** | Engine deploys independently (own Railway/Fly service) |

---

## Phase 8 — Supabase Federation

| Engine | Supabase | Status |
|--------|----------|--------|
| legal-runtime-engine | Independent project | Existing (tai-api) |
| marketing-runtime-engine | Independent project | TBD |
| monitoring-engine | Independent project | TBD |
| crm-runtime-engine | Independent project | TBD |
| analytics-engine | Independent project | TBD |

❌ **Cross-engine DB queries of any kind**

---

## Phase 9 — Railway Federation

| Engine | Railway Service | Status |
|--------|----------------|--------|
| legal-runtime-engine | Independent | On Fly.io currently |
| marketing-runtime-engine | Independent | Current (taieng repo) |
| monitoring-engine | Independent | TBD |
| crm-runtime-engine | Independent | TBD |

---

## Phase 10 — Unified Feed Redesign

### Forbidden: Function Menus

❌ Domain-specific menu structure ("법령" / "마케팅" / "CRM" tabs)

### Target: Operational Feed

- 오늘 상태 (Today's status)
- 이벤트 (Events)
- 위험 (Risks)
- 승인 대기 (Pending approvals)
- 작업 흐름 (Workflow progress)

All items are projections from engine signals.

---

## Phase 11 — Future Engine Expansion

### Planned Engines

| Engine | Domain |
|--------|--------|
| finance-engine | Financial operations + accounting |
| hr-engine | Human resources management |
| logistics-engine | Supply chain + logistics |
| procurement-engine | Procurement + vendor management |
| document-engine | Document management + generation |
| automation-engine | Workflow automation |
| ai-assistant-engine | AI-powered assistance |
| scheduling-engine | Scheduling + calendar management |

### Expansion Principle

✅ Semantic runtime internally  
✅ Machine federation externally  
❌ Any deviation from the contract federation model

---

## Phase 12 — Migration Master Plan

| Step | Action | Detail |
|------|--------|--------|
| 1 | Contract Layer Extraction | Define and publish all federation-contracts docs |
| 2 | Semantic Boundary Enforcement | Audit all engines for semantic leakage, refactor |
| 3 | Runtime Namespace Separation | Remove all shared runtime constructs |
| 4 | Repository Split | Move code from taiengineering to 45cminc engine repos |
| 5 | Database Split | Create per-engine Supabase projects |
| 6 | Railway Split | Deploy each engine as independent Railway service |
| 7 | Machine Federation Build | Implement signal routing between engines |
| 8 | Projection Reconstruction Build | Build projection-engine for human feed generation |
| 9 | Unified Feed Migration | Replace function menus with operational feed |

---

## Required Deliverables

| # | Deliverable | Location |
|---|------------|----------|
| 1 | Federation Directory Structure | 45cminc/ org repos |
| 2 | Contract Layer Documents (8 docs) | federation-contracts/docs/ |
| 3 | Semantic Boundary Document | federation-contracts/docs/ |
| 4 | Machine Signal Specification | federation-contracts/docs/ |
| 5 | Projection Specification | federation-contracts/docs/ |
| 6 | Migration Master Plan | federation-contracts/docs/ |
| 7 | Repo Federation Plan | This document |
| 8 | DB Federation Plan | federation-contracts/docs/ |
| 9 | Railway Federation Plan | federation-contracts/docs/ |

---

## Closing Philosophy

> **엔진은 의미를 가진다.**  
> **Federation은 의미를 제거한다.**  
> **Projection이 의미를 복원한다.**  
> **엔진은 독립 진화한다.**  
> **연결은 Machine Contract만 허용한다.**

---

*End of Work Order — 45CM Federation Architecture v1*
