# Cursor 작업지시서 — 건설 법령엔진 버그수정 (legal_engine.py v5.1.0)

> 파일: `routers/legal_engine.py`  
> 목표: 건설 섹터 법령진단 step1 완벽 동작

---

## 수정 1. CONDITION_CODE_TO_CONTEXT_KEY에 contract_amount 추가

아래 딕셔너리에 `"contract_amount"` 매핑 추가:

```python
CONDITION_CODE_TO_CONTEXT_KEY: Dict[str, str] = {
    "employee_count":           "worker_count",
    "building_area":            "total_floor_area",
    "electrical_capacity_kw":   "electric_capacity",
    "electric_capacity":        "electric_capacity",   # ← 추가
    "floor_count":              "floor_count",
    "elevator_count":           "elevator_count",
    "boiler_capacity_kw":       "boiler_capacity_kw",
    "boiler_capacity_th":       "boiler_capacity_th",
    "gas_capacity_kg":          "gas_capacity_kg",
    "gas_capacity_m3":          "gas_capacity_m3",
    "transformer_capacity_kva": "transformer_capacity_kva",
    "annual_energy_toe":        "annual_energy_toe",
    "construction_amount":      "construction_amount",
    "contract_amount":          "construction_amount",  # ← 핵심 버그 수정
    "contractor_count":         "contractor_count",
    "is_hazardous_material":    "is_hazardous_material",
    "is_multi_use":             "is_multi_use",
    "is_factory_registered":    "is_factory_registered",
}
```

---

## 수정 2. _input_to_facility_context CONSTRUCTION 분기 완성

기존 CONSTRUCTION 분기를 아래로 교체:

```python
elif sec == "CONSTRUCTION":
    eok = float(inp.get("contract_amount_eok") or 0)
    amount = eok * 100_000_000.0

    ctx["construction_amount"] = amount
    ctx["contract_amount"]     = amount   # condition_code 직접 매핑

    # 공사 종류 (BUILDING=건축, CIVIL=토목, SPECIALTY=전문)
    site_type = str(inp.get("construction_type") or inp.get("site_type") or "BUILDING").upper()
    ctx["construction_type"] = site_type
    ctx["building_use_code"] = site_type
    ctx["is_building"] = 1 if site_type == "BUILDING" else 0
    ctx["is_civil"]    = 1 if site_type == "CIVIL"    else 0

    # 근로자 수 (하도급 포함)
    direct = int(inp.get("direct_workers") or inp.get("worker_count") or inp.get("employee_count") or 0)
    subcon = int(inp.get("subcon_workers") or 0)
    total  = direct + subcon
    ctx["worker_count"]  = total
    ctx["employee_count"] = total   # condition_code 직접 매핑
    ctx["direct_workers"] = direct
    ctx["subcon_workers"] = subcon

    # 터널·교량 여부
    ctx["has_tunnel_bridge"] = 1 if _truthy(inp.get("has_tunnel_bridge")) else 0
```

---

## 수정 3. diagnose_step1 결과에 construction_summary 추가

`result_data` 딕셔너리 생성 부분 뒤에 아래 코드 추가:

```python
# 건설 전용 선임 판정 요약
if sector_raw == "CONSTRUCTION":
    amount    = facility_ctx.get("construction_amount", 0)
    workers   = facility_ctx.get("worker_count", 0)
    site_type = facility_ctx.get("construction_type", "BUILDING")

    threshold = 15_000_000_000 if site_type != "CIVIL" else 12_000_000_000
    sm_by_amount  = amount  >= threshold
    sm_by_workers = workers >= 50
    sm_required   = sm_by_amount or sm_by_workers

    basis_parts = []
    if sm_by_amount:
        label = "건축" if site_type == "BUILDING" else ("토목" if site_type == "CIVIL" else site_type)
        basis_parts.append(f"{label} 도급금액 {int(amount/100_000_000)}억 ≥ {int(threshold/100_000_000)}억")
    if sm_by_workers:
        basis_parts.append(f"근로자(하도급 포함) {workers}명 ≥ 50명")

    result_data["construction_summary"] = {
        "site_type":              site_type,
        "contract_amount":        amount,
        "contract_amount_eok":    amount / 100_000_000,
        "total_workers":          workers,
        "safety_manager_required": sm_required,
        "safety_manager_basis":   ", ".join(basis_parts) if basis_parts else "선임 의무 없음",
        "key_thresholds_met": {
            "1억_산업안전보건관리비":    amount >= 100_000_000,
            "50억_유해위험방지계획서":  amount >= 5_000_000_000,
            "50억_기초안전보건교육":    amount >= 5_000_000_000,
            "120억_안전관리자_토목":    site_type == "CIVIL"     and amount >= 12_000_000_000,
            "150억_안전관리자_건축":    site_type == "BUILDING"  and amount >= 15_000_000_000,
            "200억_안전보건관리책임자": amount >= 20_000_000_000,
            "1000억_건설안전판정사":    amount >= 100_000_000_000,
        },
    }
```

---

## 수정 4. ENGINE_VERSION 업데이트

```python
ENGINE_VERSION = "5.1.0"
```

변경 내역 주석 상단에 추가:
```python
# v5.1.0: 건설 섹터 법령엔진 완성
#   - CONDITION_CODE_TO_CONTEXT_KEY contract_amount 매핑 추가
#   - CONSTRUCTION context 완성 (site_type, subcon_workers, tunnel)
#   - diagnose/step1 결과에 construction_summary 추가
```

---

## Railway 배포 후 검증 (아래 3가지 시나리오)

```bash
# 시나리오 1: 건축 200억, 80명 → 선임 필요
curl -X POST https://api.taieng.co.kr/legal-engine/diagnose/step1 \
  -H "Content-Type: application/json" \
  -d '{
    "sector": "CONSTRUCTION",
    "input": {
      "contract_amount_eok": 200,
      "construction_type": "BUILDING",
      "worker_count": 50,
      "subcon_workers": 30
    }
  }'
# 기대값:
# construction_summary.safety_manager_required = true
# construction_summary.key_thresholds_met.150억_안전관리자_건축 = true
# applicable_count >= 10

# 시나리오 2: 토목 50억, 20명 → 선임 불필요
curl -X POST https://api.taieng.co.kr/legal-engine/diagnose/step1 \
  -H "Content-Type: application/json" \
  -d '{
    "sector": "CONSTRUCTION",
    "input": {
      "contract_amount_eok": 50,
      "construction_type": "CIVIL",
      "worker_count": 20,
      "subcon_workers": 0
    }
  }'
# 기대값:
# construction_summary.safety_manager_required = false
# construction_summary.key_thresholds_met.1억_산업안전보건관리비 = true
# applicable_count >= 5

# 시나리오 3: 건축 1200억 → 건설안전판정사 선임
curl -X POST https://api.taieng.co.kr/legal-engine/diagnose/step1 \
  -H "Content-Type: application/json" \
  -d '{
    "sector": "CONSTRUCTION",
    "input": {
      "contract_amount_eok": 1200,
      "construction_type": "BUILDING",
      "worker_count": 200,
      "subcon_workers": 100
    }
  }'
# 기대값:
# construction_summary.key_thresholds_met.1000억_건설안전판정사 = true
# applicable_count >= 15
```

배포 완료 후 알려주세요.
