# v1.10.0 Cursor 작업지시서 — POST /reparse-all 추가

## 목적
빈칸 보강을 curl 1번으로 전체 자동 처리. limit 없이 모든 빈칸 룰을 순차 처리하고, 이미 채워진 룰은 건너뜀.

## 대상 파일
`routers/law_rule_generator.py`

## 변경 1곳만 — 새 endpoint 추가

`auto_parse_all_endpoint` 함수 바로 아래 (reparse-master 섹션 위)에 다음 코드를 추가:

```python
# ── v1.10.0: POST /reparse-all (빈칸 전체 자동 보강) ─────────────────────────

_CRITICAL_FIELDS = [
    "penalty_summary", "condition_code", "condition_value",
    "condition_operator_code", "remarks", "submit_org_code",
    "form_code", "form_name", "tai_feature_code",
]


def _has_empty_critical(row: dict) -> bool:
    """보강이 필요한 룰인지 판별 (critical 필드 중 하나라도 빈칸이면 True)."""
    for f in _CRITICAL_FIELDS:
        v = row.get(f)
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return True
    return False


async def _run_reparse_all_background(job_id: str):
    """빈칸이 있는 모든 master 룰을 Sonnet으로 보강 (백그라운드)."""
    supabase = get_supabase()

    try:
        # 1. 빈칸 있는 활성 룰 전체 조회
        all_rows = []
        sectors = ["COMMON", "BUILDING", "MANUFACTURING", "CONSTRUCTION"]
        for sec in sectors:
            res = supabase.table("master_building_legal_rules").select("*").eq(
                "is_active", True).eq("sector", sec).execute()
            all_rows.extend(res.data or [])

        targets = [r for r in all_rows if _has_empty_critical(r)]
        # 작은 빈칸 수부터 처리 (빠른 성과)
        targets.sort(key=lambda r: sum(
            1 for f in _CRITICAL_FIELDS
            if r.get(f) is None or (isinstance(r.get(f), str) and r.get(f).strip() == "")
        ))

        supabase.table("reparse_job_log").update({
            "total_targeted": len(targets),
        }).eq("job_id", job_id).execute()

        _reparse_logger.info(
            f"[reparse-all] job {job_id} 시작: {len(targets)}/{len(all_rows)} 룰 보강 대상")

        processed = 0
        updated = 0
        skipped = 0
        errors_count = 0
        error_details: List[dict] = []
        changed_fields_total: Dict[str, int] = {}

        for row in targets:
            rid = row.get("rule_id") or ""
            law_name = row.get("law_name") or ""
            law_article = row.get("law_article") or ""

            if not law_name or not law_article:
                skipped += 1
                processed += 1
                if processed % 20 == 0:
                    supabase.table("reparse_job_log").update({
                        "processed": processed, "updated": updated,
                        "skipped": skipped, "errors": errors_count,
                    }).eq("job_id", job_id).execute()
                await asyncio.sleep(1)
                continue

            try:
                full_context = await build_full_context(law_name, law_article)
                few_shots = await _fetch_few_shot_examples(supabase, law_name, limit=3)
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
                    skipped += 1
                    processed += 1
                    await asyncio.sleep(2)
                    continue

                # fill_empty_only 로직
                patch: Dict[str, Any] = {}
                for key, value in parsed.items():
                    if key not in row:
                        continue
                    if not _is_blank(row.get(key)):
                        continue
                    if _is_blank(value):
                        continue
                    if row.get(key) != value:
                        patch[key] = value
                        changed_fields_total[key] = changed_fields_total.get(key, 0) + 1

                if "submit_org_code" in patch:
                    patch["submit_org_code"] = _normalize_submit_org_code(patch["submit_org_code"])
                    if not patch["submit_org_code"]:
                        patch.pop("submit_org_code", None)

                if patch:
                    any_saved, s_count, f_count = safe_update_master(
                        supabase, row["id"], patch, rule_id=rid)
                    if any_saved:
                        updated += 1
                    else:
                        skipped += 1
                    if f_count > 0:
                        error_details.append({
                            "rule_id": rid,
                            "error": f"partial: {s_count} saved, {f_count} type errors skipped"
                        })
                else:
                    skipped += 1

                processed += 1

            except Exception as e:
                errors_count += 1
                processed += 1
                error_details.append({"rule_id": rid, "error": str(e)[:200]})
                _reparse_logger.warning(f"[reparse-all] {rid} 에러: {e}")

            # 20건마다 진행률 업데이트
            if processed % 20 == 0:
                supabase.table("reparse_job_log").update({
                    "processed": processed,
                    "updated": updated,
                    "skipped": skipped,
                    "errors": errors_count,
                    "error_details": error_details[-20:],
                    "changed_fields": {
                        **changed_fields_total,
                        "_progress": f"{processed}/{len(targets)}",
                    },
                }).eq("job_id", job_id).execute()

            await asyncio.sleep(2)

        # 완료
        supabase.table("reparse_job_log").update({
            "status": "COMPLETED",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "processed": processed,
            "updated": updated,
            "skipped": skipped,
            "errors": errors_count,
            "error_details": error_details,
            "changed_fields": changed_fields_total,
        }).eq("job_id", job_id).execute()

        _reparse_logger.info(
            f"[reparse-all] job {job_id} 완료: {processed}/{len(targets)} 처리, "
            f"{updated} 수정, {errors_count} 에러")

    except Exception as e:
        _reparse_logger.error(f"[reparse-all] job {job_id} 실패: {e}")
        try:
            supabase.table("reparse_job_log").update({
                "status": "FAILED",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_details": [{"error": str(e)[:500]}],
            }).eq("job_id", job_id).execute()
        except Exception:
            pass


@router.post("/reparse-all")
async def reparse_all_endpoint(body: dict, background_tasks: BackgroundTasks):
    """빈칸이 있는 모든 master 룰을 Sonnet으로 일괄 보강 (백그라운드).
    이미 채워진 필드는 건드리지 않음. curl 1번으로 전체 처리.

    body:
      secret: INTERNAL_API_SECRET (필수)
    """
    secret = body.get("secret", "")
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용 엔드포인트")

    job_id = str(uuid.uuid4())

    supabase = get_supabase()
    supabase.table("reparse_job_log").insert({
        "job_id": job_id,
        "sector": "REPARSE_ALL",
        "status": "RUNNING",
    }).execute()

    background_tasks.add_task(_run_reparse_all_background, job_id)

    return {
        "status": "accepted",
        "job_id": job_id,
        "message": "빈칸 전체 보강 작업이 시작됐습니다. 이미 채워진 필드는 건너뜁니다.",
        "check_status": f"/law-rule-generator/reparse-master/status/{job_id}",
    }
```

## docstring 추가 (선택)

파일 상단 docstring의 `v1.9.0` 위에 추가:

```
v1.10.0 (2026-04-25):
  [ADD] POST /reparse-all — 빈칸 전체 자동 보강 (limit 없음)
        이미 채워진 필드 건너뜀, 타입 에러 시 필드별 개별 저장
        curl 1번으로 모든 빈칸 보강 완료
```

## 주의
- 기존 코드 수정 없음 — 새 함수/endpoint 추가만
- `safe_update_master`는 이미 import 되어 있음 (v1.9.0)
- `_reparse_logger`, `_is_blank`, `_normalize_submit_org_code` 등은 이미 파일에 있음
- 서비스 레이어 규칙: 신규 추가만이므로 분리 예외 적용
- 완료 후 main push → Railway 자동 배포
