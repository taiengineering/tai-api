# routers/law_collector.py v3.0.5
# v3.0.5: type 파라미터 제거 (data.go.kr 공식 cURL 샘플 검증 — type 미사용)
# v3.0.4: target=law 필수 파라미터 추가 (data.go.kr 공식 스펙 검증)
# v3.0.3: pageIndex → pageNo (data.go.kr 공공데이터포털 표준 파라미터명)
# v3.0.2: DATA_GO_KR_SERVICE_KEY 환경변수 호환 추가 (Railway 변수명)
# v3.0.1: messaging import 수정 (SMS_URL → EDGE_SMS_URL, _call_messageme → _call_edge_function)
# v3.0.0: data.go.kr API 전환

import os
import hashlib
import base64
import requests
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, date
from typing import Any, List, Optional, Tuple
from fastapi import APIRouter, BackgroundTasks, HTTPException
from db.database import get_supabase
from routers.messaging import EDGE_SMS_URL as SMS_URL, _call_edge_function as _call_messageme, _get_cfg

router = APIRouter(prefix="/law-collector", tags=["법령 수집기"])

# ============================================================
# 설정 — data.go.kr API (Railway IP 제한 없음)
# ============================================================

DATA_GOV_KEY  = os.environ.get("DATA_GO_KR_SERVICE_KEY", "") or os.environ.get("DATA_GOV_SERVICE_KEY", "")
DATA_GOV_BASE = "https://apis.data.go.kr/1170000/law"

# 폴백: law.go.kr (로컬 개발용)
LAW_API_OC   = os.environ.get("LAW_API_OC", "taieng")
LAW_API_BASE = "http://www.law.go.kr/DRF"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TAI-LawCollector/3.0)",
    "Accept": "application/xml,text/xml,*/*",
}

_CHUNK_SIZE = 100


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


# ============================================================
# 유틸
# ============================================================

def make_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_date(date_str: str) -> Optional[date]:
    if not date_str or len(date_str) != 8:
        return None
    try:
        return datetime.strptime(date_str, "%Y%m%d").date()
    except:
        return None


def clean_cdata(text: str) -> str:
    return text.strip() if text else ""


def _safe_int(val: str) -> Optional[int]:
    try:
        return int(val.strip()) if val and val.strip() else None
    except:
        return None


def law_type_name_to_code(name: str) -> str:
    mapping = {
        "법률": "LAW", "대통령령": "ENFORCEMENT_DECREE",
        "총리령": "ENFORCEMENT_RULE", "부령": "ENFORCEMENT_RULE",
        "고시": "NOTICE", "훈령": "NOTICE", "예규": "NOTICE",
        "기술기준": "STANDARD", "규정": "STANDARD",
    }
    for key, code in mapping.items():
        if key in name:
            return code
    return "OTHER"


def _synthesize_article_text(jo: ET.Element) -> str:
    lines: List[str] = []
    head = clean_cdata(jo.findtext("조문내용", ""))
    if head.strip():
        lines.append(head.strip())
    for hang in jo.findall("항"):
        hno = clean_cdata(hang.findtext("항번호", ""))
        htext = clean_cdata(hang.findtext("항내용", ""))
        if hno and htext:
            lines.append(f"[{hno}] {htext}")
        elif htext:
            lines.append(htext)
        elif hno:
            lines.append(f"[{hno}]")
        for ho in hang.findall("호"):
            hon = clean_cdata(ho.findtext("호번호", ""))
            hot = clean_cdata(ho.findtext("호내용", ""))
            if hon and hot:
                lines.append(f"  [{hon}] {hot}")
            elif hot:
                lines.append(f"  {hot}")
            elif hon:
                lines.append(f"  [{hon}]")
            for mok in ho.findall("목"):
                mn = clean_cdata(mok.findtext("목번호", ""))
                mt = clean_cdata(mok.findtext("목내용", ""))
                if mn and mt:
                    lines.append(f"    [{mn}] {mt}")
                elif mt:
                    lines.append(f"    {mt}")
                elif mn:
                    lines.append(f"    [{mn}]")
    return "\n".join(lines).strip()


def _article_completeness_score(article: dict) -> Tuple[int, int, int]:
    text = article.get("article_text") or ""
    title = article.get("article_title") or ""
    paras = article.get("paragraphs") or []
    return (len(text), len(title), len(paras))


def _iter_jo_units(root: ET.Element) -> List[ET.Element]:
    strict = root.findall("./조문/조문단위")
    if strict:
        return strict
    return root.findall(".//조문단위")


def _parse_article_from_jo(jo: ET.Element) -> dict:
    article = {
        "article_internal_key": jo.get("조문키", ""),
        "article_no":           _safe_int(jo.findtext("조문번호", "")),
        "article_sub_no":       _safe_int(jo.findtext("조문가지번호", "")),
        "article_type":         jo.findtext("조문여부", ""),
        "article_title":        clean_cdata(jo.findtext("조문제목", "")),
        "article_text":         _synthesize_article_text(jo),
        "enforcement_date":     parse_date(jo.findtext("조문시행일자", "")),
        "is_changed":           jo.findtext("조문변경여부", "N") == "Y",
        "paragraphs":           [],
    }
    for hang in jo.findall("항"):
        paragraph = {
            "paragraph_no":   clean_cdata(hang.findtext("항번호", "")),
            "paragraph_text": clean_cdata(hang.findtext("항내용", "")),
            "items":          [],
        }
        for ho in hang.findall("호"):
            item = {
                "item_level_code": "HO",
                "item_no":         clean_cdata(ho.findtext("호번호", "")),
                "item_text":       clean_cdata(ho.findtext("호내용", "")),
                "sub_items":       [],
            }
            for mok in ho.findall("목"):
                item["sub_items"].append({
                    "item_level_code": "MOK",
                    "item_no":         clean_cdata(mok.findtext("목번호", "")),
                    "item_text":       clean_cdata(mok.findtext("목내용", "")),
                })
            paragraph["items"].append(item)
        article["paragraphs"].append(paragraph)
    return article


def _dedupe_articles_by_internal_key(articles: List[dict]) -> List[dict]:
    by_key: dict[str, dict] = {}
    for idx, art in enumerate(articles):
        k = (art.get("article_internal_key") or "").strip()
        if not k:
            art = {**art, "article_internal_key": f"__noid_{idx}"}
            k = art["article_internal_key"]
        cur = by_key.get(k)
        if cur is None or _article_completeness_score(art) > _article_completeness_score(cur):
            by_key[k] = art
    merged = list(by_key.values())
    merged.sort(key=lambda a: (
        a.get("article_no") is None,
        a.get("article_no") or 0,
        a.get("article_sub_no") or 0,
    ))
    return merged


def snapshot_article_key_map_for_version(supabase: Any, version_id: str) -> None:
    try:
        arts = supabase.table("law_article").select("id,article_internal_key").eq(
            "law_version_id", version_id
        ).execute().data or []
        for a in arts:
            supabase.table("law_article_key_map").insert({
                "old_article_id": a["id"],
                "new_article_id": None,
                "article_internal_key": a.get("article_internal_key") or "",
                "law_version_id": version_id,
            }).execute()
    except Exception:
        return


def _chunked(seq, size: int = _CHUNK_SIZE):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _nullify_dependent_article_refs(supabase: Any, art_ids: List[str]) -> None:
    if not art_ids:
        return
    for table, col in (
        ("law_rule_drafts", "article_id"),
        ("inspection_set_items", "law_article_id"),
        ("law_rule_source_map", "article_id"),
    ):
        try:
            for chunk in _chunked(art_ids):
                supabase.table(table).update({col: None}).in_(col, chunk).execute()
        except Exception as e:
            print(f"[law_collector] {table}.{col} nullify skip: {e}")


def _clear_law_version_fk_dependents(supabase: Any, version_id: str) -> None:
    for tbl, col, op in [
        ("law_parsing_result",   None,              "delete"),
        ("law_attachment",       None,              "delete"),
        ("law_article_diff",     "new_version_id",  "delete"),
        ("law_article_diff",     "old_version_id",  "delete"),
        ("law_rule_source_map",  None,              "delete"),
    ]:
        try:
            q = supabase.table(tbl)
            if op == "delete":
                if col:
                    q.delete().eq(col, version_id).execute()
                else:
                    q.delete().eq("law_version_id", version_id).execute()
        except Exception as e:
            print(f"[law_collector] {tbl} {op} skip: {e}")
    for tbl, col in [
        ("law_update_tracking", "last_collected_version_id"),
        ("law_change_log",      "new_version_id"),
        ("law_change_log",      "old_version_id"),
    ]:
        try:
            supabase.table(tbl).update({col: None}).eq(col, version_id).execute()
        except Exception as e:
            print(f"[law_collector] {tbl}.{col} nullify skip: {e}")


def delete_law_version_cascade_for_recollect(supabase: Any, version_id: str) -> None:
    arts = supabase.table("law_article").select("id").eq("law_version_id", version_id).execute().data or []
    art_ids = [r["id"] for r in arts]
    if art_ids:
        _nullify_dependent_article_refs(supabase, art_ids)
        para_ids: list[str] = []
        for chunk in _chunked(art_ids):
            paras = supabase.table("law_paragraph").select("id").in_("article_id", chunk).execute().data or []
            para_ids.extend(p["id"] for p in paras)
        if para_ids:
            all_items: list[dict] = []
            for chunk in _chunked(para_ids):
                items = supabase.table("law_item").select("id,parent_item_id").in_(
                    "paragraph_id", chunk
                ).execute().data or []
                all_items.extend(items)
            child_ids = [i["id"] for i in all_items if i.get("parent_item_id")]
            if child_ids:
                for chunk in _chunked(child_ids):
                    supabase.table("law_item").delete().in_("id", chunk).execute()
            for chunk in _chunked(para_ids):
                supabase.table("law_item").delete().in_("paragraph_id", chunk).execute()
        for chunk in _chunked(art_ids):
            supabase.table("law_paragraph").delete().in_("article_id", chunk).execute()
        supabase.table("law_article").delete().eq("law_version_id", version_id).execute()
    _clear_law_version_fk_dependents(supabase, version_id)
    supabase.table("law_content_raw").delete().eq("law_version_id", version_id).execute()
    supabase.table("law_version").delete().eq("id", version_id).execute()


# ============================================================
# API 호출
# ============================================================

def fetch_law_list(query: str, display: int = 100, page: int = 1) -> dict:
    if DATA_GOV_KEY:
        url = f"{DATA_GOV_BASE}/lawSearchList.do"
        # v3.0.5: 공식 cURL 샘플 정확 매칭 (type 미사용)
        # serviceKey, target=law (고정값), query, numOfRows, pageNo
        params = {"serviceKey": DATA_GOV_KEY, "target": "law", "query": query,
                  "numOfRows": display, "pageNo": page}
        resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=30)
        resp.encoding = "utf-8"
        return {"xml": resp.text, "status": resp.status_code, "ok": resp.ok, "source": "data.go.kr"}
    else:
        url = f"{LAW_API_BASE}/lawSearch.do"
        params = {"OC": LAW_API_OC, "target": "law", "type": "XML",
                  "query": query, "display": display, "page": page}
        resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=30)
        resp.encoding = "utf-8"
        return {"xml": resp.text, "status": resp.status_code, "ok": resp.ok, "source": "law.go.kr"}


def fetch_law_content(mst_no: str) -> dict:
    if DATA_GOV_KEY:
        url = f"{DATA_GOV_BASE}/lawService.do"
        # v3.0.5: type 제거. 단 lawService.do는 다른 데이터셋 (15057358 LINK형 — OC 인증)일 수 있어
        # 현재 data.go.kr 키로는 동작 안 할 가능성 — Step F에서 별도 검증 필요
        params = {"serviceKey": DATA_GOV_KEY, "target": "law", "MST": mst_no}
        resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=60)
        resp.encoding = "utf-8"
        return {"xml": resp.text, "status": resp.status_code, "ok": resp.ok, "source": "data.go.kr"}
    else:
        url = f"{LAW_API_BASE}/lawService.do"
        params = {"OC": LAW_API_OC, "target": "law", "MST": mst_no, "type": "XML"}
        resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=60)
        resp.encoding = "utf-8"
        return {"xml": resp.text, "status": resp.status_code, "ok": resp.ok, "source": "law.go.kr"}


# ============================================================
# XML 파싱
# ============================================================

def parse_law_list_xml(xml_text: str) -> list:
    root = ET.fromstring(xml_text)
    laws = []
    for law in root.findall(".//법령") + root.findall(".//law"):
        laws.append({
            "law_mst_no":        law.findtext("법령일련번호", "") or law.findtext("법령ID", ""),
            "law_api_id":        law.findtext("법령ID", ""),
            "law_name":          clean_cdata(law.findtext("법령명한글", "") or law.findtext("법령명", "")),
            "law_name_short":    clean_cdata(law.findtext("법령약칭명", "")),
            "law_type_name":     law.findtext("법령구분명", ""),
            "ministry_code":     law.findtext("소관부처코드", ""),
            "ministry_name":     law.findtext("소관부처명", ""),
            "law_number":        law.findtext("공포번호", ""),
            "announcement_date": parse_date(law.findtext("공포일자", "")),
            "enforcement_date":  parse_date(law.findtext("시행일자", "")),
            "revision_type":     law.findtext("제개정구분명", ""),
            "current_status":    law.findtext("현행연혁코드", ""),
        })
    return laws


def parse_law_content_xml(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    basic = root.find("기본정보")
    info = {}
    if basic is not None:
        ministry_el = basic.find("소관부처")
        info = {
            "law_api_id":        basic.findtext("법령ID", ""),
            "announcement_date": parse_date(basic.findtext("공포일자", "")),
            "law_number":        basic.findtext("공포번호", ""),
            "law_name":          clean_cdata(basic.findtext("법령명_한글", "")),
            "law_type_name":     basic.findtext("법종구분", ""),
            "ministry_code":     ministry_el.get("소관부처코드", "") if ministry_el is not None else "",
            "ministry_name":     basic.findtext("소관부처", ""),
            "enforcement_date":  parse_date(basic.findtext("시행일자", "")),
            "revision_type":     basic.findtext("제개정구분", ""),
        }
    raw_articles = [_parse_article_from_jo(jo) for jo in _iter_jo_units(root)]
    articles = _dedupe_articles_by_internal_key(raw_articles)
    for art in articles:
        ik = art.get("article_internal_key") or ""
        if ik.startswith("__noid_"):
            art["article_internal_key"] = ""
    return {"info": info, "articles": articles, "raw_xml": xml_text}


# ============================================================
# DB 저장
# ============================================================

def save_law_to_db(law_info: dict, raw_xml: str, articles: list, supabase) -> dict:
    law_mst_no    = law_info.get("law_mst_no", "")
    law_api_id    = law_info.get("law_api_id", "")
    law_name      = law_info.get("law_name", "")
    law_type_code = law_type_name_to_code(law_info.get("law_type_name", ""))
    raw_hash      = make_hash(raw_xml)
    version_no    = f"{law_info.get('announcement_date', '')}_{law_info.get('law_number', '')}"
    law_key       = f"{law_api_id}_{law_mst_no}"

    master_res = supabase.table("law_master").upsert({
        "law_key": law_key, "law_api_id": law_api_id, "law_mst_no": law_mst_no,
        "law_name": law_name, "law_name_short": law_info.get("law_name_short", ""),
        "law_type_code": law_type_code, "ministry_code": law_info.get("ministry_code", ""),
        "ministry_name": law_info.get("ministry_name", ""),
        "law_number": str(law_info.get("law_number", "")),
        "law_status_code": "ACTIVE",
        "announcement_date": str(law_info.get("announcement_date")) if law_info.get("announcement_date") else None,
        "enforcement_date": str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
        "source_system": "data.go.kr/law", "is_active": True,
        "updated_at": datetime.now().isoformat(),
    }, on_conflict="law_key").execute()
    law_id = master_res.data[0]["id"]

    existing_version = supabase.table("law_version")\
        .select("id").eq("law_id", law_id).eq("law_mst_no", law_mst_no).execute()

    if existing_version.data:
        version_id = existing_version.data[0]["id"]
        is_new_version = False
    else:
        version_res = supabase.table("law_version").insert({
            "law_id": law_id, "version_no": version_no, "law_mst_no": law_mst_no,
            "revision_type_code": law_info.get("revision_type", ""),
            "announcement_date": str(law_info.get("announcement_date")) if law_info.get("announcement_date") else None,
            "enforcement_date": str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
            "effective_from": str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
            "is_current": True, "version_status_code": "ACTIVE",
            "raw_hash": raw_hash, "updated_at": datetime.now().isoformat(),
        }).execute()
        version_id = version_res.data[0]["id"]
        is_new_version = True
        supabase.table("law_version").update({"is_current": False})\
            .eq("law_id", law_id).neq("id", version_id).execute()
        supabase.table("law_master")\
            .update({"current_version_id": version_id, "current_version_no": version_no})\
            .eq("id", law_id).execute()

    if is_new_version:
        supabase.table("law_content_raw").insert({
            "law_version_id": version_id, "content_type_code": "XML",
            "raw_xml": raw_xml, "text_hash": raw_hash,
            "updated_at": datetime.now().isoformat(),
        }).execute()

    article_count = 0
    if is_new_version:
        for art in articles:
            art_res = supabase.table("law_article").insert({
                "law_version_id": version_id,
                "article_internal_key": art["article_internal_key"],
                "article_no": art["article_no"], "article_sub_no": art["article_sub_no"],
                "article_no_sort": f"{str(art['article_no'] or 0).zfill(4)}-{str(art['article_sub_no'] or 0).zfill(3)}",
                "article_type": art["article_type"], "article_title": art["article_title"],
                "article_text": art["article_text"], "is_changed": art["is_changed"],
                "enforcement_date": str(art["enforcement_date"]) if art["enforcement_date"] else None,
                "article_status_code": "ACTIVE", "updated_at": datetime.now().isoformat(),
            }).execute()
            article_id = art_res.data[0]["id"]
            article_count += 1
            for p_idx, para in enumerate(art["paragraphs"]):
                para_res = supabase.table("law_paragraph").insert({
                    "article_id": article_id, "paragraph_no": para["paragraph_no"],
                    "paragraph_no_sort": p_idx + 1, "paragraph_text": para["paragraph_text"],
                    "paragraph_status_code": "ACTIVE", "updated_at": datetime.now().isoformat(),
                }).execute()
                paragraph_id = para_res.data[0]["id"]
                for i_idx, item in enumerate(para["items"]):
                    item_res = supabase.table("law_item").insert({
                        "paragraph_id": paragraph_id, "item_level_code": "HO",
                        "item_no": item["item_no"], "item_no_sort": i_idx + 1,
                        "item_text": item["item_text"], "item_status_code": "ACTIVE",
                        "updated_at": datetime.now().isoformat(),
                    }).execute()
                    item_id = item_res.data[0]["id"]
                    for s_idx, sub in enumerate(item["sub_items"]):
                        supabase.table("law_item").insert({
                            "paragraph_id": paragraph_id, "parent_item_id": item_id,
                            "item_level_code": "MOK", "item_no": sub["item_no"],
                            "item_no_sort": s_idx + 1, "item_text": sub["item_text"],
                            "item_status_code": "ACTIVE", "updated_at": datetime.now().isoformat(),
                        }).execute()

    supabase.table("law_update_tracking").upsert({
        "law_id": law_id, "last_checked_at": datetime.now().isoformat(),
        "last_source_mst_no": law_mst_no, "last_source_hash": raw_hash,
        "last_collected_version_id": version_id, "update_needed": False,
        "job_status_code": "SUCCESS", "job_message": f"수집완료 - 조문 {article_count}개",
        "updated_at": datetime.now().isoformat(),
    }, on_conflict="law_id").execute()

    return {"law_id": law_id, "version_id": version_id,
            "is_new_version": is_new_version, "article_count": article_count}


# ============================================================
# 개정 감지 + AI 룰 NEEDS_REVIEW 표시
# ============================================================

def mark_rules_needs_review(law_name: str, change_summary: str, supabase) -> int:
    res = supabase.table("law_rule_drafts").update({
        "status":          "NEEDS_REVIEW",
        "review_reason":   f"법령 개정 감지: {change_summary}",
        "law_changed_at":  datetime.now().isoformat(),
        "updated_at":      datetime.now().isoformat(),
    }).eq("law_name", law_name).eq("status", "APPROVED").execute()
    return len(res.data) if res.data else 0


def _publish_law_revision_board(law_id: str, law_name: str, change_summary: str, supabase) -> None:
    try:
        now_iso = datetime.now().isoformat()
        supabase.table("law_revision_board").insert({
            "law_id": law_id,
            "law_name": law_name,
            "title": f"[법령개정] {law_name}",
            "body": f"{law_name} 개정 감지: {change_summary}",
            "status": "PUBLISHED",
            "is_public": True,
            "published_at": now_iso,
            "created_at": now_iso,
            "updated_at": now_iso,
        }).execute()
    except Exception as e:
        print(f"[LAW_UPDATE] law_revision_board INSERT 실패: {e}")


def _notify_safety_managers_by_law_change(law_name: str, change_summary: str, supabase) -> int:
    notified = 0
    try:
        sets_res = supabase.table("inspection_sets") \
            .select("id, company_id").eq("is_active", True) \
            .ilike("law_name", f"%{law_name}%").execute()
        company_ids = sorted({r.get("company_id") for r in (sets_res.data or []) if r.get("company_id")})
        if not company_ids:
            return 0
        users_res = supabase.table("users") \
            .select("id, company_id, phone, allow_sms") \
            .in_("company_id", company_ids) \
            .in_("role_code", ["003", "012"]) \
            .eq("is_active", True).execute()
        users = users_res.data or []
        if not users:
            return 0
        title = "법령 개정으로 점검 재검토가 필요합니다"
        body = f"{law_name} 개정 감지: {change_summary}"
        cfg = _get_cfg()
        for u in users:
            try:
                supabase.table("notifications").insert({
                    "user_id": u["id"],
                    "company_id": u.get("company_id"),
                    "trigger_code": "LAW_CHANGED",
                    "trigger_group": "LAW",
                    "title": title,
                    "body": body,
                    "priority": "HIGH",
                    "is_read": False,
                    "channel": "push",
                    "send_status": "SENT",
                    "sent_at": datetime.now().isoformat(),
                }).execute()
            except Exception as e:
                print(f"[LAW_UPDATE] notifications INSERT 실패 user={u.get('id')}: {e}")
            if cfg["edge_url"] and u.get("allow_sms") and u.get("phone"):
                try:
                    _call_messageme({
                        "receiver": u["phone"],
                        "message": f"[TAI] {law_name} 개정 감지. 점검/법령 항목을 확인해 주세요.",
                    })
                except Exception as e:
                    print(f"[LAW_UPDATE] SMS 실패 user={u.get('id')}: {e}")
            notified += 1
    except Exception as e:
        print(f"[LAW_UPDATE] 안전관리자 알림 처리 실패: {e}")
    return notified


def _mark_inspection_items_law_changed(law_name: str, supabase) -> int:
    try:
        sets_res = supabase.table("inspection_sets") \
            .select("id").eq("is_active", True) \
            .ilike("law_name", f"%{law_name}%").execute()
        set_ids = [r["id"] for r in (sets_res.data or []) if r.get("id")]
        if not set_ids:
            return 0
        upd = supabase.table("inspection_set_items").update({
            "is_law_changed": True,
            "updated_at": datetime.now().isoformat(),
        }).in_("inspection_set_id", set_ids).execute()
        return len(upd.data or [])
    except Exception as e:
        print(f"[LAW_UPDATE] inspection_set_items 변경표시 실패: {e}")
        return 0


def check_law_update(law_tracking: dict, supabase) -> dict:
    law_id      = law_tracking["law_id"]
    last_mst_no = law_tracking.get("last_source_mst_no", "")
    last_hash   = law_tracking.get("last_source_hash", "")
    master = supabase.table("law_master").select("law_name, law_api_id, law_mst_no")\
        .eq("id", law_id).single().execute()
    if not master.data:
        return {"changed": False, "reason": "법령 마스터 없음"}
    law_name = master.data["law_name"]
    list_result = fetch_law_list(query=law_name, display=5)
    if not list_result["ok"]:
        return {"changed": False, "reason": f"API 오류 {list_result['status']}"}
    laws = parse_law_list_xml(list_result["xml"])
    if not laws:
        return {"changed": False, "reason": "API 결과 없음"}
    current = laws[0]
    current_mst_no = current["law_mst_no"]
    if current_mst_no == last_mst_no:
        supabase.table("law_update_tracking").update({
            "last_checked_at": datetime.now().isoformat(), "update_needed": False,
            "job_status_code": "SUCCESS", "job_message": "변경 없음",
            "updated_at": datetime.now().isoformat(),
        }).eq("law_id", law_id).execute()
        return {"changed": False, "law_name": law_name}
    content_result = fetch_law_content(current_mst_no)
    if not content_result["ok"]:
        return {"changed": False, "reason": f"본문 API 오류 {content_result['status']}"}
    parsed = parse_law_content_xml(content_result["xml"])
    new_hash = make_hash(content_result["xml"])
    if new_hash == last_hash:
        return {"changed": False, "law_name": law_name, "reason": "해시 동일"}
    old_version = supabase.table("law_version").select("id")\
        .eq("law_id", law_id).eq("is_current", True).execute()
    old_version_id = old_version.data[0]["id"] if old_version.data else None
    law_info = {**parsed["info"], "law_mst_no": current_mst_no,
                "law_name_short": current.get("law_name_short", ""),
                "revision_type":  current.get("revision_type", "")}
    save_result = save_law_to_db(law_info, content_result["xml"], parsed["articles"], supabase)
    change_summary = f"{current.get('revision_type', '')} ({current_mst_no})"
    supabase.table("law_change_log").insert({
        "law_id": law_id, "old_version_id": old_version_id,
        "new_version_id": save_result["version_id"],
        "change_detected_date": datetime.now().isoformat(),
        "change_scope_code": "FULL" if "전부" in current.get("revision_type", "") else "PARTIAL",
        "changed_article_count": sum(1 for a in parsed["articles"] if a.get("is_changed")),
        "change_summary": change_summary,
        "processed_status_code": "DETECTED", "updated_at": datetime.now().isoformat(),
    }).execute()
    needs_review_count = mark_rules_needs_review(law_name, change_summary, supabase)
    _publish_law_revision_board(law_id, law_name, change_summary, supabase)
    notified_count = _notify_safety_managers_by_law_change(law_name, change_summary, supabase)
    law_changed_items = _mark_inspection_items_law_changed(law_name, supabase)
    supabase.table("law_update_tracking").update({
        "last_checked_at": datetime.now().isoformat(),
        "last_source_mst_no": current_mst_no, "last_source_hash": new_hash,
        "last_collected_version_id": save_result["version_id"],
        "update_needed": False, "job_status_code": "SUCCESS",
        "job_message": f"개정 감지 — AI룰 {needs_review_count}개 재검토 표시",
        "updated_at": datetime.now().isoformat(),
    }).eq("law_id", law_id).execute()
    return {
        "changed":            True,
        "law_name":           law_name,
        "old_mst_no":         last_mst_no,
        "new_mst_no":         current_mst_no,
        "articles":           save_result["article_count"],
        "needs_review_rules": needs_review_count,
        "notified_safety_managers": notified_count,
        "inspection_items_law_changed": law_changed_items,
    }


# ============================================================
# 라우터 엔드포인트
# ============================================================

@router.get("/debug/{law_name}")
async def debug_law_api(law_name: str):
    try:
        result = fetch_law_list(query=law_name, display=5)
        http_status = result["status"]
        xml_text    = result["xml"]
        source      = result.get("source", "unknown")
        try:
            root = ET.fromstring(xml_text)
            laws = root.findall(".//법령") + root.findall(".//law")
            law_count = len(laws)
            root_tag  = root.tag
            first_law = {}
            if laws:
                for child in laws[0]:
                    first_law[child.tag] = child.text
        except Exception as pe:
            law_count, root_tag, first_law = -1, "parse_error", {"error": str(pe)}
        return {
            "api_source":  source, "has_api_key": bool(DATA_GOV_KEY),
            "query": law_name, "http_status": http_status, "ok": result["ok"],
            "law_count": law_count, "xml_root_tag": root_tag, "first_law": first_law,
            "xml_b64": _b64(xml_text[:2000]),
        }
    except Exception as e:
        return {"error_type": type(e).__name__, "error_b64": _b64(str(e))}


@router.post("/collect/all")
async def collect_all_laws(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_collect_all)
    return {"status": "started", "message": "전체 법령 수집 시작."}


def _run_collect_all():
    supabase = get_supabase()
    targets = supabase.table("law_collection_target")\
        .select("*").eq("is_active", True).eq("collection_method", "API")\
        .order("collection_priority").execute()
    results = {"success": 0, "failed": 0, "skipped": 0, "errors": []}
    for target in targets.data:
        try:
            list_result = fetch_law_list(query=target["law_name"], display=5)
            if not list_result["ok"]:
                results["failed"] += 1
                results["errors"].append({"law_name": target["law_name"], "error": f"HTTP {list_result['status']}"})
                continue
            laws = parse_law_list_xml(list_result["xml"])
            if not laws:
                results["skipped"] += 1
                continue
            matched = next((l for l in laws if target["law_name"] in l["law_name"]), laws[0])
            content_result = fetch_law_content(matched["law_mst_no"])
            if not content_result["ok"]:
                results["failed"] += 1
                continue
            parsed = parse_law_content_xml(content_result["xml"])
            law_info = {**parsed["info"], "law_mst_no": matched["law_mst_no"],
                        "law_name_short": matched.get("law_name_short", ""),
                        "revision_type": matched.get("revision_type", "")}
            save_law_to_db(law_info, content_result["xml"], parsed["articles"], supabase)
            results["success"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"law_name": target["law_name"], "error": type(e).__name__})
    return results


@router.post("/collect/{law_name}")
async def collect_single_law(law_name: str, force: bool = False):
    supabase = get_supabase()
    try:
        list_result = fetch_law_list(query=law_name, display=10)
        if not list_result["ok"]:
            raise HTTPException(status_code=502, detail=f"법제처 API 오류 HTTP {list_result['status']}")
        laws = parse_law_list_xml(list_result["xml"])
        if not laws:
            raise HTTPException(status_code=404, detail=f"법령을 찾을 수 없습니다: {law_name}")
        matched = next((l for l in laws if law_name in l["law_name"]), laws[0])
        content_result = fetch_law_content(matched["law_mst_no"])
        if not content_result["ok"]:
            raise HTTPException(status_code=502, detail=f"법제처 본문 API 오류 HTTP {content_result['status']}")
        parsed = parse_law_content_xml(content_result["xml"])
        if force:
            law_key_check = supabase.table("law_master")\
                .select("id").ilike("law_name", f"%{matched['law_name']}%").limit(1).execute()
            if law_key_check.data:
                existing_law_id = law_key_check.data[0]["id"]
                ev = supabase.table("law_version")\
                    .select("id").eq("law_id", existing_law_id).eq("law_mst_no", matched["law_mst_no"]).execute()
                if ev.data:
                    old_vid = ev.data[0]["id"]
                    snapshot_article_key_map_for_version(supabase, old_vid)
                    delete_law_version_cascade_for_recollect(supabase, old_vid)
        law_info = {**parsed["info"], "law_mst_no": matched["law_mst_no"],
                    "law_name_short": matched.get("law_name_short", ""),
                    "revision_type": matched.get("revision_type", "")}
        result = save_law_to_db(law_info, content_result["xml"], parsed["articles"], supabase)
        return {
            "status": "success", "api_source": list_result.get("source"),
            "law_name": matched["law_name"], "law_mst_no": matched["law_mst_no"],
            "is_new_version": result["is_new_version"], "article_count": result["article_count"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)[:200]}")


@router.post("/check-updates")
async def check_all_updates(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_check_updates)
    return {"status": "started", "message": "변경 감지 시작됐습니다."}


@router.post("/check-updates-v2")
async def check_all_updates_v2(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_check_updates)
    return {"status": "started", "message": "법령 개정 감지 시작 — 변경 시 AI 룰 재검토 표시됩니다."}


def _run_check_updates():
    supabase = get_supabase()
    trackings = supabase.table("law_update_tracking").select("*").execute()
    results = {"checked": 0, "changed": 0, "needs_review_total": 0, "errors": []}
    for tracking in trackings.data:
        try:
            result = check_law_update(tracking, supabase)
            results["checked"] += 1
            if result.get("changed"):
                results["changed"] += 1
                results["needs_review_total"] += result.get("needs_review_rules", 0)
        except Exception as e:
            results["errors"].append({"law_id": tracking["law_id"], "error": type(e).__name__})
    return results


@router.get("/status")
async def get_collection_status():
    supabase = get_supabase()
    total     = supabase.table("law_master").select("id", count="exact").execute()
    collected = supabase.table("law_update_tracking").select("id", count="exact").execute()
    changed   = supabase.table("law_change_log").select("id", count="exact").execute()
    needs_rev = supabase.table("law_rule_drafts").select("id", count="exact")\
        .eq("status", "NEEDS_REVIEW").execute()
    failed    = supabase.table("law_update_tracking")\
        .select("law_id, job_message, updated_at").eq("job_status_code", "FAILED")\
        .order("updated_at", desc=True).limit(10).execute()
    return {
        "version":             "3.0.5",
        "api_source":          "data.go.kr" if DATA_GOV_KEY else "law.go.kr (폴백)",
        "has_api_key":         bool(DATA_GOV_KEY),
        "collected_law_count": total.count,
        "tracked_law_count":   collected.count,
        "change_log_count":    changed.count,
        "needs_review_rules":  needs_rev.count,
        "recent_failed":       failed.data,
    }
