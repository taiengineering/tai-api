# v1.9.0 Cursor 작업지시서 — law_rule_generator.py 3건 수정

## 목적
1. CLAUDE_MODEL Sonnet 전환
2. reparse UPDATE 실패 시 필드별 개별 저장 (채울 수 있는 건 채움)
3. import 추가

## 대상 파일
`routers/law_rule_generator.py` (55KB, 수정 3곳만)

## 변경 1 — import 추가

`from services.rule_gen_svc import _auto_approve_to_master` 줄 다음에 추가:

```python
from services.safe_db_update import safe_update_master
```

## 변경 2 — CLAUDE_MODEL Sonnet 전환

기존:
```python
CLAUDE_MODEL      = "claude-haiku-4-5-20251001"
```

변경:
```python
CLAUDE_MODEL      = "claude-sonnet-4-20250514"
```

## 변경 3 — reparse 필드별 개별 저장

`_run_reparse_background` 함수 안에서 이 블록을 찾으세요:

기존:
```python
                if patch:
                    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
                    supabase.table("master_building_legal_rules").update(patch).eq("id", row["id"]).execute()
                    updated += 1
                else:
                    skipped += 1
```

변경:
```python
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
```

## docstring v1.9.0 추가 (선택)

파일 상단 docstring의 `v1.8.0` 위에 추가:

```
v1.9.0 (2026-04-25):
  [FIX] CLAUDE_MODEL Haiku → Sonnet 전환 (향후 신규 파싱도 Sonnet)
  [FIX] reparse UPDATE 실패 시 필드별 개별 저장
        기존: 1개 필드 타입 에러 → 30개 필드 전부 버려짐
        변경: 29개 저장, 1개만 skip
  [ADD] services/safe_db_update.py — safe_update_master 헬퍼
```

## 서비스 레이어 규칙
- 20KB+ 라우터 수정 시 Router/Service/Schema/Tests 분리 필요 (docs/DEV_RULES_SERVICE_LAYER.md)
- 이번 변경은 3곳 최소 변경이므로 예외 적용
- 완료 후 main push → Railway 자동 배포

## 테스트
배포 후 `/health` 200 확인 → reparse curl 재실행
