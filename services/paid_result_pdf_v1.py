"""services/paid_result_pdf_v1.py — Premium PDF export v1

INPUT  = premium_result_v1 public projection only
OUTPUT = HTML str (pure) / PDF bytes (Gotenberg transport)

formatter 이지 판정기가 아니다.
build_paid_result_pdf_html_v1: DB 0 · HTTP 0 · LEG 0 · LLM 0 · datetime 0 · random 0.
generate_paid_result_pdf_v1: Gotenberg HTTP 만.
법령 재판정 0 · 정렬/renumber/dedupe 0 · 원문 trim/정규화 0.
duty.what · legal.evidence fallback 0.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

import httpx

from services.paid_result_excel_v1 import (
    CANONICAL_UNAVAILABLE,
    canonical_source_text,
)

GOTENBERG_URL = os.getenv("GOTENBERG_URL", "http://gotenberg.railway.internal:3000")
GOTENBERG_CONVERT_PATH = "/forms/chromium/convert/html"
GOTENBERG_A4 = {
    "paperWidth": "8.27",
    "paperHeight": "11.69",
    "marginTop": "0",
    "marginBottom": "0",
    "marginLeft": "0",
    "marginRight": "0",
    "printBackground": "true",
    "scale": "1",
}

_FILENAME_SAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')

SECTOR_LABELS: Dict[str, str] = {
    "BUILDING": "건물",
    "INDUSTRY": "산업",
    "MANUFACTURING": "산업(제조)",
    "CONSTRUCTION": "건설",
}
OBLIGATION_TYPE_LABELS: Dict[str, str] = {
    "ACTION": "조치",
    "PROHIBIT": "금지·제한",
    "NOTIFY": "신고·통지",
    "INSPECT": "점검·검사",
}
CONTENT_TYPE_LABELS: Dict[str, str] = {
    "OBLIGATION": "의무",
    "PROHIBITION": "금지",
}
PRESENCE_FACTS = (
    ("has_excavation", "굴착작업"),
    ("has_hazardous_material", "유해물질 취급"),
)
FINDING_LABELS: Dict[str, str] = {
    "F01": "진단 범위",
    "F02": "조문 범위",
    "F03": "최다 수행주체",
    "F04": "법령상 수행주체 구성",
    "F05": "금지·제한사항",
    "F06": "점검·검사 의무",
    "F07": "신고·통지 의무",
    "F08": "최다 연결 법령",
    "F09": "최다 연결 조문",
    "F10": "법적 시점이 명시된 의무",
    "F11": "적용 조건이 명시된 의무",
    "F12": "수신 대상이 명시된 의무",
    "F13": "판정에 사용된 사업장 정보",
    "F14": "추가 확인 항목이 있는 의무",
}
FINDING_TYPES: Dict[str, str] = {
    "F01": "OBLIGATION_LAW_COVERAGE",
    "F02": "LAW_ARTICLE_COVERAGE",
    "F03": "ACTOR_MAX_OBLIGATION_COUNT",
    "F04": "LEGAL_ACTOR_DIVERSITY",
    "F05": "PROHIBITION_OBLIGATION_COUNT",
    "F06": "INSPECTION_OBLIGATION_COUNT",
    "F07": "NOTIFICATION_OBLIGATION_COUNT",
    "F08": "LAW_MAX_OBLIGATION_COUNT",
    "F09": "ARTICLE_MAX_OBLIGATION_COUNT",
    "F10": "LEGAL_TIMING_COVERAGE",
    "F11": "CONDITION_COVERAGE",
    "F12": "RECIPIENT_COVERAGE",
    "F13": "TRIGGER_FACT_PROFILE",
    "F14": "OBLIGATION_INFORMATION_GAP_COUNT",
}
TRIGGER_LABELS: Dict[str, str] = {
    "worker_count": "근로자 수",
    "total_floor_area": "면적",
    "contract_amount_eok": "공사금액",
    "sector": "업종/분야",
    "construction_type": "공사 유형",
    "building_use_type": "건축물 용도",
    "has_excavation": "굴착작업",
    "has_hazardous_material": "유해물질 취급",
}
REPORT_SECTIONS = (
    ("cover", "01", "진단 개요"),
    ("business", "02", "우리 사업장"),
    ("glance", "03", "진단 결과 요약"),
    ("findings", "04", "이번 진단에서 확인된 것"),
    ("landscape", "05", "결과의 관리 구조"),
    ("workbench", "06", "법적 의무"),
    ("legal", "07", "법령·조문"),
    ("confirm", "08", "추가 확인"),
    ("evidence", "09", "법적 근거"),
    ("deliverables", "10", "결과물"),
)
DELIVERABLE_ITEMS = (
    {"key": "web", "label": "Web 진단 결과"},
    {"key": "pdf", "label": "PDF 진단보고서"},
    {"key": "excel", "label": "Excel 법정의무 관리대장"},
    {"key": "legal", "label": "법령·조문 근거"},
)

FACT_LABELS = (
    ("who", "법령상 수행주체"),
    ("recipient", "의무 대상"),
    ("condition", "적용 조건"),
    ("where", "장소"),
    ("how", "방법"),
    ("when", "의무 조문상 시점"),
    ("inspection_cycle", "점검 주기 표기"),
)


class PaidResultPdfTransportError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _dig(src: Any, path: Sequence[str]) -> Any:
    cur = src
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _label_enum(value: Any, table: Dict[str, str]) -> Optional[str]:
    if not isinstance(value, str) or value not in table:
        return None
    return table[value]


def _count_text(n: int) -> str:
    return "{}건".format(n)


def _article_count_text(n: int) -> str:
    return "{}개".format(n)


def result_mode(total_obligation_count: Any) -> str:
    total = total_obligation_count if isinstance(total_obligation_count, int) else 0
    if total <= 1:
        return "SINGLE"
    if total <= 5:
        return "COMPACT"
    return "PORTFOLIO"


def pdf_filename(premium_result: Dict[str, Any]) -> str:
    """stored 값만. 시계/UUID/token 사용 0."""
    company = _dig(premium_result, ("profile", "company_name"))
    diagnosed = _dig(premium_result, ("diagnosis", "diagnosed_at"))
    company_s = str(company).strip() if _present(company) else ""
    diagnosed_s = str(diagnosed).strip() if _present(diagnosed) else ""
    if not company_s:
        return "결과.pdf"
    cname = _FILENAME_SAFE.sub("_", company_s).strip(" ._") or "결과"
    if not diagnosed_s:
        return "TAI_법령진단_{}.pdf".format(cname)
    stamp = _FILENAME_SAFE.sub("_", diagnosed_s).strip(" ._")
    if not stamp:
        return "TAI_법령진단_{}.pdf".format(cname)
    return "TAI_법령진단_{}_{}.pdf".format(cname, stamp)


def pdf_content_disposition(filename: str) -> str:
    ascii_fallback = "TAI_diagnosis.pdf"
    return "attachment; filename=\"{}\"; filename*=UTF-8''{}".format(
        ascii_fallback, quote(filename, safe=""),
    )


def _finding_number(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    return int(value)


def _finding_value(finding_id: str, facts: Dict[str, Any]) -> Optional[str]:
    if finding_id == "F01":
        obligations = _finding_number(facts.get("obligation_count"))
        laws = _finding_number(facts.get("law_count"))
        if obligations is None or laws is None:
            return None
        return "법적 의무 {} · 관련 법령 {}".format(
            _count_text(obligations), _article_count_text(laws),
        )
    if finding_id == "F02":
        laws = _finding_number(facts.get("law_count"))
        articles = _finding_number(facts.get("article_count"))
        if laws is None or articles is None:
            return None
        return "관련 법령 {} · 관련 조문 {}".format(
            _article_count_text(laws), _article_count_text(articles),
        )
    if finding_id == "F03":
        top = _finding_number(facts.get("max_obligation_count"))
        if top is None:
            return None
        names = [
            row.get("actor") for row in _as_list(facts.get("actors"))
            if isinstance(row, dict) and isinstance(row.get("actor"), str) and row.get("actor")
        ]
        if not names:
            return None
        return "{} · {}".format(" · ".join(names), _count_text(top))
    if finding_id == "F04":
        kinds = _finding_number(facts.get("actor_count"))
        return None if kinds is None else "{}종류".format(kinds)
    simple = {
        "F05": "prohibition_count",
        "F06": "inspection_count",
        "F07": "notification_count",
        "F10": "timing_obligation_count",
        "F11": "condition_obligation_count",
        "F12": "recipient_obligation_count",
        "F14": "obligation_gap_count",
    }
    if finding_id in simple:
        n = _finding_number(facts.get(simple[finding_id]))
        return None if n is None else _count_text(n)
    if finding_id == "F08":
        top = _finding_number(facts.get("obligation_count"))
        if top is None:
            return None
        names = [
            row.get("law_name") for row in _as_list(facts.get("laws"))
            if isinstance(row, dict) and _present(row.get("law_name"))
        ]
        if not names:
            return None
        return "{} · {}".format(" · ".join(str(n) for n in names), _count_text(top))
    if finding_id == "F09":
        top = _finding_number(facts.get("obligation_count"))
        if top is None:
            return None
        names = []
        for row in _as_list(facts.get("articles")):
            if not isinstance(row, dict):
                return None
            law_name = row.get("law_name")
            article = row.get("law_article")
            if not _present(law_name) or not _present(article):
                return None
            names.append("{} · {}".format(law_name, article))
        if not names:
            return None
        return "{} · {}".format(" / ".join(names), _count_text(top))
    if finding_id == "F13":
        labels: List[str] = []
        for raw in _as_list(facts.get("triggers")):
            if isinstance(raw, str) and raw in TRIGGER_LABELS:
                label = TRIGGER_LABELS[raw]
                if label not in labels:
                    labels.append(label)
        if not labels:
            return None
        return "{} · {}".format(_article_count_text(len(labels)), " · ".join(labels))
    return None


def _build_findings(premium: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    items: List[Dict[str, str]] = []
    for row in _as_list(_dig(premium, ("materials", "diagnosis_findings", "findings"))):
        if not isinstance(row, dict) or row.get("eligible") is not True:
            continue
        finding_id = row.get("id") or row.get("finding_id")
        if not isinstance(finding_id, str) or finding_id not in FINDING_TYPES:
            continue
        if row.get("type") != FINDING_TYPES[finding_id]:
            continue
        value = _finding_value(finding_id, _as_dict(row.get("facts")))
        if value is None:
            continue
        items.append({"label": FINDING_LABELS[finding_id], "value": value})
    if not items:
        return None
    return {"title": "진단 결과에서 확인된 사항", "rows": items}


def _build_business(profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    rows: List[Dict[str, str]] = []
    company = profile.get("company_name")
    if _present(company):
        rows.append({"label": "사업장명", "value": str(company)})
    sector = _label_enum(profile.get("sector"), SECTOR_LABELS)
    if sector is not None:
        rows.append({"label": "업종/분야", "value": sector})
    workers = profile.get("workers")
    if isinstance(workers, (int, float)) and not isinstance(workers, bool):
        rows.append({"label": "근로자 수", "value": "{}명".format(int(workers) if float(workers).is_integer() else workers)})
    floor_area = profile.get("floor_area")
    if isinstance(floor_area, (int, float)) and not isinstance(floor_area, bool):
        rows.append({"label": "면적", "value": "{}㎡".format(floor_area)})
    amount = profile.get("contract_amount_eok")
    if isinstance(amount, (int, float)) and not isinstance(amount, bool):
        rows.append({"label": "공사금액", "value": "{}억원".format(amount)})
    for key, label in (
        ("construction_type", "공사 유형"),
        ("building_use_type", "건축물 용도"),
        ("address", "주소"),
    ):
        if _present(profile.get(key)):
            rows.append({"label": label, "value": str(profile.get(key))})
    presence = [
        {"label": label, "value": "해당"}
        for field, label in PRESENCE_FACTS
        if profile.get(field) is True
    ]
    if not rows and not presence:
        return None
    return {
        "title": "이번 진단의 사업장 정보",
        "presence_title": "진단에 제공된 사업장 특성",
        "rows": rows,
        "presence": presence,
    }


def _build_workbench(premium: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for ob in _as_list(_dig(premium, ("materials", "obligations"))):
        if not isinstance(ob, dict):
            continue
        legal = _as_dict(ob.get("legal"))
        classification = _as_dict(ob.get("classification"))
        duty = _as_dict(ob.get("duty"))
        timing = _as_dict(ob.get("timing"))
        applicability = _as_dict(ob.get("applicability"))
        facts = []
        values = {
            "who": duty.get("who"),
            "recipient": duty.get("recipient"),
            "condition": applicability.get("condition"),
            "where": duty.get("where"),
            "how": duty.get("how"),
            "when": timing.get("when"),
            "inspection_cycle": timing.get("inspection_cycle"),
        }
        for key, label in FACT_LABELS:
            if _present(values[key]):
                facts.append({"key": key, "label": label, "value": values[key]})
        badges = []
        ctype = _label_enum(classification.get("content_type"), CONTENT_TYPE_LABELS)
        otype = _label_enum(classification.get("obligation_type"), OBLIGATION_TYPE_LABELS)
        if ctype is not None:
            badges.append(ctype)
        if otype is not None:
            badges.append(otype)
        items.append({
            "ref": ob.get("ref"),
            "law_name": legal.get("law_name") if _present(legal.get("law_name")) else None,
            "law_article": legal.get("law_article") if _present(legal.get("law_article")) else None,
            "canonical": canonical_source_text(premium, ob.get("ref")),
            "badges": badges,
            "facts": facts,
        })
    if not items:
        return None
    return {
        "title": "법적 의무 상세",
        "intro": "이번 진단에서 확인된 법적 의무별로 수행주체, 적용 조건과 법적 시점 등 확인 가능한 정보를 정리했습니다.",
        "cards": items,
    }


def _article_heading(article: Dict[str, Any]) -> str:
    bits: List[str] = []
    if _present(article.get("law_name")):
        bits.append(str(article.get("law_name")))
    no = article.get("article_no")
    sub = article.get("article_sub_no")
    if no is not None and no != "":
        if sub is not None and sub != "":
            bits.append("제{}조의{}".format(no, sub))
        else:
            bits.append("제{}조".format(no))
    if _present(article.get("article_title")):
        bits.append(str(article.get("article_title")))
    return " · ".join(bits)


def _build_evidence(premium: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    articles_out: List[Dict[str, Any]] = []
    for article in _as_list(_dig(premium, ("evidence", "articles"))):
        if not isinstance(article, dict):
            continue
        text = article.get("article_text")
        if text is None:
            text = ""
        if not isinstance(text, str):
            text = str(text)
        refs = article.get("related_refs")
        related = list(refs) if isinstance(refs, list) else []
        articles_out.append({
            "heading": _article_heading(article),
            "article_no": article.get("article_no"),
            "article_sub_no": article.get("article_sub_no"),
            "article_text": text,
            "related_refs": related,
            "related_refs_text": ", ".join(str(x) for x in related),
        })
    if not articles_out:
        return None
    return {
        "title": "법적 근거 원문",
        "intro": "이번 진단 결과와 연결된 법령 조문 원문입니다.",
        "articles": articles_out,
    }


def _build_legal(premium: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    portfolio = [
        row for row in _as_list(_dig(premium, ("materials", "law_portfolio")))
        if isinstance(row, dict)
    ]
    bundles = [
        row for row in _as_list(_dig(premium, ("materials", "article_bundles")))
        if isinstance(row, dict)
    ]
    if not portfolio and not bundles:
        return None
    return {"title": "법령·조문 근거", "portfolio": portfolio, "bundles": bundles}


def _build_confirm(premium: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    gaps = _as_dict(_dig(premium, ("materials", "information_gaps")))
    input_gaps = _as_dict(gaps.get("diagnosis_input_gaps"))
    obl_gaps = _as_dict(gaps.get("obligation_information_gaps"))
    rows: List[Dict[str, Any]] = []
    for label, value in (
        ("진단 입력 공백", input_gaps.get("missing_count")),
        ("확인 필요 입력", input_gaps.get("unknown_count")),
        ("형식 확인 필요 입력", input_gaps.get("invalid_count")),
        ("추가 확인이 있는 의무", obl_gaps.get("obligation_count_with_gaps")),
    ):
        if isinstance(value, int) and value > 0:
            rows.append({"label": label, "value": _count_text(value)})
    if not rows:
        return None
    return {"title": "추가 확인 정보", "rows": rows}


def _build_glance(overview: Dict[str, Any], mode: str) -> Optional[Dict[str, Any]]:
    if mode == "SINGLE":
        return None
    stats: List[Dict[str, Any]] = []
    total = overview.get("total_obligation_count")
    laws = overview.get("distinct_law_count")
    if isinstance(total, int):
        stats.append({"label": "적용 법적 의무", "value": _count_text(total)})
    if isinstance(laws, int):
        stats.append({"label": "관련 법령", "value": _article_count_text(laws)})
    type_counts = _as_dict(overview.get("obligation_type_counts"))
    for code, n in type_counts.items():
        if not isinstance(n, int) or n <= 0:
            continue
        label = OBLIGATION_TYPE_LABELS.get(code)
        if label is None:
            continue
        stats.append({"label": label, "value": _count_text(n)})
    if not stats:
        return None
    return {"title": "진단 결과 요약", "stats": stats}


def _build_landscape(premium: Dict[str, Any], mode: str) -> Optional[Dict[str, Any]]:
    if mode == "SINGLE":
        return None
    portfolio = [
        row for row in _as_list(_dig(premium, ("materials", "law_portfolio")))
        if isinstance(row, dict)
    ]
    actors = [
        row for row in _as_list(_dig(premium, ("materials", "legal_actor_map")))
        if isinstance(row, dict)
    ]
    if not portfolio and not actors:
        return None
    return {
        "title": "결과의 관리 구조",
        "portfolio": portfolio,
        "actors": actors,
    }


def _build_cover(premium: Dict[str, Any], overview: Dict[str, Any]) -> Dict[str, Any]:
    stats: List[Dict[str, Any]] = []
    total = overview.get("total_obligation_count")
    laws = overview.get("distinct_law_count")
    if isinstance(total, int):
        stats.append({"label": "적용 법적 의무", "value": _count_text(total)})
    if isinstance(laws, int):
        stats.append({"label": "관련 법령", "value": _article_count_text(laws)})
    bundles = [
        row for row in _as_list(_dig(premium, ("materials", "article_bundles")))
        if isinstance(row, dict) and _present(row.get("law_article"))
        and row.get("law_article") != "UNSPECIFIED"
    ]
    if bundles:
        stats.append({"label": "관련 조문", "value": _article_count_text(len(bundles))})
    company = _dig(premium, ("profile", "company_name"))
    diagnosed = _dig(premium, ("diagnosis", "diagnosed_at"))
    return {
        "title": "유료 법정의무 진단 결과",
        "company_name": str(company) if _present(company) else None,
        "diagnosed_at": str(diagnosed) if _present(diagnosed) else None,
        "stats": stats,
    }


def _build_view(premium: Dict[str, Any]) -> Dict[str, Any]:
    overview = _as_dict(_dig(premium, ("materials", "overview")))
    obligations = [
        ob for ob in _as_list(_dig(premium, ("materials", "obligations")))
        if isinstance(ob, dict)
    ]
    stored_total = overview.get("total_obligation_count")
    total = stored_total if isinstance(stored_total, int) else len(obligations)
    mode = result_mode(total)
    cover = _build_cover(premium, overview)
    business = _build_business(_as_dict(premium.get("profile")))
    glance = _build_glance(overview, mode)
    findings = _build_findings(premium)
    landscape = _build_landscape(premium, mode)
    workbench = _build_workbench(premium)
    legal = _build_legal(premium)
    confirm = _build_confirm(premium)
    evidence = _build_evidence(premium)
    deliverables = {"title": "이번 진단에 포함되는 결과물", "list": list(DELIVERABLE_ITEMS)}
    pieces = {
        "cover": cover,
        "business": business,
        "glance": glance,
        "findings": findings,
        "landscape": landscape,
        "workbench": workbench,
        "legal": legal,
        "confirm": confirm,
        "evidence": evidence,
        "deliverables": deliverables,
    }
    outline = []
    for section_id, no, title in REPORT_SECTIONS:
        if pieces.get(section_id):
            outline.append({"id": section_id, "no": no, "title": title})
    return {
        "mode": mode,
        "outline": outline,
        **pieces,
    }


def _render_html(view: Dict[str, Any]) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    tmpl_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    tmpl_dir = os.path.abspath(tmpl_dir)
    env = Environment(
        loader=FileSystemLoader(tmpl_dir),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("paid_result_premium_pdf_v1.html")
    return template.render(**view)


def build_paid_result_pdf_html_v1(premium_result: dict) -> str:
    """premium_result_v1 → HTML. 입력 mutation 0. HTTP/DB/LEG/LLM/datetime/random 0."""
    return _render_html(_build_view(_as_dict(premium_result)))


async def generate_paid_result_pdf_v1(premium_result: dict) -> bytes:
    """HTML → Gotenberg Chromium PDF. transport 만."""
    html = build_paid_result_pdf_html_v1(premium_result)
    url = "{}{}".format(GOTENBERG_URL.rstrip("/"), GOTENBERG_CONVERT_PATH)
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            files={"files": ("index.html", html.encode("utf-8"), "text/html")},
            data=dict(GOTENBERG_A4),
        )
    if response.status_code != 200:
        raise PaidResultPdfTransportError(
            response.status_code,
            "PDF 생성 실패: Gotenberg {}".format(response.status_code),
        )
    return response.content


__all__ = [
    "CANONICAL_UNAVAILABLE",
    "GOTENBERG_A4",
    "GOTENBERG_CONVERT_PATH",
    "GOTENBERG_URL",
    "PaidResultPdfTransportError",
    "build_paid_result_pdf_html_v1",
    "canonical_source_text",
    "generate_paid_result_pdf_v1",
    "pdf_content_disposition",
    "pdf_filename",
    "result_mode",
]
