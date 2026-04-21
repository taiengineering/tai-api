from datetime import date, datetime, timezone

from dateutil.relativedelta import relativedelta


CATEGORY_MAP = {
    "MECH": "기계설비",
    "ELEC": "전기설비",
    "FIRE": "소방설비",
    "INDUSTRY": "산업설비",
    "ENV": "환경설비",
    "HAZMAT": "위험물설비",
    "GAS": "가스설비",
    "ENERGY": "에너지설비",
    "UTILITY": "유틸리티",
    "LIFT": "승강기설비",
    "BUILD": "건축부속",
    "SAFETY": "안전설비",
}

DELTA_MAP = {
    "day": lambda v: relativedelta(days=v),
    "week": lambda v: relativedelta(weeks=v),
    "month": lambda v: relativedelta(months=v),
    "quarter": lambda v: relativedelta(months=3 * v),
    "half_year": lambda v: relativedelta(months=6 * v),
    "year": lambda v: relativedelta(years=v),
}

REPEAT_TYPE_MAP = {
    "day": "daily",
    "week": "weekly",
    "month": "monthly",
    "quarter": "quarterly",
    "half_year": "half_yearly",
    "year": "yearly",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_schedules_for_repair(iset: dict, anchor: date, end: date) -> list:
    cycle_unit = (iset.get("cycle_unit") or "year").lower()
    cycle_value = int(iset.get("cycle_value") or 1)
    fn = DELTA_MAP.get(cycle_unit)
    delta = fn(cycle_value) if fn else relativedelta(years=cycle_value)
    repeat_type = REPEAT_TYPE_MAP.get(cycle_unit, "yearly")

    rows, cursor = [], anchor
    while cursor <= end:
        rows.append(
            {
                "factory_id": iset["factory_id"],
                "company_id": iset.get("company_id"),
                "inspection_set_id": iset["id"],
                "planned_date": cursor.isoformat(),
                "start_date": cursor.isoformat(),
                "end_date": cursor.isoformat(),
                "repeat_type": repeat_type,
                "repeat_interval": cycle_value,
                "status_code": "SCHEDULED",
                "source_type": "MANUAL",
                "obligation_type": iset.get("inspection_category") or "GENERAL",
                "summary": iset.get("inspection_set_name") or "",
                "active_yn": True,
            }
        )
        cursor += delta
    return rows


def _enrich_asset_row(row: dict) -> dict:
    mid = row.get("equipment_model_id") or row.get("model_id")
    row["has_model"] = mid is not None
    row["facility_category"] = row.get("equipment_type_code") or ""
    row["rule_count"] = 0
    row["has_inspection"] = bool(row.get("last_inspection_date"))
    row["has_failure"] = False
    return row
