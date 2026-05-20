# TAI Engineering — Repository Structure Analysis Report

**Analysis Date:** 2026-05-20  
**Organizations:** taiengineering (10 repos) / 45cminc (4 repos)  
**Status:** Migration Planning Phase

---

## 1. Overview

- **taiengineering org** (GitHub User): 10 repos
- **45cminc org** (GitHub Organization): 4 repos (all empty placeholders)

TAI Engineering operates two separate product lines sharing a single GitHub account: the TAI industrial safety AI platform and the 45cm marketing operations engine. This report documents the current state of all repositories, their deployment dependencies, code evolution patterns, and risk assessment for the planned migration to the 45cminc organization.

---

## 2. Full Repository Inventory

### 2.1 taiengineering (10 repos)

| Repo | Language | Description | Deploy | Status |
|------|----------|-------------|--------|--------|
| **tai-api** | Python/FastAPI | TAI core platform API. app/, engine/, routers/, services/, models/, schemas/, sql/, supabase/, watch_engine/, workflow_engine/ | Fly.io (nrt) | ✅ ACTIVE |
| **tai-admin** | HTML/JS | Admin dashboard + mobile app (Capacitor). admin/, site/, taieng/, payment/, request/, mobile/, android/ | CF Pages | ✅ ACTIVE |
| **taieng** | TS/Node | ⚠️ MIXED monorepo. apps/marketing-\*, packages/core-\*, nexas, legacy-taieng-public, cloudflare-worker. pnpm+turbo | Railway | ⚠️ FROZEN |
| **45cm** | TS/Node | NEW canonical monorepo. engines/marketing-engine/{api,worker,scheduler,runtime,channels,domain}, platform/\*, surfaces/{admin,app-shell}. Next.js+React+MUI | (Dockerfile) | ✅ ACTIVE DEV |
| **45cm-mkt** | TS/Node | Marketing engine extraction. apps/marketing-api, marketing-worker. Intermediate step from taieng | (Dockerfile) | ⏸ SUPERSEDED |
| **45cm-ui** | TS | Shared UI package scaffold. src/index.ts, theme.ts, layout/ | - | SCAFFOLD |
| **tai-engineering** | - | Docs only. docs/watch-engine/TAI_Watch_Engine_v1_Spec.md | - | DOCS ONLY |
| **45cm-runtime** | - | Empty repo. README.md + empty docs file | - | ❌ EMPTY |
| **45cm-ops** | - | Single doc. docs/운영-qa-런타임-플랫폼.md | - | DOCS ONLY |
| **ui** | - | Duplicate of 45cm-ui (created in error, empty) | - | 🗑 DELETE |

### 2.2 45cminc (4 repos)

| Repo | Description | Created | Content |
|------|-------------|---------|--------|
| **www** | 45cm marketing site | 2026-05-20 | README only |
| **mkt** | Marketing Engine | 2026-05-20 | README only |
| **ui** | Shared UI package | 2026-05-20 | README only |
| **ops** | ODS control engine | 2026-05-20 | README only |

> All 45cminc repos are empty placeholder shells created on 2026-05-20. No code has been pushed yet.

---

## 3. Deployment Dependency Map

### 3.1 tai-api → Fly.io

- **App name:** tai-api-prod
- **Region:** Tokyo (nrt), latency ~25–35ms to Korea
- **Runtime:** Python/FastAPI on port 8080
- **DB:** Supabase (env-configured)
- **VM:** shared CPU, 512MB RAM, auto-stop enabled
- **Health check:** /health (UptimeRobot monitoring)

### 3.2 taieng → Railway — ⚠️ CRITICAL

Railway deploys **TWO services** from the taieng repo:

**Service 1 — Marketing Engine (nixpacks.toml):**  
Builds `@45cm/marketing-api` and `@45cm/marketing-worker` via pnpm, runs `node start-mkt.js` which spawns both API server (`apps/marketing-api/dist/server.js`) and BullMQ worker (`apps/marketing-worker/dist/worker.js`) in parallel with auto-restart logic.

**Service 2 — Naver Monitor (railway.toml):**  
Runs `python naver_monitor.py` as a daily cron job at UTC 00:00 (KST 09:00).

### 3.3 tai-admin → Cloudflare Pages

- Static HTML site with `_headers` and `_redirects` config
- Capacitor wrapper for Android mobile app
- Depends on tai-api for all backend API calls

---

## 4. Code Evolution Analysis

### 4.1 Evolution Path

The 45cm marketing engine code has evolved through three stages:

| Stage | Repo | Structure | Last Commit | Status |
|-------|------|-----------|-------------|--------|
| Stage 1 | **taieng** | apps/marketing-api, apps/marketing-worker, packages/core-\*-runtime | 2026-05-19 (docs only) | Code frozen |
| Stage 2 | **45cm-mkt** | apps/ structure (same as taieng) | 2026-05-16 | Superseded |
| Stage 3 | **45cm** ✅ | engines/marketing-engine/{api,worker,scheduler,runtime,channels,domain} | 2026-05-20 (today) | Active development |

### 4.2 Directory Structure Comparison

| taieng (original) | 45cm (new canonical) |
|-------------------|---------------------|
| apps/marketing-api/dist/server.js | engines/marketing-engine/api/dist/server.js |
| apps/marketing-worker/dist/worker.js | engines/marketing-engine/worker/dist/worker.js |
| packages/core-\*-runtime | engines/marketing-engine/runtime/\* |
| packages/channel-naver-kin | engines/marketing-engine/channels/\* |
| (no frontend) | surfaces/admin, surfaces/app-shell |
| (no infra config) | infra/ |

### 4.3 start-mkt.js Comparison

| Feature | taieng (2710B) | 45cm (570B) |
|---------|---------------|-------------|
| Auto-restart | ✅ Yes (3s API, 5s worker) | ❌ No |
| Logging prefix | ✅ Yes ([api], [worker]) | ❌ No (stdio:inherit) |
| Graceful shutdown | ✅ Yes (SIGTERM/SIGINT, 10s timeout) | Basic (5s timeout) |

---

## 5. Risk Assessment

| Risk | Item | Detail |
|------|------|--------|
| 🔴 **HIGH** | Railway deployment on taieng | nixpacks.toml builds marketing engine; railway.toml runs naver cron. If taieng repo is transferred, deleted, or has 45cm code removed, Railway deployment breaks immediately. |
| 🟡 **MID** | Code divergence taieng vs 45cm | Directory structures differ (apps/ vs engines/). start-mkt.js maturity differs. Unknown whether actual source files have diverged. |
| 🟡 **MID** | naver_monitor.py duplication | Same file exists in tai-api (18.8KB) and taieng (0B empty). Railway cron runs taieng version. Needs consolidation. |
| 🟢 **LOW** | Empty/duplicate repo cleanup | taiengineering/ui (empty duplicate), 45cm-runtime (empty), 45cm-ops (1 doc), tai-engineering (1 doc). |
| 🟢 **LOW** | 45cminc empty shells | All 4 repos (www, mkt, ui, ops) are README-only placeholders. |

---

## 6. Recommended Migration Plan

| Step | Action | Risk | Prerequisite |
|------|--------|------|--------------|
| 1 | Delete taiengineering/ui (empty duplicate) | None | - |
| 2 | Run file-level diff: taieng/apps vs 45cm/engines | None | - |
| 3 | Push 45cm repo content to 45cminc/mkt (or transfer) | Low | Step 2 result |
| 4 | Push 45cm-ui content to 45cminc/ui | Low | - |
| 5 | Move 45cm-ops docs to 45cminc/ops | Low | - |
| 6 | **Update Railway deployment: taieng → 45cminc/mkt** | **HIGH** | Steps 3 + testing |
| 7 | Separate naver_monitor.py into tai-api or dedicated service | Medium | Step 6 complete |
| 8 | Archive/delete superseded repos | Low | All above |

---

## 7. Target State After Migration

### 7.1 taiengineering (TAI only)

| Repo | Purpose | Deploy |
|------|---------|--------|
| **tai-api** | TAI industrial safety platform API | Fly.io (tai-api-prod, nrt) |
| **tai-admin** | TAI admin dashboard + mobile app | Cloudflare Pages |
| **tai-engineering** | TAI engineering docs (optional keep) | - |

### 7.2 45cminc (45cm only)

| Repo | Purpose | Deploy |
|------|---------|--------|
| **mkt** | 45cm marketing engine (engines/, platform/, surfaces/) | Railway |
| **www** | 45cm marketing website | TBD |
| **ui** | Shared UI package (design system, components, theme) | npm package |
| **ops** | ODS operational monitoring + docs | TBD |

---

## 8. Pending Decisions

1. **Railway deployment switch timing:** When to point Railway to 45cminc/mkt instead of taieng
2. **naver_monitor.py consolidation:** Move to tai-api (where the real code exists) or keep separate
3. **Code sync verification:** File-level diff between taieng/apps and 45cm/engines before declaring 45cm canonical
4. **taieng repo fate:** Archive entirely, or strip 45cm code and keep TAI-specific content (nexas, legacy-taieng-public, cloudflare-worker)

---

*End of Report — Generated 2026-05-20*
