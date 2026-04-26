# v1.6.0 Cursor 작업지시서 — POST /precedents/save 추가

## 목적
Mac에서 수집한 판례를 Railway DB에 저장하는 endpoint.
prec_seq 기준 upsert (중복 방지).

## 대상 파일
`routers/precedent_api.py`

## 추가 위치
`search_precedents` 함수 위 (기존 endpoint 위)에 다음 코드 추가:

```python
# ── POST /precedents/save ───────────────────────────────────────

@router.post("/save")
async def save_precedent(body: dict):
    """Mac 수집 스크립트에서 호출. prec_seq 기준 upsert."""
    secret = body.get("secret", "")
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용")

    prec = body.get("precedent", {})
    if not prec.get("prec_seq"):
        raise HTTPException(status_code=400, detail="prec_seq 필수")
    if not prec.get("case_number"):
        raise HTTPException(status_code=400, detail="case_number 필수")

    sb = get_supabase()

    # 중복 체크
    existing = sb.table("industrial_accident_precedents").select(
        "id"
    ).eq("prec_seq", prec["prec_seq"]).execute()

    if existing.data:
        # UPDATE (상세 보강)
        sb.table("industrial_accident_precedents").update({
            k: v for k, v in prec.items()
            if v is not None and k != "prec_seq"
        }).eq("prec_seq", prec["prec_seq"]).execute()
        return {"status": "success", "action": "updated", "prec_seq": prec["prec_seq"]}
    else:
        # INSERT
        sb.table("industrial_accident_precedents").insert(prec).execute()
        return {"status": "success", "action": "inserted", "prec_seq": prec["prec_seq"]}
```

## docstring 추가

파일 상단 v1.5.0 위에:
```
v1.6.0 (2026-04-26):
  [ADD] POST /precedents/save — Mac 수집 스크립트에서 판례 저장
        prec_seq 기준 upsert (중복 방지)
```

## 주의
- INTERNAL_SECRET은 이미 파일 상단에 정의되어 있음
- 기존 endpoint 수정 없음
- 완료 후 main push → Railway 자동 배포
