# 법령 백엔드 작업 지시서 — 2026-03-30
## 담당: Claude Code

---

## STEP 1. 항 파싱 0개 법령 12개 재수집

```bash
for law in \
  "근로기준법" "소방기본법" "소방시설공사업법" \
  "소음·진동관리법" "수도법" "악취방지법" \
  "의료기기법" "주차장법" "토양환경보전법" \
  "하수도법" "환경기술 및 환경산업 지원법" \
  "장애인·노인·임산부 등의 편의증진 보장에 관한 법률"
do
  encoded=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$law'))")
  echo "재수집: $law"
  curl -s -X POST "https://api.taieng.co.kr/law-collector/collect/$encoded" | python3 -m json.tool
  sleep 3
done
```

재수집 후 확인:
```sql
SELECT lm.law_name, COUNT(la.id) as 조문수, COUNT(lp.id) as 항수
FROM law_master lm
JOIN law_version lv ON lv.law_id = lm.id AND lv.is_current = true
JOIN law_article la ON la.law_version_id = lv.id
LEFT JOIN law_paragraph lp ON lp.article_id = la.id
WHERE lm.law_name IN (
  '근로기준법','소방기본법','소방시설공사업법','소음·진동관리법',
  '수도법','악취방지법','의료기기법','주차장법',
  '토양환경보전법','하수도법','환경기술 및 환경산업 지원법',
  '장애인·노인·임산부 등의 편의증진 보장에 관한 법률'
)
GROUP BY lm.law_name
ORDER BY 항수 ASC;
```
목표: 12개 모두 항수 > 0

---

## STEP 2. 별표 데이터 import API 생성

파일: `routers/byulpyo.py`

```python
# routers/byulpyo.py — 별표 데이터 일괄 적재 API
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from db.database import get_supabase
from datetime import datetime

router = APIRouter(prefix="/byulpyo", tags=["별표 데이터"])

# ── 안전인증·자율안전확인 ──────────────────────────────
class SafetyCertItem(BaseModel):
    cert_code: str
    category: str
    item_name: str
    item_name_detail: Optional[str] = None
    legal_basis: Optional[str] = None
    cert_type: str = "CERT"
    inspection_cycle: Optional[str] = None
    issuing_agency: Optional[str] = "한국산업안전보건공단"
    notes: Optional[str] = None

@router.post("/safety-cert/import")
def import_safety_cert(items: List[SafetyCertItem]):
    sb = get_supabase()
    data = [i.dict() for i in items]
    res = sb.table("master_safety_certification").upsert(data, on_conflict="cert_code").execute()
    return {"status": "success", "count": len(res.data)}

@router.get("/safety-cert")
def list_safety_cert(cert_type: str = None):
    sb = get_supabase()
    q = sb.table("master_safety_certification").select("*").eq("is_active", True)
    if cert_type:
        q = q.eq("cert_type", cert_type)
    res = q.order("cert_code").execute()
    return {"status": "success", "data": res.data}

# ── 위험물 품명·지정수량 ──────────────────────────────
class DangerousGoodsItem(BaseModel):
    goods_code: str
    hazard_class: int
    hazard_class_name: str
    item_name: str
    designated_qty: Optional[float] = None
    designated_unit: Optional[str] = None
    storage_standard: Optional[str] = None
    legal_basis: Optional[str] = "위험물안전관리법 시행령 별표 1"
    notes: Optional[str] = None

@router.post("/dangerous-goods/import")
def import_dangerous_goods(items: List[DangerousGoodsItem]):
    sb = get_supabase()
    data = [i.dict() for i in items]
    res = sb.table("master_dangerous_goods").upsert(data, on_conflict="goods_code").execute()
    return {"status": "success", "count": len(res.data)}

@router.get("/dangerous-goods")
def list_dangerous_goods(hazard_class: int = None):
    sb = get_supabase()
    q = sb.table("master_dangerous_goods").select("*").eq("is_active", True)
    if hazard_class:
        q = q.eq("hazard_class", hazard_class)
    res = q.order("goods_code").execute()
    return {"status": "success", "data": res.data}

# ── 안전관리자·보건관리자 선임 기준 ──────────────────────
class SafetyManagerCriteriaItem(BaseModel):
    criteria_code: str
    manager_type: str
    industry_category: str
    ksic_codes: Optional[str] = None
    min_workers: Optional[int] = None
    max_workers: Optional[int] = None
    required_count: int = 1
    qualification: Optional[str] = None
    legal_basis: Optional[str] = None
    notes: Optional[str] = None

@router.post("/safety-manager/import")
def import_safety_manager(items: List[SafetyManagerCriteriaItem]):
    sb = get_supabase()
    data = [i.dict() for i in items]
    res = sb.table("master_safety_manager_criteria").upsert(data, on_conflict="criteria_code").execute()
    return {"status": "success", "count": len(res.data)}

@router.get("/safety-manager")
def list_safety_manager(manager_type: str = None):
    sb = get_supabase()
    q = sb.table("master_safety_manager_criteria").select("*").eq("is_active", True)
    if manager_type:
        q = q.eq("manager_type", manager_type)
    res = q.order("criteria_code").execute()
    return {"status": "success", "data": res.data}

# ── 법정 안전검사 대상·주기 ──────────────────────────────
class LegalInspectionItem(BaseModel):
    target_code: str
    equipment_name: str
    equipment_std: Optional[str] = None
    inspection_type: Optional[str] = None
    cycle_value: Optional[int] = None
    cycle_unit: Optional[str] = None
    cycle_desc: Optional[str] = None
    issuing_agency: Optional[str] = "한국산업안전보건공단"
    legal_basis: Optional[str] = "산업안전보건법 제93조"
    penalty_summary: Optional[str] = None
    notes: Optional[str] = None

@router.post("/legal-inspection/import")
def import_legal_inspection(items: List[LegalInspectionItem]):
    sb = get_supabase()
    data = [i.dict() for i in items]
    res = sb.table("master_legal_inspection_target").upsert(data, on_conflict="target_code").execute()
    return {"status": "success", "count": len(res.data)}

@router.get("/legal-inspection")
def list_legal_inspection():
    sb = get_supabase()
    res = sb.table("master_legal_inspection_target").select("*").eq("is_active", True).order("target_code").execute()
    return {"status": "success", "data": res.data}

# ── 고압가스 ──────────────────────────────────────────
class HighpressureGasItem(BaseModel):
    gas_code: str
    gas_name: str
    gas_type: Optional[str] = None
    processing_limit: Optional[float] = None
    processing_unit: Optional[str] = None
    storage_limit: Optional[float] = None
    storage_unit: Optional[str] = None
    manager_required: bool = False
    legal_basis: Optional[str] = "고압가스 안전관리법 시행령"
    notes: Optional[str] = None

@router.post("/highpressure-gas/import")
def import_highpressure_gas(items: List[HighpressureGasItem]):
    sb = get_supabase()
    data = [i.dict() for i in items]
    res = sb.table("master_highpressure_gas").upsert(data, on_conflict="gas_code").execute()
    return {"status": "success", "count": len(res.data)}

@router.get("/byulpyo/stats")
def byulpyo_stats():
    sb = get_supabase()
    return {
        "status": "success",
        "data": {
            "safety_cert":      sb.table("master_safety_certification").select("id", count="exact").eq("cert_type","CERT").execute().count,
            "self_cert":        sb.table("master_safety_certification").select("id", count="exact").eq("cert_type","SELF").execute().count,
            "dangerous_goods":  sb.table("master_dangerous_goods").select("id", count="exact").execute().count,
            "safety_manager":   sb.table("master_safety_manager_criteria").select("id", count="exact").execute().count,
            "legal_inspection": sb.table("master_legal_inspection_target").select("id", count="exact").execute().count,
            "highpressure_gas": sb.table("master_highpressure_gas").select("id", count="exact").execute().count,
        }
    }
```

main.py에 추가:
```python
from routers.byulpyo import router as byulpyo_router
app.include_router(byulpyo_router)
```

---

## STEP 3. obligation_summary 공백 룰 표준 문구 채우기

```sql
-- APPOINT 룰 summary 채우기
UPDATE master_building_legal_rules
SET obligation_summary = CONCAT(
  COALESCE(appointment_target, '관리자'), ' 선임 의무 (',
  law_name, ' ', COALESCE(law_article, ''), ')'
)
WHERE is_active = true
  AND obligation_type = 'APPOINT'
  AND (obligation_summary IS NULL OR obligation_summary = '');

-- REPORT 룰 summary 채우기
UPDATE master_building_legal_rules
SET obligation_summary = CONCAT(
  COALESCE(rule_name, '신고'), ' 신고 의무 (',
  law_name, ' ', COALESCE(law_article, ''), ')'
)
WHERE is_active = true
  AND obligation_type = 'REPORT'
  AND (obligation_summary IS NULL OR obligation_summary = '');

-- NOTIFY 룰 summary 채우기
UPDATE master_building_legal_rules
SET obligation_summary = CONCAT(
  COALESCE(rule_name, '보고'), ' 보고 의무 (',
  law_name, ' ', COALESCE(law_article, ''), ')'
)
WHERE is_active = true
  AND obligation_type = 'NOTIFY'
  AND (obligation_summary IS NULL OR obligation_summary = '');
```

---

## STEP 4. 최종 무결성 검증

```sql
SELECT 
  (SELECT COUNT(*) FROM law_master WHERE law_type_code IN ('LAW','ENFORCEMENT_DECREE','ENFORCEMENT_RULE')) as 전체법령,
  (SELECT COUNT(*) FROM law_article) as 조문,
  (SELECT COUNT(*) FROM law_paragraph) as 항,
  (SELECT COUNT(*) FROM master_building_legal_rules WHERE is_active=true) as 판정룰,
  (SELECT COUNT(*) FROM master_building_legal_rules r
   LEFT JOIN law_master lm ON lm.law_name=r.law_name
   WHERE r.is_active=true AND lm.id IS NULL) as 미매핑룰,
  (SELECT COUNT(*) FROM master_safety_certification WHERE cert_type='CERT') as 안전인증,
  (SELECT COUNT(*) FROM master_safety_certification WHERE cert_type='SELF') as 자율안전확인,
  (SELECT COUNT(*) FROM master_dangerous_goods) as 위험물,
  (SELECT COUNT(*) FROM master_safety_manager_criteria) as 선임기준,
  (SELECT COUNT(*) FROM master_legal_inspection_target) as 법정검사;
```

## 완료 기준
- [ ] 항 파싱 0개 법령 0개
- [ ] byulpyo.py 라우터 배포
- [ ] /byulpyo/stats API 정상 응답
- [ ] obligation_summary 공백 0개
