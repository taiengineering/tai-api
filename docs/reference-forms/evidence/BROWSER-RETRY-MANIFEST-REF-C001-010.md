# REF-01 BROWSER RETRY EVIDENCE MANIFEST — REF-C001~010
Date: 2026-10-08
WO: WO-REF01-KOSHA-BROWSER-RETRY-040
Investigator: Claude Code (collect/evidence only)
Note: Does NOT overwrite PILOT-MANIFEST-REF-C001-010.md

## Baseline at WO-040 start
- Branch HEAD (WO-039 commit): c13c49963645ea409e617d1d6dc70f0d6afa60f1
- DB total rows: 189
- REF-C001~010 status (from WO-039): source_url SET, source_document_access=PAGE_ACCESSIBLE_FILE_AUTH_BLOCKED

## Browser automation availability
- Tool: Playwright Python (installed at /opt/homebrew/bin/playwright)
- Browser: Chromium (~/Library/Caches/ms-playwright/chromium-1134, chromium-1243)
- Status: AVAILABLE ✓ (BROWSER_NOT_AVAILABLE does not apply)

## Browser probe — KOSHA article access test
Target: https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view

### API calls captured by Playwright (ALL /api/ calls)
| # | URL | HTTP Status | Body preview |
|---|---|---|---|
| 1 | /api/compn24/auth/token/refresh | **401** | `{"statusCode":401}` |
| 2 | /api/compn24/auth/v1/etc/menus | 200 | navigation menus (public) |

### Page render result
```
산업재해예방 안전보건공단
404
페이지가 존재하지 않거나, 사용할 수 없는 페이지입니다.
입력하신 주소가 정확한지 다시 한 번 확인해주세요.
```

### Root cause (definitive)
The KOSHA SPA initializes by calling `POST /api/compn24/auth/token/refresh`.
Without an existing valid session, this returns HTTP 401.
After the 401, the SPA does **NOT** attempt the `boardDetail` API call.
It renders a "404 page not found" error screen instead.
The boardDetail API (`/api/compn24/auth/stdtboard/api.do`) was NEVER called.

This means: the KOSHA article content (not just file download) requires a valid KOSHA user login session. This is a structural site requirement, not a temporary API misconfiguration.

### WO-040 decision gate
> "If login required, STOP; do not manufacture or capture bearer JWT."

Result: **LOGIN_REQUIRED → STOP**

No login bypass attempted. No token manufactured. No credential extraction.

## S1 RESULT PER ID (unchanged from WO-039, now confirmed by browser)

| ID | Title | Attachment | WO-039 result | WO-040 confirmation |
|---|---|---|---|---|
| REF-C001 | 안전보건경영방침 | 붙임2 HWP | DOWNLOAD_FAILED | ARTICLE_LOGIN_REQUIRED confirmed |
| REF-C002 | 안전보건활동 목표/세부 추진계획 | 붙임2 HWP | DOWNLOAD_FAILED | ARTICLE_LOGIN_REQUIRED confirmed |
| REF-C003 | 위험기계·기구·설비 목록 작성 서식 | 붙임2 HWP | DOWNLOAD_FAILED | ARTICLE_LOGIN_REQUIRED confirmed |
| REF-C004 | 유해·위험물질 목록 작성 서식 | 붙임2 HWP | DOWNLOAD_FAILED | ARTICLE_LOGIN_REQUIRED confirmed |
| REF-C005 | 작업별 위험과관리 대장 | 붙임2 HWP | DOWNLOAD_FAILED | ARTICLE_LOGIN_REQUIRED confirmed |
| REF-C006 | 위험성평가표(빈도강도법) | 붙임2 HWP | DOWNLOAD_FAILED | ARTICLE_LOGIN_REQUIRED confirmed |
| REF-C007 | 안전보건예산 편성 서식 | 붙임2 HWP | DOWNLOAD_FAILED | ARTICLE_LOGIN_REQUIRED confirmed |
| REF-C008 | 안전보건 전문이력 평가 기준 및 평가표 | 붙임2 HWP | DOWNLOAD_FAILED | ARTICLE_LOGIN_REQUIRED confirmed |
| REF-C009 | 안전보건 전문인력 등 배치표 및 담당업무 | 붙임2 HWP | DOWNLOAD_FAILED | ARTICLE_LOGIN_REQUIRED confirmed |
| REF-C010 | 사고 발생 대응 시나리오(처리 흐름도) | 붙임2 HWP | DOWNLOAD_FAILED | ARTICLE_LOGIN_REQUIRED confirmed |

## DB SQL EVIDENCE

### BEFORE (WO-040 start)
source_document_access = PAGE_ACCESSIBLE_FILE_AUTH_BLOCKED (10 rows)

### UPDATE executed
```sql
UPDATE public.ref_form_research_items
SET
  source_document_access  = 'ARTICLE_LOGIN_REQUIRED',
  source_observation_note = source_observation_note || ' | 2026-10-08 WO-040 BROWSER RETRY: ...',
  updated_at              = now()
WHERE research_id IN ('REF-C001',...,'REF-C010')
AND source_document_access = 'PAGE_ACCESSIBLE_FILE_AUTH_BLOCKED';
```

### AFTER
- updated_count: 10 ✓
- source_document_access: ARTICLE_LOGIN_REQUIRED (all 10)
- source_fields_status: FIELDS_UNVERIFIED (unchanged ✓)
- owner_approval_status: NOT_REQUESTED (unchanged ✓)
- publication_status: NOT_READY (unchanged ✓)
- review_status: IN_PROGRESS (unchanged ✓)
- observed_fields: [] (unchanged ✓)
- Total DB rows: 189 (unchanged ✓)

Fields NOT updated:
- source_attachment_url (remains NULL — URL never retrieved)
- source_document_checksum (remains NULL)
- observed_fields (remains [] — no file obtained)

## GIT RECEIPT
- This file: docs/reference-forms/evidence/BROWSER-RETRY-MANIFEST-REF-C001-010.md
- Branch: docs/tai-reference-forms-charter-obj-20261008
- Screenshot saved locally: /tmp/ref01_evidence/kosha_page_screenshot.png (NOT committed — local evidence only)
- No third-party file bytes committed

## Open question for GPT
The KOSHA article is indexed by search engines showing 5 attachments (붙임2 HWP etc.), but the live article now requires login. Options for GPT to decide:
1. Is there an authorized KOSHA account that Owner can use to download the HWP?
2. Is there a direct file download URL derivable from the article metadata (file number)?
3. Is the board accessible without login from a different KOSHA subdomain/path?
4. Should source be changed to a different publicly accessible KOSHA posting of the same material?

FINAL: BLOCKED (ARTICLE_LOGIN_REQUIRED)
DO_NOT_EXPAND = TRUE
