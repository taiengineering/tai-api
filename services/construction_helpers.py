from typing import Any, Dict


# factories.construction_type CHECK 제약: '건축' | '토목' | '공통' | '기타'
CONSTRUCTION_TYPE_MAP: Dict[str, str] = {
    "BUILDING": "건축",
    "CIVIL": "토목",
    "SPECIALTY": "공통",
}


def map_site_type_to_construction_type(site_type: str) -> str:
    return CONSTRUCTION_TYPE_MAP.get((site_type or "").upper(), "건축")


def calc_safety_manager(site_type: str, contract_amount: float, total_workers: int) -> Dict[str, Any]:
    required = False
    count = 0
    reasons = []

    if site_type == "BUILDING" and contract_amount >= 150:
        required = True
        count = max(1, int(contract_amount // 150))
        reasons.append(f"건축 도급금액 {contract_amount}억 ≥ 150억 (시행령 제16조①1호가목)")
    elif site_type == "CIVIL" and contract_amount >= 120:
        required = True
        count = max(1, int(contract_amount // 120))
        reasons.append(f"토목 도급금액 {contract_amount}억 ≥ 120억 (시행령 제16조①1호나목)")

    if total_workers >= 50:
        required = True
        count = max(count, 1)
        reasons.append(f"상시 근로자(하도급 포함) {total_workers}명 ≥ 50명 (시행령 제16조③)")

    return {
        "required": required,
        "count": count,
        "reasons": reasons,
        "site_type": site_type,
        "contract_amount": contract_amount,
        "total_workers": total_workers,
    }
