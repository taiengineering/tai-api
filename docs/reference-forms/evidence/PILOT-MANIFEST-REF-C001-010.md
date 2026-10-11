# REF-01 PILOT EVIDENCE MANIFEST — REF-C001~010
Date: 2026-10-08
WO: WO-REF01-CLAUDE-SOURCE-AUDIT-PILOT-039
Investigator: Claude Code (collect/evidence only)

## S0 PREFLIGHT
| Item | Value |
|---|---|
| Branch | docs/tai-reference-forms-charter-obj-20261008 |
| Branch HEAD SHA | 01e67b9589f9e94fb8f65127f4b83d1f1d9831b7 |
| Supabase project | vwlahtguyggrhvslabax |
| Table | public.ref_form_research_items |
| DB row count | 189 ✓ (confirmed via SELECT COUNT(*)) |
| RLS | ENABLED (rowsecurity=true) |
| REF-C001~010 baseline | source_url=NULL, source_document_access=NOT_CHECKED, observed_fields=[], source_fields_status=FIELDS_UNVERIFIED (all 10 identical) |
| Tooling | curl, python3 (HWP/ZIP not testable — file download blocked before reaching that stage) |

## S1 SOURCE RETRIEVAL — OUTCOME: DOWNLOAD_FAILED / API_AUTH_BLOCKED

### Target URL (WO-specified, read-only)
https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view

### Access probes
| Probe | Method | URL | Result |
|---|---|---|---|
| Page load | GET | https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?... | HTTP 200, 1993 bytes — Vue.js SPA shell only |
| API config | GET | /stdtboard/js/kosha-tboard-config.js | HTTP 200 — obtained API root=/api/compn24/auth |
| Board detail API | POST JSON | /api/compn24/auth/stdtboard/api.do | HTTP 200, error: "permission error" / "API 권한 조회 중 오류가 발생했습니다" |
| Token refresh | POST | /api/compn24/auth/token/refresh | HTTP 401 Unauthorized |
| Direct tboard API | POST | /stdtboard/api.do | HTTP 405 Not Allowed |
| OSHRI crosspost | GET | https://oshri.kosha.or.kr/kosha/intro/...articleNo=449234 | HTTP 200, 380 bytes — site inactive (redirect to about:blank) |
| File download direct | GET | /api/compn24/auth/stdtboard/fileDownload.do?boardNo=141&articleNo=453942 | HTTP 200, 0 bytes (empty) |

### Root cause
KOSHA site is a Vue.js SPA (Single Page Application). All article content and file attachments are served via the tboard API at `/api/compn24/auth/stdtboard/api.do`. This API requires a valid Bearer JWT token obtained through a browser login/session initialization flow. Without a token, all boardDetail requests return `{"code":-1,"message":"error","subCode":-1,"subMessage":"API 권한 조회 중 오류가 발생했습니다"}`. The token refresh endpoint requires an existing valid session (HTTP 401). No guest/anonymous token path available.

### Access error code
ERROR_CODE: KOSHA_TBOARD_API_AUTH_REQUIRED
- Page URL: HTTP 200 (SPA shell — no content)
- Attachment URL: UNAVAILABLE (blocked before URL retrieval)
- File bytes: NOT_OBTAINED
- File hash: NOT_OBTAINED

## S1 RESULT PER ID (all 10 from same source)

| ID | Title | Source attachment | S1 result | Reason |
|---|---|---|---|---|
| REF-C001 | 안전보건경영방침 | 붙임2 HWP | DOWNLOAD_FAILED | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C002 | 안전보건활동 목표/세부 추진계획 | 붙임2 HWP | DOWNLOAD_FAILED | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C003 | 위험기계·기구·설비 목록 작성 서식 | 붙임2 HWP | DOWNLOAD_FAILED | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C004 | 유해·위험물질 목록 작성 서식 | 붙임2 HWP | DOWNLOAD_FAILED | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C005 | 작업별 위험과관리 대장 | 붙임2 HWP | DOWNLOAD_FAILED | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C006 | 위험성평가표(빈도강도법) | 붙임2 HWP | DOWNLOAD_FAILED | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C007 | 안전보건예산 편성 서식 | 붙임2 HWP | DOWNLOAD_FAILED | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C008 | 안전보건 전문이력 평가 기준 및 평가표 | 붙임2 HWP | DOWNLOAD_FAILED | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C009 | 안전보건 전문인력 등 배치표 및 담당업무 | 붙임2 HWP | DOWNLOAD_FAILED | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C010 | 사고 발생 대응 시나리오(처리 흐름도) | 붙임2 HWP | DOWNLOAD_FAILED | KOSHA_TBOARD_API_AUTH_REQUIRED |

## S2 PARSE — BLOCKED
Cannot parse: no file obtained.

## S3 RIGHTS
Known from source report 03:
> "KOSHA statement: posted reference forms may be modified to the workplace context. This is NOT an explicit general grant of commercial redistribution or an authoritative legal obligation determination."
Source: https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view (page content observed in prior research, not independently re-verified in this pilot due to API auth block)
Rights status: RIGHTS_UNVERIFIED (no change)

## S4 MANIFEST FIELDS PER ID
All 10 IDs share identical manifest entries:

| Field | Value |
|---|---|
| source_url | https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view |
| source_attachment_url | UNAVAILABLE (API auth blocked) |
| SHA256 checksum | NOT_OBTAINED |
| byte count | NOT_OBTAINED |
| MIME | NOT_OBTAINED |
| page/section | 붙임2 HWP (from prior research — not independently re-verified) |
| observed_fields | [] (no file accessed) |
| error code | KOSHA_TBOARD_API_AUTH_REQUIRED |
| usage rights | RIGHTS_UNVERIFIED |

## S5 DB SQL EVIDENCE

### BEFORE (all 10 rows)
source_url=NULL, source_document_access=NOT_CHECKED, source_observation_note="Official webpage lists document names, attachments HWP or ZIP unread. Zero original input fields confirmed."

### SQL executed
```sql
UPDATE public.ref_form_research_items
SET
  source_url              = 'https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view',
  source_document_access  = 'PAGE_ACCESSIBLE_FILE_AUTH_BLOCKED',
  source_observation_note = source_observation_note || ' | 2026-10-08 PILOT: KOSHA tboard API requires Bearer token for boardDetail. GET page=HTTP200 SPA shell. POST /api/compn24/auth/stdtboard/api.do = permission error. Token refresh = HTTP401. Attachment URL and file bytes NOT obtained.',
  updated_at              = now()
WHERE research_id IN (
  'REF-C001','REF-C002','REF-C003','REF-C004','REF-C005',
  'REF-C006','REF-C007','REF-C008','REF-C009','REF-C010'
)
AND source_url IS NULL
AND source_document_access = 'NOT_CHECKED';
```

### AFTER (all 10 rows)
- has_url: true (source_url set)
- source_document_access: PAGE_ACCESSIBLE_FILE_AUTH_BLOCKED
- source_fields_status: FIELDS_UNVERIFIED (unchanged ✓)
- owner_approval_status: NOT_REQUESTED (unchanged ✓)
- publication_status: NOT_READY (unchanged ✓)
- review_status: IN_PROGRESS (unchanged ✓)
- Total DB rows: 189 (unchanged ✓)
- updated_count confirmed: 10

Fields NOT updated:
- source_attachment_url (remains NULL)
- source_document_checksum (remains NULL)
- observed_fields (remains [])
- source_fields_status (remains FIELDS_UNVERIFIED)

## S6 RECEIPT SUMMARY
| ID | Status | Field count | Hash | Note |
|---|---|---|---|---|
| REF-C001 | DOWNLOAD_FAILED | 0 | N/A | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C002 | DOWNLOAD_FAILED | 0 | N/A | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C003 | DOWNLOAD_FAILED | 0 | N/A | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C004 | DOWNLOAD_FAILED | 0 | N/A | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C005 | DOWNLOAD_FAILED | 0 | N/A | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C006 | DOWNLOAD_FAILED | 0 | N/A | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C007 | DOWNLOAD_FAILED | 0 | N/A | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C008 | DOWNLOAD_FAILED | 0 | N/A | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C009 | DOWNLOAD_FAILED | 0 | N/A | KOSHA_TBOARD_API_AUTH_REQUIRED |
| REF-C010 | DOWNLOAD_FAILED | 0 | N/A | KOSHA_TBOARD_API_AUTH_REQUIRED |

## GIT RECEIPT
- Path: docs/reference-forms/evidence/PILOT-MANIFEST-REF-C001-010.md
- Branch: docs/tai-reference-forms-charter-obj-20261008
- No third-party attachment bytes committed

FINAL: PARTIAL (PREFLIGHT PASS, SOURCE RETRIEVAL BLOCKED)
DO_NOT_EXPAND = TRUE
