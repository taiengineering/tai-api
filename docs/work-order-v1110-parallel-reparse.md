# v1.11.0 Cursor 작업지시서 — reparse 병렬 처리

## 목적
`_run_reparse_background` 함수의 순차 처리를 5건 병렬로 변경.
현재: 건당 87초, 1000건 = 22시간.
목표: 5건 병렬 + sleep 단축 → ~2시간.

## 대상 파일
`routers/law_rule_generator.py`

## 변경 — `_run_reparse_background` 함수 전체 교체

기존 `_run_reparse_background` 함수 전체를 아래로 교체하세요.
변경 포인트:
1. 5건씩 `asyncio.gather` 병렬 호출
2. `sleep(3)` → `sleep(0.5)` (배치 간)
3. 동일 법령 컨텍스트 캐시 (`_context_cache` dict)
4. 진행률 업데이트 10건마다 → 효율화
5. 기존 safe_update_master 그대로 사용

```python
async def _run_reparse_background(
    job_id: str, sector: str, limit_count: int,
    fill_empty_only: bool, rule_ids: List[str],
):
    """백그라운드에서 master 룰을 5건씩 병렬로 Sonnet 재파싱.
    v1.11.0: 순차 → 병렬 5건, sleep 단축, 컨텍스트 캐시."""
    supabase = get_supabase()
    CONCURRENCY = 5

    try:
        q = supabase.table("master_building_legal_rules").select("*").eq("is_active", True)
        if sector and sector != "ALL":
            q = q.eq("sector", sector)
        if rule_ids:
            q = q.in_("rule_id", rule_ids)
        rows = q.limit(max(limit_count * 3, 50)).execute().data or []
        targets = _pick_reparse_targets(rows, limit_count)

        supabase.table("reparse_job_log").update({
            "total_targeted": len(targets),
        }).eq("job_id", job_id).execute()

        processed = 0
        updated = 0
        skipped = 0
        errors_count = 0
        error_details: List[dict] = []
        changed_fields_total: Dict[str, int] = {}
        _context_cache: Dict[str, str] = {}  # law_name+law_article → context
        _few_shot_cache: Dict[str, list] = {}  # law_name → few_shots

        async def _process_one(row: dict) -> dict:
            """단일 룰 재파싱. 결과를 dict로 반환."""
            rid = row.get("rule_id") or ""
            law_name = row.get("law_name") or ""
            law_article = row.get("law_article") or ""
            result = {"status": "skip", "rid": rid, "saved": 0, "failed": 0}

            if not law_name or not law_article:
                return result

            try:
                # 컨텍스트 캐시
                cache_key = f"{law_name}|{law_article}"
                if cache_key not in _context_cache:
                    _context_cache[cache_key] = await build_full_context(law_name, law_article)
                full_context = _context_cache[cache_key]

                if law_name not in _few_shot_cache:
                    _few_shot_cache[law_name] = await _fetch_few_shot_examples(supabase, law_name, limit=3)
                few_shots = _few_shot_cache[law_name]

                prompt = _build_reparse_prompt(row, full_context, few_shots)

                parsed = await call_claude_messages_ai(
                    "빈 필드 보강 전용 리라이팅 모델입니다. JSON object 1개만 반환하세요.",
                    prompt,
                    CLAUDE_SONNET_MODEL,
                    _extract_json_payload,
                    ANTHROPIC_API_KEY,
                    max_tokens=1800,
                    timeout=90,
                )
                if not isinstance(parsed, dict):
                    return result

                patch: Dict[str, Any] = {}
                changed: Dict[str, int] = {}
                for key, value in parsed.items():
                    if key not in row:
                        continue
                    if fill_empty_only and not _is_blank(row.get(key)):
                        continue
                    if _is_blank(value):
                        continue
                    if row.get(key) != value:
                        patch[key] = value
                        changed[key] = 1

                if "submit_org_code" in patch:
                    patch["submit_org_code"] = _normalize_submit_org_code(patch["submit_org_code"])
                    if not patch["submit_org_code"]:
                        patch.pop("submit_org_code", None)
                        changed.pop("submit_org_code", None)

                if patch:
                    any_saved, s_count, f_count = safe_update_master(
                        supabase, row["id"], patch, rule_id=rid)
                    if any_saved:
                        result["status"] = "updated"
                        result["saved"] = s_count
                        result["failed"] = f_count
                        result["changed"] = changed
                    else:
                        result["status"] = "skip"
                    if f_count > 0:
                        result["error"] = f"partial: {s_count} saved, {f_count} type errors skipped"
                else:
                    result["status"] = "skip"

            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)[:200]
                _reparse_logger.warning(f"[reparse] {rid} 에러: {e}")

            return result

        # 배치 처리: CONCURRENCY건씩 병렬
        for i in range(0, len(targets), CONCURRENCY):
            batch = targets[i:i + CONCURRENCY]
            results = await asyncio.gather(
                *[_process_one(row) for row in batch],
                return_exceptions=True,
            )

            for res in results:
                processed += 1
                if isinstance(res, Exception):
                    errors_count += 1
                    error_details.append({"error": str(res)[:200]})
                    continue
                if res["status"] == "updated":
                    updated += 1
                    for k, v in res.get("changed", {}).items():
                        changed_fields_total[k] = changed_fields_total.get(k, 0) + v
                elif res["status"] == "error":
                    errors_count += 1
                    error_details.append({"rule_id": res["rid"], "error": res.get("error", "")})
                else:
                    skipped += 1

                if res.get("error") and res["status"] != "error":
                    error_details.append({"rule_id": res["rid"], "error": res["error"]})

            # 10건마다 진행률 업데이트
            if processed % 10 == 0 or processed == len(targets):
                supabase.table("reparse_job_log").update({
                    "processed": processed,
                    "updated": updated,
                    "skipped": skipped,
                    "errors": errors_count,
                    "error_details": error_details[-20:],
                    "changed_fields": changed_fields_total,
                }).eq("job_id", job_id).execute()

            # 배치 간 sleep (서버 부하 방지)
            await asyncio.sleep(0.5)

        # 전체 완료 → validate-master 실행
        validate_data = None
        try:
            validate_result = await validate_master({"sector": sector or "ALL"})
            validate_data = validate_result.get("data")
        except Exception as e:
            _reparse_logger.warning(f"[reparse] validate-master 실패: {e}")

        supabase.table("reparse_job_log").update({
            "status": "COMPLETED",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "processed": processed,
            "updated": updated,
            "skipped": skipped,
            "errors": errors_count,
            "error_details": error_details,
            "changed_fields": {
                **changed_fields_total,
                "_validation": validate_data or {},
            },
        }).eq("job_id", job_id).execute()

        _reparse_logger.info(
            f"[reparse] job {job_id} 완료: {processed}/{len(targets)} 처리, "
            f"{updated} 수정, {errors_count} 에러"
        )

    except Exception as e:
        _reparse_logger.error(f"[reparse] job {job_id} 실패: {e}")
        try:
            supabase.table("reparse_job_log").update({
                "status": "FAILED",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_details": [{"error": str(e)[:500]}],
            }).eq("job_id", job_id).execute()
        except Exception:
            pass
```

## docstring 추가 (선택)

v1.10.0 위에:

```
v1.11.0 (2026-04-25):
  [FIX] reparse 병렬 처리 — 순차 → 5건 동시 (asyncio.gather)
        건당 87초 → 배치당 ~20초 (5배 속도 향상)
  [FIX] sleep(3) → sleep(0.5) (배치 간)
  [ADD] 동일 법령 컨텍스트 캐시 (DB 조회 대폭 감소)
```

## 주의
- `_run_reparse_background` 함수만 교체. 다른 함수 손대지 마세요.
- `safe_update_master`, `call_claude_messages_ai` 등 import는 이미 되어 있음
- 완료 후 main push → Railway 자동 배포
