# GIT_DEPLOYMENT_IDENTITY

조사일: 2026-10-07
작업: WO-DOC-OBJ00-READONLY-DISCOVERY-001

---

## tai-api

| 항목 | 값 |
|---|---|
| local HEAD | `aa46bbb7ed07416784f3310681540c9fce7eef92` |
| origin/main | `939ef60ba3c43f2ac0ff6a0256a787ebf05bd1aa` |
| branch | main |
| local vs origin | DIVERGED — local main = aa46bbb7, origin/main = 939ef60b |
| last local commit | `fix(migrations): normalize duplicate version identities for 5 debt migrations (#532)` |
| last origin commit | 별도 커밋 존재 (fetch 후 확인) |
| OBJ00 기준 branch | `origin/docs/integrated-search-document-plan-20261007` → SHA `ad91df39c3dfab03c380387435ef90999386fcd7` |

### 최근 5 커밋 (local main)
```
aa46bbb7 fix(migrations): normalize duplicate version identities for 5 debt migrations (#532)
39e735cf feat(public-data-sync): add WP-1B runtime state foundation (#531)
8d3116a5 feat(h02-p1): legal occupancy capacity calculator and assessment source (#530)
16612104 feat(public-data-sync): add WP-1A control plane foundation (#528)
3e75cfae fix(lfr): close H02 direct occupancy assertion path
```

---

## tai-admin

| 항목 | 값 |
|---|---|
| local HEAD | `94f2491c468df73d2a50e50551a51a5a6de44224` |
| origin/main | `94f2491c468df73d2a50e50551a51a5a6de44224` |
| branch | main |
| local vs origin | IN SYNC |
| last commit | `feat(build): WO-QA-H3B-SAFE-BUILD-IDENTITY — SAFE/SaaS vue3 deployment identity (#131)` |

---

## 45cminc/doc

| 항목 | 값 |
|---|---|
| main SHA | `218091f6adc0895294ac6c9da74f565e557084ea` |
| last pushed | 2026-06-24T10:35:51Z |
| last commit message | `feat(docling): PaddleOCR 설치 추가` |
| 로컬 clone | NOT FOUND — GitHub API로만 접근 |

---

## Railway

| 항목 | 값 |
|---|---|
| tai-api project_id | `7c3ab53b-feb6-40a4-a4f0-7ade3f6e524b` |
| production env_id | `9dacb6f0-5d2a-4064-839e-e050af50bf30` |
| list_deployments | UNAUTHORIZED (API token 권한 부족) |
| deployed commit | UNVERIFIED — Railway deployment API 접근 불가 |
| Gotenberg service | Railway project 내 존재 여부 UNVERIFIED |

---

## Supabase (tai-api DB)

| 항목 | 값 |
|---|---|
| project_id | `vwlahtguyggrhvslabax` |
| URL | `https://vwlahtguyggrhvslabax.supabase.co` |
| connection method | MCP mcp__claude_ai_guri__execute_sql |
| 로컬 link | NOT LINKED (supabase status = not linked) |

---

## Anchor vs 기대값 비교

| 레포 | 기대값 (master plan) | 실측값 | 일치 |
|---|---|---|---|
| tai-api | `aa46bbb7ed07416784f3310681540c9fce7eef92` | `aa46bbb7ed07416784f3310681540c9fce7eef92` | YES |
| tai-admin | `94f2491c468df73d2a50e50551a51a5a6de44224` | `94f2491c468df73d2a50e50551a51a5a6de44224` | YES |
| 45cminc/doc | `218091f6adc0895294ac6c9da74f565e557084ea` | `218091f6adc0895294ac6c9da74f565e557084ea` | YES |

---

## Post-Discovery Verification Note (CORR-B)

GPT 독립검증 2026-10-07 확인 내용.

```
OBJ00 조사 시 local tai-api main:
  aa46bbb7ed07416784f3310681540c9fce7eef92

현재 remote main (독립검증 시점):
  939ef60ba3c43f2ac0ff6a0256a787ebf05bd1aa

difference: 1 commit
  commit: feat(public-data-sync): WP-1C-B1 heartbeat (또는 유사)

document-engine scope changed: NO
changed scope: public-data-sync / KOSHA adapter only

판정: OBJ00 조사 결과는 aa46bbb7 기준으로 유효하며 재조사 불필요.
```
