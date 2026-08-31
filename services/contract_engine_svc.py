from datetime import datetime, timedelta, timezone

from services.contract_ai import generate_contract_sections, revise_with_claude
from services.contract_helpers import _entity_type_label, _expert_type_label
from services.time import now_kst


async def run_generate_contract(supabase, body, now: str, storage_bucket: str, contract_template: str):
    req_res = supabase.table("matching_requests").select("*").eq("id", body.request_id).limit(1).execute()
    if not req_res.data:
        raise LookupError("신청을 찾을 수 없습니다.")
    if req_res.data[0]["status"] != "SELECTED":
        raise ValueError("SELECTED 상태인 신청만 계약서를 생성할 수 있습니다.")

    result_res = supabase.table("matching_results").select("*").eq("id", body.result_id).limit(1).execute()
    if not result_res.data or not result_res.data[0].get("is_selected"):
        raise ValueError("선택된 전문가의 제안서만 계약서 생성 가능합니다.")

    req_data = req_res.data[0]
    result_data = result_res.data[0]
    expert_type = req_data.get("expert_type", "EXPERT")

    supplier_table = {
        "personnel": "safety_personnel",
        "agency": "safety_agencies",
        "repair": "repair_companies",
    }.get(result_data.get("supplier_type", ""), "safety_personnel")
    expert_res = supabase.table(supplier_table).select("*").eq("id", result_data["supplier_id"]).limit(1).execute()
    expert_d = expert_res.data[0] if expert_res.data else {}

    client_info = {}
    if req_data.get("company_id"):
        co = (
            supabase.table("companies")
            .select("name, business_number, representative_name, address")
            .eq("id", req_data["company_id"])
            .limit(1)
            .execute()
        )
        if co.data:
            client_info = co.data[0]

    contract_amount = result_data.get("proposal_amount", 0)
    duration_months = result_data.get("proposal_period", 1)
    tai_fee_rate = 10.0
    tai_fee_amount = round(contract_amount * tai_fee_rate / 100)
    expert_amount = contract_amount - tai_fee_amount

    expert_name = expert_d.get("name") or expert_d.get("agency_name") or expert_d.get("company_name") or ""
    sections = await generate_contract_sections(
        expert_type=expert_type,
        contract_amount=contract_amount,
        duration_months=duration_months,
        client_name=client_info.get("name", ""),
        expert_name=expert_name,
        description=req_data.get("description", ""),
        proposal_note=result_data.get("proposal_note", ""),
    )

    start_dt = now_kst()
    end_dt = start_dt + timedelta(days=duration_months * 30)
    html = contract_template.format(
        contract_id="PENDING",
        contract_title=f"{_expert_type_label(expert_type)} 서비스 계약서",
        generated_date=start_dt.strftime("%Y년 %m월 %d일"),
        client_name=client_info.get("name", "-"),
        client_biz_no=client_info.get("business_number", "-"),
        client_ceo=client_info.get("representative_name", "-"),
        client_address=client_info.get("address", "-"),
        expert_name=expert_name or "-",
        entity_type_label=_entity_type_label(expert_d.get("entity_type", "")),
        expert_biz_info=f"사업자번호: {expert_d.get('biz_number') or expert_d.get('business_no', '-')}",
        service_type_label=_expert_type_label(expert_type),
        article3=sections.get("article3", ""),
        start_date=start_dt.strftime("%Y-%m-%d"),
        end_date=end_dt.strftime("%Y-%m-%d"),
        duration_months=duration_months,
        contract_amount_fmt=f"{contract_amount:,}",
        tai_fee_rate=tai_fee_rate,
        tai_fee_amount_fmt=f"{tai_fee_amount:,}",
        expert_amount_fmt=f"{expert_amount:,}",
        article5=sections.get("article5", ""),
        article6=sections.get("article6", ""),
        article7=sections.get("article7", ""),
        client_signed_info="서명 대기",
        expert_signed_info="서명 대기",
    )

    contract_res = supabase.table("matching_contracts").insert(
        {
            "request_id": body.request_id,
            "result_id": body.result_id,
            "status": "DRAFT",
            "contract_title": f"{_expert_type_label(expert_type)} 서비스 계약서",
            "contract_html": html,
            "contract_version": 1,
            "revision_count": 0,
            "contract_amount": contract_amount,
            "tai_fee_rate": tai_fee_rate,
            "tai_fee_amount": tai_fee_amount,
            "expert_amount": expert_amount,
            "client_user_id": req_data.get("user_id"),
            "expert_user_id": result_data.get("expert_user_id"),
            "generated_at": now,
            "created_at": now,
            "updated_at": now,
        }
    ).execute()
    if not contract_res.data:
        raise RuntimeError("계약서 저장 실패")

    contract_id = contract_res.data[0]["id"]
    html_final = html.replace("PENDING", contract_id[:8].upper())
    storage_path = f"{contract_id}/v1/contract.html"
    try:
        supabase.storage.from_(storage_bucket).upload(
            path=storage_path,
            file=html_final.encode("utf-8"),
            file_options={"content-type": "text/html; charset=utf-8"},
        )
    except Exception:
        pass

    supabase.table("matching_contracts").update(
        {"contract_html": html_final, "contract_pdf_url": storage_path, "updated_at": now}
    ).eq("id", contract_id).execute()

    req_history = req_data.get("status_history") or []
    req_history.append({"status": "CONTRACTING", "at": now, "by": "system", "memo": f"계약서 생성 contract_id={contract_id}"})
    supabase.table("matching_requests").update({"status": "CONTRACTING", "status_history": req_history, "updated_at": now}).eq(
        "id", body.request_id
    ).execute()

    for uid, msg in [
        (req_data.get("user_id"), "계약서 초안이 작성되었습니다. 검토 후 서명해 주세요."),
        (result_data.get("expert_user_id"), "계약서 초안이 작성되었습니다. 내용을 확인해 주세요."),
    ]:
        if uid:
            supabase.table("notifications").insert(
                {"user_id": uid, "title": "계약서 초안 완성", "body": msg, "type": "CONTRACT", "ref_id": contract_id, "is_read": False, "created_at": now}
            ).execute()

    return {"contract_id": contract_id, "status": "DRAFT", "view_url": f"/matching/contracts/{contract_id}/view"}


async def run_revise_contract(supabase, contract_id: str, revision_note: str, uid: str, is_admin: bool, now: str, storage_bucket: str):
    res = supabase.table("matching_contracts").select("*").eq("id", contract_id).limit(1).execute()
    if not res.data:
        raise LookupError("계약서를 찾을 수 없습니다.")
    contract = res.data[0]
    is_party = uid in (contract.get("client_user_id"), contract.get("expert_user_id"))
    if not (is_admin or is_party):
        raise PermissionError("권한이 없습니다.")

    revision_count = (contract.get("revision_count") or 0) + 1
    if revision_count > 3:
        supabase.table("matching_contracts").update({"status": "ADMIN_HOLD", "revision_note": revision_note, "updated_at": now}).eq(
            "id", contract_id
        ).execute()
        return {"contract_id": contract_id, "status": "ADMIN_HOLD", "message": "수정 횟수(3회)를 초과하여 어드민 검토가 필요합니다.", "revision_count": revision_count}

    old_html = contract.get("contract_html", "")
    new_html = await revise_with_claude(old_html, revision_note)
    new_version = (contract.get("contract_version") or 1) + 1
    storage_path = f"{contract_id}/v{new_version}/contract.html"

    try:
        supabase.storage.from_(storage_bucket).upload(
            path=storage_path,
            file=new_html.encode("utf-8"),
            file_options={"content-type": "text/html; charset=utf-8"},
        )
    except Exception:
        pass

    supabase.table("matching_contracts").update(
        {
            "status": "REVISING",
            "contract_html": new_html,
            "contract_pdf_url": storage_path,
            "contract_version": new_version,
            "revision_count": revision_count,
            "revision_note": revision_note,
            "updated_at": now,
        }
    ).eq("id", contract_id).execute()

    notify_uid = contract.get("expert_user_id") if uid == contract.get("client_user_id") else contract.get("client_user_id")
    if notify_uid:
        supabase.table("notifications").insert(
            {
                "user_id": notify_uid,
                "title": "계약서 수정 요청",
                "body": f"상대방이 계약서 수정을 요청했습니다. ({revision_count}/3회)",
                "type": "CONTRACT",
                "ref_id": contract_id,
                "is_read": False,
                "created_at": now,
            }
        ).execute()

    return {"contract_id": contract_id, "status": "REVISING", "contract_version": new_version, "revision_count": revision_count, "remaining": 3 - revision_count}


def run_get_contract_for_view(supabase, contract_id: str, uid: str, is_admin: bool):
    res = (
        supabase.table("matching_contracts")
        .select("id, contract_html, status, client_user_id, expert_user_id, client_signed, expert_signed, revision_count")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise LookupError("계약서를 찾을 수 없습니다.")
    contract = res.data[0]
    is_party = uid in (contract.get("client_user_id"), contract.get("expert_user_id"))
    if not (is_admin or is_party):
        raise PermissionError("접근 권한이 없습니다.")
    return contract, is_party


def run_prepare_sign(supabase, contract_id: str, uid: str, now: str):
    res = (
        supabase.table("matching_contracts")
        .select("id, status, client_user_id, expert_user_id, client_signed, expert_signed")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise LookupError("계약서를 찾을 수 없습니다.")
    contract = res.data[0]
    if uid not in (contract.get("client_user_id"), contract.get("expert_user_id")):
        raise PermissionError("계약 당사자만 서명할 수 있습니다.")
    if contract.get("status") not in ("DRAFT", "REVISING", "REVIEWING"):
        raise ValueError(f"현재 상태({contract['status']})에서는 서명할 수 없습니다.")
    supabase.table("identity_logs").insert(
        {"user_id": uid, "method": "KAKAO", "status": "PENDING", "request_id": contract_id, "created_at": now}
    ).execute()


def run_complete_sign(supabase, contract_id: str, user_id: str, ci: str, now: str):
    contract_res = supabase.table("matching_contracts").select("*").eq("id", contract_id).limit(1).execute()
    if not contract_res.data:
        return {"found": False, "updated": False, "both_signed": False}
    c = contract_res.data[0]
    update_row = {}
    if user_id == c.get("client_user_id"):
        update_row = {"client_signed": True, "client_signed_at": now, "client_sign_ci": ci}
    elif user_id == c.get("expert_user_id"):
        update_row = {"expert_signed": True, "expert_signed_at": now, "expert_sign_ci": ci}
    if not update_row:
        return {"found": True, "updated": False, "both_signed": False}

    supabase.table("matching_contracts").update({**update_row, "updated_at": now}).eq("id", contract_id).execute()
    updated_res = (
        supabase.table("matching_contracts")
        .select("client_signed, expert_signed, request_id")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    if not updated_res.data:
        return {"found": True, "updated": True, "both_signed": False}
    updated = updated_res.data[0]
    both_signed = updated.get("client_signed") and updated.get("expert_signed")

    if both_signed:
        supabase.table("matching_contracts").update({"status": "SIGNED", "updated_at": now}).eq("id", contract_id).execute()
        request_id = updated.get("request_id")
        if request_id:
            req_res = supabase.table("matching_requests").select("status_history").eq("id", request_id).limit(1).execute()
            if req_res.data:
                history = req_res.data[0].get("status_history") or []
                history.append({"status": "CONTRACTED", "at": now, "by": "system", "memo": "양측 서명 완료"})
                supabase.table("matching_requests").update(
                    {"status": "CONTRACTED", "status_history": history, "updated_at": now}
                ).eq("id", request_id).execute()
        for uid, msg in [
            (c.get("client_user_id"), "계약이 성사되었습니다! 계약금 입금 안내를 확인해 주세요."),
            (c.get("expert_user_id"), "계약이 성사되었습니다! 업무 시작을 준비해 주세요."),
        ]:
            if uid:
                supabase.table("notifications").insert(
                    {"user_id": uid, "title": "🎉 계약 성사", "body": msg, "type": "CONTRACT", "ref_id": contract_id, "is_read": False, "created_at": now}
                ).execute()
    return {"found": True, "updated": True, "both_signed": bool(both_signed)}


def run_get_contract_meta(supabase, contract_id: str):
    res = (
        supabase.table("matching_contracts")
        .select(
            "id, status, contract_title, contract_version, revision_count, "
            "contract_amount, tai_fee_rate, tai_fee_amount, expert_amount, "
            "client_signed, client_signed_at, expert_signed, expert_signed_at, "
            "generated_at, updated_at"
        )
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise LookupError("계약서를 찾을 수 없습니다.")
    return res.data[0]
