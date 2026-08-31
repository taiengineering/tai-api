"""
routers/diagnosis_proposal.py — v2.1.0
기안 PDF — 품의서 첨부용 분석보고서 (v6 콘텐츠 + Storage 캐싱 + Gotenberg Chromium)

v2.1.0 (2026-04-19): Gotenberg Chromium PDF 엔진 적용 (xhtml2pdf 제거)
v2.0.0 (2026-04-19): v6 콘텐츠 개편, Storage 캐싱, penalty_sum/paid_tiers 신규
v1.0.3 (2026-04-18): xhtml2pdf 한글 폰트(NanumGothic) @font-face 주입
v1.0.2 (2026-04-18): str 타입 규칙 항목 처리 (AttributeError 수정)
v1.0.1 (2026-04-18): penalty_summary 한국어 텍스트 파싱 (ValueError 수정)
v1.0.0 (2026-04-18): 최초 생성
"""
from __future__ import annotations

import io
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse

from db.supabase_client import get_supabase
from services.legal_rules import normalize_sector_db
from services.time import now_kst, parse_external_datetime, to_external_utc

log = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis", tags=["기안PDF"])

VERSION = "2.1.0"

GOTENBERG_URL = os.getenv("GOTENBERG_URL", "http://tai-gotenberg.internal:3000")

SECTOR_LABEL: Dict[str, str] = {
    "INDUSTRIAL": "산업(제조)",
    "INDUSTRY": "산업(제조)",
    "BUILDING": "건물·시설",
    "CONSTRUCTION": "건설",
    "MANUFACTURING": "산업(제조)",
    "SPECIAL_FACILITY": "건물·시설",
}
SECTOR_NORMALIZE: Dict[str, str] = {
    "MANUFACTURING": "INDUSTRIAL",
    "SPECIAL_FACILITY": "BUILDING",
}



def _now() -> datetime:
    return now_kst()


def _parse_penalty_krw(text: Any) -> float:
    if text is None:
        return 0.0
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        pass
    best = 0.0
    for m in re.finditer(r'([0-9,]+(?:\.[0-9]+)?)\s*\uc5b5\s*\uc6d0?', s):
        v = float(m.group(1).replace(',', ''))
        best = max(best, v * 100_000_000)
    for m in re.finditer(r'([0-9,]+(?:\.[0-9]+)?)\s*\ub9cc\s*\uc6d0?', s):
        v = float(m.group(1).replace(',', ''))
        best = max(best, v * 10_000)
    return best


def _format_penalty(amount: float) -> str:
    if amount <= 0:
        return "\ubc95\ub839 \uae30\uc900"
    if amount >= 100_000_000:
        v = amount / 100_000_000
        return f"{int(v):,}\uc5b5\uc6d0" if v == int(v) else f"{v:.1f}\uc5b5\uc6d0"
    if amount >= 10_000:
        v = amount / 10_000
        return f"{int(v):,}\ub9cc\uc6d0"
    return f"{int(amount):,}\uc6d0"


def _get_penalty_from_rule(r: Any) -> float:
    if not isinstance(r, dict):
        return _parse_penalty_krw(r) if isinstance(r, str) else 0.0
    amt = r.get("penalty_amount")
    if amt is not None:
        parsed = _parse_penalty_krw(amt)
        if parsed > 0:
            return parsed
    return _parse_penalty_krw(r.get("penalty_summary") or r.get("penalty_text") or "")


def _compute_penalty_sum(rules_flat: List[Dict[str, Any]]) -> float:
    """\uc804\uccb4 \uaddc\uce59\uc758 \uacfc\ud0dc\ub8cc\ub97c \ud569\uc0b0. \uc911\ub300\uc7ac\ud574\uccab\ubc8c\ubc95 \ud56d\ubaa9\uc740 \uc81c\uc678."""
    total = 0.0
    for r in rules_flat:
        if not isinstance(r, dict):
            continue
        law_name = str(r.get("law_name") or r.get("law") or "").strip()
        if "\uc911\ub300\uc7ac\ud574" in law_name:
            continue
        total += _get_penalty_from_rule(r)
    return total


def _build_paid_tiers(sector: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    \uc139\ud130\ubcc4 \uc720\ub8cc \ud2f0\uc5b4 \uad6c\uc131 \uc0dd\uc131.
    - INDUSTRY: 3\uac1c \ud2f0\uc5b4 \ub9ac\uc2a4\ud2b8 (\uc0ac\uc6a9\uc790 \uc120\ud0dd\ud615)
    - BUILDING: \uba74\uc801 \uae30\uc900 \uc790\ub3d9 \ud310\uc815 (\ub2e8\uc77c \ud655\uc815 + \uc0c1\uc704 \ud78c\ud2b8)
    - CONSTRUCTION: \uacf5\uc0ac\uae08\uc561 \uae30\uc900 \uc790\ub3d9 \ud310\uc815 (\ub2e8\uc77c \ud655\uc815 + \uc0c1\uc704 \ud78c\ud2b8)
    """
    if sector == "INDUSTRIAL":
        return {
            "mode": "select",
            "tiers": [
                {"badge_class": "basic",    "code": "INDUSTRY_V2",       "name": "\uc81c\uc870\u00b7\uc0b0\uc5c5 \uae30\ubcf8", "price": 79000,  "pages": 20},
                {"badge_class": "standard", "code": "INDUSTRY_STANDARD", "name": "\uc81c\uc870\u00b7\uc0b0\uc5c5 \uc815\ubc00", "price": 149000, "pages": 24},
                {"badge_class": "premium",  "code": "INDUSTRY_PREMIUM",  "name": "\uc81c\uc870\u00b7\uc0b0\uc5c5 \uc885\ud569", "price": 249000, "pages": 28},
            ],
        }

    if sector == "BUILDING":
        try:
            area = float(input_data.get("total_floor_area") or 0)
        except (TypeError, ValueError):
            area = 0.0

        if area < 5000:
            determined = {
                "code": "BUILDING_V2",
                "name": "\uc18c\ud615\uac74\ubb3c (5,000\u33a1 \ubbf8\ub9cc)",
                "price": 99000,
                "pages": 20,
            }
            upper: Optional[Dict[str, Any]] = {
                "name": "\ub300\ud615\uac74\ubb3c \ub4f1\uae09",
                "price": 249000,
                "threshold": "\uc5f0\uba74\uc801 5,000\u33a1 \uc774\uc0c1",
            }
        else:
            determined = {
                "code": "BUILDING_LARGE_V2",
                "name": "\ub300\ud615\uac74\ubb3c (5,000\u33a1 \uc774\uc0c1)",
                "price": 249000,
                "pages": 25,
            }
            upper = None

        return {
            "mode": "determined",
            "determined": determined,
            "upper": upper,
            "basis": f"\uc785\ub825 \uc5f0\uba74\uc801 {int(area):,}\u33a1 \uae30\uc900 \uc790\ub3d9 \ud310\uc815",
        }

    if sector == "CONSTRUCTION":
        try:
            raw_amount = input_data.get("project_amount") or 0
            amount_won = float(raw_amount)
            # 10\uc5b5 \uc774\uc0c1\uc774\uba74 \uc6d0 \ub2e8\uc704, \uc544\ub2c8\uba74 \uc5b5\uc6d0 \ub2e8\uc704\ub85c \uac00\uc815
            amount_eok = amount_won / 100_000_000 if amount_won >= 1_000_000_000 else amount_won
        except (TypeError, ValueError):
            amount_eok = 0.0

        if amount_eok < 50:
            determined = {
                "code": "CONSTRUCTION",
                "name": "\uac74\uc124 \uae30\ubcf8 \ub4f1\uae09 (50\uc5b5\uc6d0 \ubbf8\ub9cc)",
                "price": 145000,
                "pages": 22,
            }
            upper = {
                "name": "\uac74\uc124 \uc885\ud569 \ub4f1\uae09",
                "price": 299000,
                "threshold": "\uacf5\uc0ac\uae08\uc561 50\uc5b5\uc6d0 \uc774\uc0c1",
            }
        else:
            determined = {
                "code": "CONSTRUCTION_PREMIUM",
                "name": "\uac74\uc124 \uc885\ud569 \ub4f1\uae09 (50\uc5b5\uc6d0 \uc774\uc0c1)",
                "price": 299000,
                "pages": 28,
            }
            upper = None

        return {
            "mode": "determined",
            "determined": determined,
            "upper": upper,
            "basis": f"\uc785\ub825 \uacf5\uc0ac\uae08\uc561 {int(amount_eok):,}\uc5b5\uc6d0 \uae30\uc900 \uc790\ub3d9 \ud310\uc815",
        }

    return {"mode": "select", "tiers": []}


def _fetch_row(token: str) -> Dict[str, Any]:
    sb = get_supabase()
    res = sb.table("anonymous_diagnosis_results").select("*").eq("public_token", token).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="\uc9c4\ub2e8 \uacb0\uacfc\ub97c \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.")
    row = res.data[0]
    exp = row.get("expires_at")
    if exp:
        try:
            exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = to_external_utc(parse_external_datetime(exp_dt.isoformat(), source_timezone='UTC')) if exp_dt.tzinfo is None else to_external_utc(exp_dt)
            if _now() > exp_dt:
                raise HTTPException(status_code=410, detail="\ub9cc\ub8cc\ub41c \uc9c4\ub2e8 \uacb0\uacfc\uc785\ub2c8\ub2e4.")
        except HTTPException:
            raise
        except Exception:
            pass
    return row


def _get_top5(full: Dict[str, Any]) -> List[Dict[str, Any]]:
    def _parse_items(items: Optional[list]) -> List[Dict[str, Any]]:
        result = []
        for r in (items or []):
            if not isinstance(r, dict):
                continue
            amt = _get_penalty_from_rule(r)
            penalty_text = (
                r.get("penalty_text") or r.get("penalty_summary") or
                (_format_penalty(amt) if amt > 0 else "-")
            )
            result.append({
                "title": (
                    r.get("rule_name") or r.get("title") or
                    r.get("obligation_summary") or r.get("obligation") or
                    r.get("name") or "\ubc95\uc801 \uc758\ubb34 \uc0ac\ud56d"
                ),
                "law": r.get("law_name") or r.get("law") or r.get("law_short_name") or "-",
                "penalty": penalty_text,
                "amount": amt,
            })
        return result

    candidates: List[Dict[str, Any]] = _parse_items(full.get("rules_table"))
    if not candidates:
        candidates = _parse_items(full.get("key_obligations"))
    if not candidates:
        for key in ("appointment_required", "inspection_required", "action_required", "report_required"):
            candidates.extend(_parse_items(full.get(key)))

    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for c in candidates:
        k = c["title"][:30]
        if k not in seen:
            seen.add(k)
            deduped.append(c)
    deduped.sort(key=lambda x: x["amount"], reverse=True)
    return deduped[:5]


def _build_context(row: Dict[str, Any]) -> Dict[str, Any]:
    input_data = row.get("input_data") or {}
    partial    = row.get("partial_result") or {}
    full       = row.get("full_result") or {}

    raw_sector   = str(input_data.get("sector") or full.get("sector") or partial.get("sector") or "INDUSTRIAL").upper()
    canon        = normalize_sector_db(raw_sector)
    sector       = SECTOR_NORMALIZE.get(canon, canon)
    sector_label = SECTOR_LABEL.get(sector, SECTOR_LABEL.get(canon, "\uc0b0\uc5c5"))

    company_name = input_data.get("company_name") or input_data.get("site_kind") or "\uadc0 \uc0ac\uc5c5\uc7a5"
    report_date  = _now().strftime("%Y\ub144 %m\uc6d4 %d\uc77c")
    workers      = int(input_data.get("workers") or input_data.get("worker_count") or 0)

    summary       = partial.get("summary") or full.get("summary") or {}
    total         = int(summary.get("total") or full.get("applicable_count") or 0)
    appointment   = int(summary.get("appointment") or 0)
    inspection    = int(summary.get("inspection") or 0)
    action        = int(summary.get("action") or 0)
    report_notify = int(summary.get("report") or 0) + int(summary.get("notify") or 0)

    risk_level = str(partial.get("risk_level") or full.get("risk_level") or "MEDIUM").upper()
    law_count  = len(partial.get("law_badges") or full.get("law_badges") or [])

    all_rules_flat: List[Dict[str, Any]] = []
    for key in ("appointment_required", "inspection_required", "action_required", "report_required"):
        items = full.get(key) or []
        all_rules_flat.extend(r for r in items if isinstance(r, dict))
    for key in ("rules_table", "key_obligations"):
        items = full.get(key) or []
        all_rules_flat.extend(r for r in items if isinstance(r, dict))

    # v2.0.0: \uacfc\ud0dc\ub8cc \ud569\uc0b0 (\uc911\ub300\uc7ac\ud574\ubc95 \uc81c\uc678)
    penalty_sum      = _compute_penalty_sum(all_rules_flat)
    penalty_sum_text = _format_penalty(penalty_sum)

    top5            = _get_top5(full)
    csia_applicable = workers >= 50

    # v2.0.0: \uc139\ud130\ubcc4 \uc720\ub8cc \ud2f0\uc5b4
    paid_tiers = _build_paid_tiers(sector, input_data)

    return {
        "company_name":     company_name,
        "report_date":      report_date,
        "sector_label":     sector_label,
        "sector":           sector,
        "risk_level":       risk_level,
        "workers":          workers,
        "report_no":        str(row.get("public_token", ""))[:8].upper(),
        "total":            total,
        "appointment":      appointment,
        "inspection":       inspection,
        "action":           action,
        "report_notify":    report_notify,
        "law_count":        law_count,
        "penalty_sum":      penalty_sum,
        "penalty_sum_text": penalty_sum_text,
        "top5":             top5,
        "csia_applicable":  csia_applicable,
        "paid_tiers":       paid_tiers,
    }


def _render_html(context: Dict[str, Any]) -> str:
    try:
        from jinja2 import Environment, FileSystemLoader
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates",
        )
        env = Environment(loader=FileSystemLoader(templates_dir), autoescape=False)
        template = env.get_template("proposal_pdf.html")
        return template.render(**context)
    except Exception as e:
        log.error(f"[proposal-pdf] \ud15c\ud50c\ub9bf \ub80c\ub354\ub9c1 \uc2e4\ud328: {e}")
        raise HTTPException(status_code=500, detail=f"\ud15c\ud50c\ub9bf \ub80c\ub354\ub9c1 \uc2e4\ud328: {e}")


async def _generate_pdf(html: str) -> bytes:
    """Gotenberg Chromium PDF \uc5d4\uc9c4\uc73c\ub85c HTML \u2192 PDF \ubcc0\ud658."""
    url = f"{GOTENBERG_URL}/forms/chromium/convert/html"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            files={"files": ("index.html", html.encode("utf-8"), "text/html")},
            data={
                "paperWidth": "8.27",
                "paperHeight": "11.69",
                "marginTop": "0",
                "marginBottom": "0",
                "marginLeft": "0",
                "marginRight": "0",
                "printBackground": "true",
                "scale": "1",
            },
        )
    if response.status_code != 200:
        log.error(f"[proposal-pdf] Gotenberg \uc624\ub958: {response.status_code} {response.text[:200]}")
        raise HTTPException(status_code=500, detail=f"PDF \uc0dd\uc131 \uc2e4\ud328: Gotenberg {response.status_code}")
    return response.content


@router.get("/proposal-pdf/{public_token}")
async def get_proposal_pdf(public_token: str):
    """\uae30\uc548\uc6a9 PDF \u2014 \ud488\uc758\uc11c \uccca\ubd80 \uadfc\uac70\uc790\ub8cc (\uacf5\uac1c \uc5d4\ub4dc\ud3ec\uc778\ud2b8, Storage \uce90\uc2f1 \uc801\uc6a9)."""
    row = _fetch_row(public_token)

    # Cache hit check \u2014 \uc774\ubbf8 \uc0dd\uc131\ub41c PDF\uac00 \uc788\uc73c\uba74 \uc989\uc2dc redirect
    cached_url = row.get("proposal_pdf_url")
    if cached_url:
        log.info(f"[proposal-pdf] cache hit: {public_token}")
        return RedirectResponse(url=cached_url, status_code=302)

    # PDF \uc0dd\uc131
    context  = _build_context(row)
    html     = _render_html(context)
    pdf      = await _generate_pdf(html)
    filename = f"TAI_proposal_{context['report_no']}.pdf"

    input_data = row.get("input_data") or {}
    full_result = row.get("full_result") or {}
    diagnosis_id = row.get("id")
    company_id = input_data.get("company_id") or full_result.get("company_id")
    factory_id = full_result.get("factory_id") or input_data.get("factory_id")
    if not company_id and factory_id:
        try:
            sb_lookup = get_supabase()
            fac_res = (
                sb_lookup.table("factories")
                .select("company_id")
                .eq("id", factory_id)
                .limit(1)
                .execute()
            )
            if fac_res.data:
                company_id = fac_res.data[0].get("company_id")
        except Exception:
            pass

    try:
        from services.document_svc import register_generated

        if company_id:
            await register_generated(
                file_bytes=pdf,
                file_name=filename,
                mime_type="application/pdf",
                company_id=company_id,
                category="report",
                generated_by="diagnosis_proposal",
                factory_id=factory_id,
                linked_table="diagnosis_results",
                linked_id=diagnosis_id,
                title=f"법령진단 제안서 {context['report_no']}",
            )
    except Exception as _doc_err:
        log.warning("documents 기록 실패 (PDF는 정상 반환): %s", _doc_err)

    # Storage \uc5c5\ub85c\ub4dc \ud6c4 DB\uc5d0 URL \uae30\ub85d (\uc2e4\ud328 \uc2dc \uc9c1\uc811 \uc2a4\ud2b8\ub9ac\ubc0d fallback)
    try:
        sb           = get_supabase()
        storage_path = f"{public_token}/{filename}"

        sb.storage.from_("proposals").upload(
            path=storage_path,
            file=pdf,
            file_options={
                "content-type": "application/pdf",
                "upsert": "true",
            },
        )
        public_url = sb.storage.from_("proposals").get_public_url(storage_path)

        sb.table("anonymous_diagnosis_results").update({
            "proposal_pdf_url":          public_url,
            "proposal_pdf_generated_at": _now().isoformat(),
        }).eq("public_token", public_token).execute()

        log.info(f"[proposal-pdf] generated+cached: {public_token}")
        return RedirectResponse(url=public_url, status_code=302)

    except Exception as e:
        log.error(f"[proposal-pdf] storage upload failed, streaming fallback: {e}")
        return StreamingResponse(
            io.BytesIO(pdf),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length":      str(len(pdf)),
                "Cache-Control":       "no-store",
            },
        )
