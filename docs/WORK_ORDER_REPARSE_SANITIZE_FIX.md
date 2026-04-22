# WORK ORDER: reparse sanitize 확장 + AUTO_PARSE 자동화 개선

**작성일:** 2026-04-22  
**대상:** Cursor / Claude Code  
**긴급도:** 🟡 Medium (현재 배포된 fix로 대부분 해결됐으나 잔여 에러 존재)  
**예상 소요:** 40-60분

---

## 🎯 배경 및 진단

### 관찰된 문제
2026-04-21 21:30 KST 시작된 reparse job `8756176e`가 약 44분 동안 131건 처리 후 완전히 멈췄습니다 (좀비 상태로 10+시간 방치). DB에서 확인된 24건의 에러 패턴:

| 에러 유형 | 건수 | 샘플 rule_id |
|---|---|---|
| `updated_by = "system"/"SYSTEM"/"system_import"` → UUID 타입 오류 | **22** | `NFTC-003`, `CONST-IND-003`, `HAZDC-003` |
| `penalty_value = "과태료 최대 500만원"` → numeric 오류 | 1 | `CHEMDC-001-MFG` |
| `penalty_value = "true"` → numeric 오류 | 1 | `ELECBIZRULE-002-MFG` |
| `penalty_value = "charging_business,group_supply_business"` → numeric 오류 | 1 | `LPGACT-049-COMMON` |
| `LABORADD-001` varchar(30) 초과 | 1 | `LABORADD-001` |

### 근본 원인 분석

**UUID 에러 (22건):** ✅ **이미 해결됨 (배포 타이밍 race condition)**
- 커밋 `801728` (2026-04-21 12:12 UTC = 21:12 KST)에서 `sanitize_master_patch()`에 UUID 검증 추가
- 해당 커밋이 main → dev 머지된 시각: **21:24 KST** (Railway 배포 시작)
- reparse job 시작 시각: **21:30 KST** — 배포 완료 전에 시작됨
- 현재 `services/rule_gen_helpers.py`는 이미 올바르게 `"system"`을 UUID로 인정하지 않음. 다음 실행 시 에러 사라짐 예상.

**numeric 에러 (3건) + varchar 에러 (1건):** 🟡 **현재 코드도 미커버**
- `sanitize_master_patch()`의 numeric 검증이 `condition_value`만 커버함
- `penalty_value`, `appointment_count_value`, `inspection_cycle_value` 등 다른 numeric 컬럼 누락
- Sonnet 응답에서 `"과태료 최대 500만원"` 같은 자연어 문자열이 numeric 컬럼으로 들어가면 DB INSERT 실패

---

## 📋 작업 항목

### STEP 0: 테스트부터 작성 (DEV_RULES v2 준수)

**파일:** `tests/test_rule_gen_helpers.py` (기존 파일에 추가)

기존 파일에 `sanitize_master_patch` 테스트가 **0건**이므로, 현 동작 baseline부터 확인한 뒤 확장:

```python
# tests/test_rule_gen_helpers.py 파일 하단에 추가

from services.rule_gen_helpers import sanitize_master_patch


def test_sanitize_master_patch_uuid_removal():
    """updated_by/created_by 컬럼에서 UUID 아닌 값은 제거된다."""
    for bad_value in ["system", "SYSTEM", "system_import", "", "admin", "SYSTEM_USER"]:
        patch = {"updated_by": bad_value, "law_name": "X"}
        sanitize_master_patch(patch)
        assert "updated_by" not in patch, f"sanitize가 '{bad_value}' 제거 실패"

    valid_uuid = "12345678-1234-1234-1234-123456789012"
    patch = {"updated_by": valid_uuid, "created_by": valid_uuid}
    sanitize_master_patch(patch)
    assert patch["updated_by"] == valid_uuid
    assert patch["created_by"] == valid_uuid


def test_sanitize_master_patch_numeric_coercion():
    """condition_value, penalty_value 등 numeric 컬럼은 변환 or 제거."""
    patch = {"condition_value": "50"}
    sanitize_master_patch(patch)
    assert patch["condition_value"] == 50.0

    for bad_value in ["과태료 최대 500만원", "true", "charging_business,group_supply_business"]:
        patch = {"penalty_value": bad_value}
        sanitize_master_patch(patch)
        if "penalty_value" in patch:
            assert isinstance(patch["penalty_value"], (int, float)), \
                f"'{bad_value}' 처리 후 잘못된 타입: {type(patch['penalty_value'])}"


def test_sanitize_master_patch_varchar_truncate():
    long_value = "A" * 50
    patch = {"condition_code": long_value}
    sanitize_master_patch(patch)
    assert len(patch["condition_code"]) == 30


def test_sanitize_master_patch_preserves_valid_fields():
    patch = {
        "law_name": "건축법",
        "law_article": "제12조",
        "obligation_summary": "2년마다 안전점검 실시",
        "condition_code": "floor_count",
    }
    original = dict(patch)
    sanitize_master_patch(patch)
    assert patch == original
```

**검증:** `pytest tests/test_rule_gen_helpers.py -v` → 새 테스트 중 `test_sanitize_master_patch_numeric_coercion`은 **penalty_value 관련 케이스에서 실패**해야 함 (현재 미구현).

---

### STEP 1: `sanitize_master_patch` 확장

**파일:** `services/rule_gen_helpers.py`

```python
# 상수 추가 (파일 상단 _VARCHAR_30_FIELDS 아래)
_NUMERIC_FIELDS = frozenset([
    "condition_value",
    "penalty_value",
    "appointment_count_value",
    "inspection_cycle_value",
    "equipment_condition_value",
])


def _coerce_numeric(value: Any) -> Optional[float]:
    """numeric 컬럼용 안전 변환.

    - "50" → 50.0
    - "50.5" → 50.5
    - "과태료 500만원" → 500 (숫자 추출)
    - "true"/"false"/"charging_business" → None
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            pass
        m = re.search(r"-?\d+(?:\.\d+)?", value)
        if m:
            try:
                return float(m.group())
            except ValueError:
                return None
    return None


def sanitize_master_patch(patch: dict) -> dict:
    """master_building_legal_rules UPDATE 전 타입 안전 검증.
    - updated_by/created_by: UUID 아니면 제거
    - numeric 필드들: 변환 실패 시 제거, 성공 시 float
    - varchar(30) 초과 시 truncate
    """
    for uuid_field in ("updated_by", "created_by"):
        if uuid_field in patch:
            if not _is_valid_uuid(patch[uuid_field]):
                patch.pop(uuid_field)

    for nf in _NUMERIC_FIELDS:
        if nf in patch and patch[nf] is not None:
            coerced = _coerce_numeric(patch[nf])
            if coerced is None:
                patch.pop(nf)
            else:
                patch[nf] = coerced

    for f in _VARCHAR_30_FIELDS:
        if f in patch and patch[f] is not None and len(str(patch[f])) > 30:
            patch[f] = str(patch[f])[:30]

    return patch
```

**참고:**
- `_coerce_numeric` 2차 추출(regex)은 **의도적으로 보수적**. `"과태료 500만원"` → 500 (만원 단위 컨벤션 따름)
- Sonnet이 자연어로 답하는 건 구조적 이슈 → 궁극적으로 prompt 개선(`services/rule_gen_builders.py::_build_reparse_prompt`)이 더 나은 해결책 (별도 작업)

---

### STEP 2: 테스트 보강

```bash
cd tai-api
pytest tests/test_rule_gen_helpers.py -v
```

**기대 결과:** 기존 3개 + 신규 4개 = **7개 모두 PASSED**.

---

### STEP 3: 통합 검증

`services/rule_gen_reparse.py`는 **수정 불필요**. 이미 `sanitize_master_patch(patch)`를 호출함.

```bash
pytest tests/ -v --tb=short
wc -l services/rule_gen_helpers.py        # 150줄 이내여야 함
grep -E "from fastapi|import fastapi" services/rule_gen_helpers.py  # 0 matches
```

---

### STEP 4 (선택): AUTO_PARSE_NEW cron 래퍼 엔드포인트

**목적:** Chrome 탭 기반 auto-parse를 Railway 백그라운드 cron으로 대체.

**파일:** `services/rule_gen_batch.py` (신규) + `routers/law_rule_generator.py` (1줄 추가)

**스키마:** `schemas/rule_gen.py`에 `AutoParseBatchRequest` 추가

```python
class AutoParseBatchRequest(BaseModel):
    secret: str
    max_laws: int = 10
    max_articles_per_law: int = 50
    auto_approve_threshold: int = 80
    sector: Optional[str] = None
```

**서비스:** `services/rule_gen_batch.py`

```python
"""AUTO_PARSE_NEW cron용 배치 처리."""
from typing import Any, Dict, List
import asyncio


async def run_auto_parse_batch(
    supabase, body, *,
    parse_single_law_fn,
    logger,
) -> Dict[str, Any]:
    """미파싱 조문이 있는 법령을 max_laws 개까지 순회 파싱."""
    query = supabase.rpc("get_unparsed_laws", {"limit_count": body.max_laws}).execute()
    target_laws = query.data or []

    if not target_laws:
        return {"status": "no_work", "processed": 0}

    totals = {"parsed": 0, "drafts": 0, "auto_approved": 0, "errors": 0}
    processed_laws: List[dict] = []

    for law in target_laws:
        try:
            result = await parse_single_law_fn(
                law_id=law["law_id"],
                max_articles=body.max_articles_per_law,
                auto_approve_threshold=body.auto_approve_threshold,
            )
            data = result.get("data", {})
            totals["parsed"] += data.get("parsed", 0)
            totals["drafts"] += data.get("drafts_created", 0)
            totals["auto_approved"] += data.get("auto_approved", 0)
            totals["errors"] += len(data.get("errors", []))
            processed_laws.append({"law_id": law["law_id"], "law_name": law["law_name"], **data})
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"[auto-parse-batch] {law['law_id']} 실패: {e}")
            totals["errors"] += 1

    return {"status": "success", "totals": totals, "processed_laws": processed_laws}
```

**Supabase RPC (migration):**

```sql
CREATE OR REPLACE FUNCTION get_unparsed_laws(limit_count int DEFAULT 10)
RETURNS TABLE(law_id uuid, law_name text, remaining bigint, status text)
LANGUAGE sql STABLE
AS $$
  SELECT
    lm.id AS law_id,
    lm.law_name,
    COUNT(la.id) - COUNT(la.ai_parsed_at) AS remaining,
    CASE WHEN COUNT(la.ai_parsed_at) > 0 THEN 'PARTIAL' ELSE 'FRESH' END AS status
  FROM law_master lm
  LEFT JOIN law_version lv ON lv.law_id = lm.id AND lv.is_current = true
  LEFT JOIN law_article la ON la.law_version_id = lv.id
  WHERE lm.is_active = true
  GROUP BY lm.id, lm.law_name
  HAVING COUNT(la.id) > COUNT(la.ai_parsed_at)
  ORDER BY
    CASE WHEN COUNT(la.ai_parsed_at) > 0 THEN 0 ELSE 1 END,
    COUNT(la.id) - COUNT(la.ai_parsed_at) DESC
  LIMIT limit_count;
$$;
```

**라우터 엔드포인트:**

```python
@router.post("/auto-parse-batch")
async def auto_parse_batch(body: AutoParseBatchRequest, request: Request):
    if body.secret != INTERNAL_API_SECRET:
        raise HTTPException(403, "내부 전용 엔드포인트")
    from services.rule_gen_batch import run_auto_parse_batch
    result = await run_auto_parse_batch(
        get_supabase(), body,
        parse_single_law_fn=run_auto_parse_and_approve,
        logger=logger,
    )
    return {"status": "success", **result}
```

**Cron 활성화:** cron_manager에서 `AUTO_PARSE_NEW` 활성화
- 스케줄: 매 4시간 (`0 */4 * * *`)
- 엔드포인트: `POST /law-rule-generator/auto-parse-batch`
- body: `{"secret": "$INTERNAL", "max_laws": 20, "max_articles_per_law": 50}`

---

## ✅ 체크리스트

- [ ] **STEP 0**: 새 테스트 4개 작성 후 numeric 테스트 실패 확인
- [ ] **STEP 1**: `sanitize_master_patch` 확장
- [ ] **STEP 2**: 새 테스트 4개 모두 PASSED
- [ ] 기존 테스트 regression 없음
- [ ] `services/rule_gen_helpers.py` 150줄 이내
- [ ] `from fastapi` import 없음
- [ ] **STEP 4 (선택)**: AUTO_PARSE_NEW cron 래퍼 추가

---

## 🚀 배포 전 검증 커맨드

```bash
git checkout dev
git pull

pytest tests/test_rule_gen_helpers.py -v
wc -l services/rule_gen_helpers.py
grep -c "fastapi" services/rule_gen_helpers.py

git add services/rule_gen_helpers.py tests/test_rule_gen_helpers.py
git commit -m "fix: sanitize_master_patch에 penalty_value 등 numeric 필드 확장

- _NUMERIC_FIELDS frozenset 도입
- _coerce_numeric() 헬퍼 추가
- sanitize 테스트 4개 신설

관련: reparse job 8756176e의 numeric 타입 오류 3건 대응"
git push origin dev
```

---

## 📊 예상 효과

- **UUID 에러 22건 → 0건** (이미 배포된 sanitize가 잡음)
- **numeric 에러 3건 → 0건** (이 작업 완료 시)
- **varchar 에러 1건 → 0건** (이미 커버됨)
- 전체 에러율 **5% → 0.2% 이하** 감소 예상

### STEP 4 완료 시
- Chrome 탭 의존성 제거
- 4시간 주기 cron 자동 재개
- 기획자가 법령 추가 시 자동 파싱 파이프라인 진입

---

## 📎 관련 파일/커밋

- 현재 상태: `services/rule_gen_helpers.py` @ `dev` SHA `60c70086`
- 참고 커밋: `801728` "fix: reparse 58건 버그 수정" (2026-04-21 21:12 KST)
- 실패 job: `reparse_job_log.job_id = '8756176e-e938-4a87-a47a-f33404d1411a'` (FAILED 처리됨)
- 영향 master: 1,402건 active (현재), `source_api='AI_GENERATED'` 329건
