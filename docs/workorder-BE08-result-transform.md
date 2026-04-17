# BE-08: 법령진단 결과 Transform 레이어

> **작성일**: 2026-04-17  
> **대상 레포**: taiengineering/tai-api (백엔드)  
> **🔴 절대 금지**: `routers/legal_engine.py` 수정 금지. 엔진은 v5.6.8 원본 유지.

---

## 배경

BE-06에서 legal_engine.py를 직접 수정하여 스키마 표준화를 시도했으나 엔진 손상 발생.
이번에는 **엔진 출력을 후처리하는 별도 Transform 레이어**로 동일 목표 달성.

엔진(legal_engine.py) → [그대로 출력] → Transform 레이어(신규) → 프론트

---

## 작업 1: `routers/diagnosis_transform.py` 신규 생성

### 역할
- `factory_diagnosis_results.result_data` (JSONB)를 읽어서 프론트용 표준 포맷으로 변환
- 엔진 코드는 건드리지 않음. DB에 저장된 결과를 읽기 전용으로 가공

### API 엔드포인트

```
GET /diagnosis/transform/{diagnosis_id}
```

### 응답 표준 스키마 (v2026.04)

```json
{
  "diagnosis_id": "uuid",
  "factory_id": "uuid",
  "sector": "BUILDING|INDUSTRY|CONSTRUCTION",
  "evaluated_at": "ISO8601",
  "engine_version": "5.6.8",
  
  "headline": {
    "risk_level": "HIGH|MEDIUM|LOW",
    "applicable_count": 95,
    "law_count": 12,
    "summary_text": "12개 법령에서 95건의 의무사항이 발견되었습니다."
  },
  
  "obligations": [
    {
      "category": "appointment|inspection|action|report|notify",
      "category_label": "선임|점검|조치|신고|보고",
      "items": [
        {
          "rule_id": "...",
          "law_name": "산업안전보건법",
          "law_article": "제16조",
          "description": "...",
          "obligation_type": "APPOINT",
          "inspection_cycle": "연 1회",
          "schedule_type": "PERIODIC",
          "executor_type_label": "자격자만",
          "penalty_summary": "과태료 500만원",
          "form_code": "...",
          "form_url": "..."
        }
      ]
    }
  ],
  
  "warnings": [
    {
      "type": "threshold_near",
      "message": "근로자 49명 — 50명 도달 시 중대재해법 적용",
      "severity": "high"
    }
  ],
  
  "exposure": {
    "total_penalty_krw": 26000000,
    "penalty_items": [
      {"law": "산안법 §175", "amount": 5000000, "type": "과태료"}
    ]
  },
  
  "inspection_schedule": {
    "periodic_count": 15,
    "before_work_count": 3,
    "on_demand_count": 5,
    "periodic": [...],
    "before_work": [...]
  },
  
  "roi": {
    "annual_subscription": 948000,
    "total_exposure": 26000000,
    "roi_ratio": 27.4,
    "message": "연 구독료 대비 27.4배 리스크 감소"
  }
}
```

### 구현 로직

```python
# routers/diagnosis_transform.py
from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase

router = APIRouter(prefix="/diagnosis", tags=["진단결과변환"])

def transform_result(raw_result: dict, sector: str) -> dict:
    """엔진 출력(result_data)을 프론트 표준 스키마로 변환"""
    # 1. headline 생성
    summary = raw_result.get("summary", {})
    headline = {
        "risk_level": raw_result.get("risk_level", "LOW"),
        "applicable_count": summary.get("total", 0),
        "law_count": len(raw_result.get("law_badges", [])),
        "summary_text": f"{len(raw_result.get('law_badges', []))}개 법령에서 "
                        f"{summary.get('total', 0)}건의 의무사항이 발견되었습니다."
    }
    
    # 2. obligations 표준화 (엔진 출력 키 매핑)
    obligations = []
    category_map = [
        ("appointment_required", "appointment", "선임"),
        ("inspection_required", "inspection", "점검"),
        ("action_required", "action", "조치"),
        ("report_required", "report", "신고"),
    ]
    for key, cat, label in category_map:
        items = raw_result.get(key, [])
        if items:
            obligations.append({
                "category": cat,
                "category_label": label,
                "items": items  # 이미 format_rule_result_db() 포맷
            })
    
    # 3. warnings 생성 (facility_context 기반)
    warnings = _generate_warnings(raw_result.get("facility_context", {}), sector)
    
    # 4. exposure (penalty 합산)
    exposure = _calc_exposure(raw_result)
    
    # 5. inspection_schedule (이미 엔진 출력에 포함)
    insp = raw_result.get("inspection_schedule_ready", {})
    
    # 6. ROI 계산
    roi = _calc_roi(exposure.get("total_penalty_krw", 0), sector)
    
    return {
        "headline": headline,
        "obligations": obligations,
        "warnings": warnings,
        "exposure": exposure,
        "inspection_schedule": insp,
        "roi": roi,
    }

def _generate_warnings(ctx: dict, sector: str) -> list:
    """시설 컨텍스트에서 경계값 경고 추출"""
    warnings = []
    workers = ctx.get("worker_count", 0)
    thresholds = [
        (50, "중대재해법 적용"),
        (100, "안전보건관리체제 강화"),
        (300, "안전관리자 추가 선임"),
        (500, "안전관리자 전담 전환"),
    ]
    for t, msg in thresholds:
        diff = t - workers
        if 0 < diff <= 5:
            warnings.append({
                "type": "threshold_near",
                "message": f"근로자 {workers}명 — {t}명 도달 시 {msg} ({diff}명 차이)",
                "severity": "high"
            })
    return warnings

def _calc_exposure(result: dict) -> dict:
    """penalty_summary에서 과태료 합산"""
    total = 0
    items = []
    for cat_key in ["appointment_required", "inspection_required", "action_required", "report_required"]:
        for rule in result.get(cat_key, []):
            ps = rule.get("penalty_summary", "")
            # 숫자 추출 시도
            # ... (구현)
    return {"total_penalty_krw": total, "penalty_items": items}

def _calc_roi(exposure: int, sector: str) -> dict:
    """SaaS 구독료 대비 ROI 계산"""
    ANNUAL_MAP = {
        "BUILDING": 59000 * 12,
        "INDUSTRY": 79000 * 12,
        "CONSTRUCTION": 145000 * 12,
    }
    annual = ANNUAL_MAP.get(sector, 79000 * 12)
    ratio = round(exposure / annual, 1) if annual > 0 and exposure > 0 else 0
    return {
        "annual_subscription": annual,
        "total_exposure": exposure,
        "roi_ratio": ratio,
        "message": f"연 구독료 대비 {ratio}배 리스크 감소" if ratio > 0 else ""
    }

@router.get("/transform/{diagnosis_id}")
async def get_transformed_result(diagnosis_id: str):
    supabase = get_supabase()
    res = supabase.table("factory_diagnosis_results").select(
        "id, factory_id, sector, result_data, created_at"
    ).eq("id", diagnosis_id).single().execute()
    if not res.data:
        raise HTTPException(404, "진단 결과 없음")
    
    raw = res.data
    result_data = raw.get("result_data") or {}
    transformed = transform_result(result_data, raw.get("sector", ""))
    
    return {
        "status": "success",
        "data": {
            "diagnosis_id": diagnosis_id,
            "factory_id": raw.get("factory_id"),
            "sector": raw.get("sector"),
            "evaluated_at": raw.get("created_at"),
            "engine_version": result_data.get("engine_version", "5.6.8"),
            **transformed
        }
    }

@router.get("/transform/latest/{factory_id}")
async def get_latest_transformed(factory_id: str):
    supabase = get_supabase()
    res = supabase.table("factory_diagnosis_results").select(
        "id, factory_id, sector, result_data, created_at"
    ).eq("factory_id", factory_id).eq("is_latest", True).order(
        "created_at", desc=True
    ).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "진단 결과 없음")
    
    raw = res.data[0]
    result_data = raw.get("result_data") or {}
    transformed = transform_result(result_data, raw.get("sector", ""))
    
    return {
        "status": "success",
        "data": {
            "diagnosis_id": raw["id"],
            "factory_id": factory_id,
            "sector": raw.get("sector"),
            "evaluated_at": raw.get("created_at"),
            "engine_version": result_data.get("engine_version", "5.6.8"),
            **transformed
        }
    }
```

### main.py 라우터 등록

```python
from routers.diagnosis_transform import router as diagnosis_transform_router
app.include_router(diagnosis_transform_router)
```

---

## 작업 2: DB 스키마 추가 (non-breaking)

### 2-1. `factory_diagnosis_results` 컬럼 추가

```sql
ALTER TABLE factory_diagnosis_results
  ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS refund_at TIMESTAMPTZ DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS refund_reason TEXT DEFAULT NULL;

COMMENT ON COLUMN factory_diagnosis_results.expires_at IS '진단 결과 유효기간 (1년 기본)';
COMMENT ON COLUMN factory_diagnosis_results.refund_at IS '환불 처리 일시';
COMMENT ON COLUMN factory_diagnosis_results.refund_reason IS '환불 사유';
```

### 2-2. `master_building_legal_rules` 컬럼 추가

```sql
ALTER TABLE master_building_legal_rules
  ADD COLUMN IF NOT EXISTS is_retroactive BOOLEAN DEFAULT false;

COMMENT ON COLUMN master_building_legal_rules.is_retroactive IS '소급 적용 여부 (true=기존 건축물에도 적용)';
```

---

## 작업 3: 가격 DB 확정 반영 확인

현재 DB와 docs/PRICING_FINAL.md가 100% 일치하는지 transform 레이어에서 참조하는 가격도 동기화.

| 섹터 | SaaS 최저가 (ROI 계산 기준) |
|---|---|
| BUILDING | 59,000/월 (기본관리) |
| INDUSTRY | 79,000/월 (STARTER) |
| CONSTRUCTION | 145,000/월 (STANDARD) |

---

## 체크리스트

- [ ] `routers/diagnosis_transform.py` 생성
- [ ] `main.py`에 라우터 등록
- [ ] DB: expires_at, refund_at, refund_reason 컬럼 추가
- [ ] DB: is_retroactive 컬럼 추가
- [ ] `GET /diagnosis/transform/{diagnosis_id}` 동작 확인
- [ ] `GET /diagnosis/transform/latest/{factory_id}` 동작 확인
- [ ] `legal_engine.py` SHA 변경 없음 확인

---

## 🔴 금지사항

1. `routers/legal_engine.py` 수정 절대 금지
2. `routers/legal_engine_patch.py` 수정 금지
3. `routers/inspection_set_auto.py` 수정 금지
4. `factory_diagnosis_results.result_data` JSONB 구조 변경 금지 (읽기 전용)
5. `services/legal_engine_v202604.py` 참조 금지 (deprecated stub)
