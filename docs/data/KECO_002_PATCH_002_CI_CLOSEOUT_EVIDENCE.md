---
title: KECO 15149420 API — CHEM-WO-DATA-KECO-002-PATCH-002 CI Closeout Evidence
status: CLOSED
date: 2026-10-04
branch: feat/keco-reference-foundation
head_sha: 2dd3ce29f57f621ea7f4d1aea160232db33720cd
ci_run_id: "37200436287"
ci_conclusion: success
---

# KECO_002 PATCH-002 CI Closeout Evidence

## CI Run

| 항목 | 값 |
|------|-----|
| Run ID | 37200436287 |
| Branch | feat/keco-reference-foundation |
| HEAD SHA | 2dd3ce29f57f621ea7f4d1aea160232db33720cd |
| Triggered | 2026-10-04T11:56:53Z |
| Completed | 2026-10-04T11:59:52Z |
| Conclusion | **success** |

## Q001–Q016 체크리스트

| 코드 | 항목 | 결과 |
|------|------|------|
| Q001 | CI Time Guard = PASS | ✅ PASS |
| Q002 | CI Time no-expansion = PASS | ✅ PASS |
| Q003 | probe.py no-result sentinel = SEARCH_ENGLISH_NAME 방식 | ✅ PASS (`test_probe_noresult_sentinel_uses_english_name_search`) |
| Q004 | sentinel 값 = `TAI-PROBE-NORESULT-001` (CAS 아님) | ✅ PASS (동일 테스트) |
| Q005 | fail_run() serviceKey 값 + query-param 쌍 redact 실측 | ✅ PASS (`test_fail_run_redacts_secret_value`, `test_fail_run_redacts_servicekey_query_param`) |
| Q006 | error code 29 → ERROR_AUTH | ✅ PASS (`test_error_29_is_auth`) |
| Q007 | error code 29 in NON_RETRY_CODES | ✅ PASS (`test_error_29_in_non_retry`) |
| Q008 | KECO Reference Foundation tests = PASS (CI) | ✅ PASS |
| Q009 | KECO tests 실제 실행됨 (SKIPPED 아님) | ✅ PASS — 71 tests collected & run |
| Q010 | CI workflow conclusion = success | ✅ PASS |
| Q011 | store.py `datetime.now(timezone.utc)` 없음 | ✅ PASS — `_now_iso()` uses `serialize_business_datetime(now_kst())` |
| Q012 | store.py `from datetime import timezone` 없음 | ✅ PASS — import 완전 제거됨 |
| Q013 | fail_run() error_message 실제 redact 호출 | ✅ PASS — `redact_key(error_message, api_key)` 경로 확인 |
| Q014 | probe NORESULT sentinel = SEARCH_ENGLISH_NAME (SEARCH_CAS 아님) | ✅ PASS |
| Q015 | error code 29 = BLACKLIST_IP_ACCESS_ERROR → NON_RETRY | ✅ PASS |
| Q016 | 기존 테스트 회귀 없음 (71/71 PASS) | ✅ PASS |

## 로컬 테스트 실행 요약

```
71 passed in 0.20s
```

모든 71개 테스트 PASS. SKIPPED=0, FAILED=0.

## PATCH-002 변경 파일

| 파일 | 변경 내용 |
|------|-----------|
| `services/keco_chemical/store.py` | `datetime.now(timezone.utc)` → `serialize_business_datetime(now_kst())` + `fail_run()` redact 구현 |
| `services/keco_chemical/contract.py` | `NON_RETRY_CODES`에 `"29"` 추가 |
| `services/keco_chemical/client.py` | `_classify_error_code`에 `"29"` → AUTH 추가 |
| `services/keco_chemical/probe.py` | `PROBE_NORESULT_SENTINEL = "TAI-PROBE-NORESULT-001"` + `SEARCH_ENGLISH_NAME` 방식으로 변경 |
| `tests/test_keco_chemical.py` | Q003~Q007 대응 테스트 4건 추가 |

## 상태

**PATCH-002 CI CLOSEOUT: ALL PASS**

PR #507 (`feat/keco-reference-foundation`) HEAD `2dd3ce29` — GPT 독립검증 대기.
merge 금지 (GPT 독립검증 완료 전).
