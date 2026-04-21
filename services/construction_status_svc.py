def build_ptw_update_payload(body, now_iso_fn):
    allowed = {"APPROVED", "REJECTED", "CLOSED"}
    if body.ptw_status not in allowed:
        raise ValueError(f"ptw_status는 {allowed} 중 하나여야 합니다.")
    data = {"ptw_status": body.ptw_status, "updated_at": now_iso_fn()}
    if body.ptw_status == "APPROVED":
        data["ptw_approved_by"] = body.ptw_approved_by
        data["ptw_approved_at"] = now_iso_fn()
    return data


def build_entry_update_payload(body, now_iso_fn):
    allowed = {"IN", "OUT", "OFFSITE"}
    if body.entry_status not in allowed:
        raise ValueError(f"entry_status는 {allowed} 중 하나여야 합니다.")
    data = {"entry_status": body.entry_status, "updated_at": now_iso_fn()}
    if body.entry_status == "IN":
        data["last_entry_at"] = now_iso_fn()
    return data


def build_corrective_update_payload(body, now_iso_fn):
    allowed = {"IN_PROGRESS", "DONE"}
    if body.corrective_status not in allowed:
        raise ValueError(f"corrective_status는 {allowed} 중 하나여야 합니다.")
    data = {"corrective_status": body.corrective_status, "updated_at": now_iso_fn()}
    if body.corrective_action:
        data["corrective_action"] = body.corrective_action
    return data
