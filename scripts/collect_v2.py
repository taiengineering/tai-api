#!/usr/bin/env python3
"""
법령 수집 v3 - 조문 중심 설계 (Article-Centric)

주요 변경 (v2.1 → v3.0):
  - 테이블명: law_master_new → law_master (Atomic Switch 완료 후)
  - 저장 방식: DELETE + INSERT → UPSERT 기반
  - 조문 UUID 영구 유지: (law_id, article_internal_key) UNIQUE 활용
  - 재수집해도 외부 참조 안 끊어짐

설계 문서:
  docs/ARTICLE_CENTRIC_DESIGN_2026-04-23.md

사용법:
    cd ~/dev/tai-api
    set -a; source .env; set +a
    
    python3 scripts/collect_v2.py test "산업안전보건법"
    python3 scripts/collect_v2.py all
    python3 scripts/collect_v2.py retry
    python3 scripts/collect_v2.py domain FIRE
    python3 scripts/collect_v2.py monitor
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Optional

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from services.time import now_kst, serialize_business_datetime
from db.database import get_supabase
from routers.law_collector import (
    fetch_law_list,
    fetch_law_content,
    parse_law_list_xml,
    parse_law_content_xml,
    law_type_name_to_code,
    make_hash,
)
from routers.law_collector_admrul import (
    fetch_admrul_list,
    fetch_admrul_content,
    parse_admrul_list_xml,
    parse_admrul_content_xml,
)


# ═══════════════════════════════════════════════════════════
# 유틸
# ═══════════════════════════════════════════════════════════

def _is_admrul(target: dict) -> bool:
    """행정규칙 여부 (STANDARD/NOTICE 또는 NFTC/NFPC 포함)."""
    type_code = target.get("law_type_code", "")
    name = target.get("law_name", "") or ""
    if type_code in ("STANDARD", "NOTICE"):
        return True
    if "NFTC" in name or "NFPC" in name:
        return True
    return False


def get_targets(supabase, filter_type: str = "pending", value: str = None) -> list[dict]:
    query = supabase.table("law_collection_target") \
        .select("*") \
        .eq("is_active", True)
    
    if filter_type == "pending":
        query = query.eq("collection_status", "PENDING")
    elif filter_type == "failed":
        query = query.eq("collection_status", "FAILED")
    elif filter_type == "domain":
        query = query.eq("domain_code", value)
    elif filter_type == "name":
        query = query.ilike("law_name", f"%{value}%")
    
    result = query.order("collection_priority") \
        .order("added_in_phase") \
        .order("law_name") \
        .execute()
    
    return result.data or []


def update_target_status(
    supabase, target_id: str, status: str,
    checklist: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    update_data = {
        "collection_status": status,
        "updated_at": serialize_business_datetime(now_kst()),
    }
    
    if status in ("SUCCESS", "FAILED", "SKIPPED"):
        update_data["last_collected_at"] = serialize_business_datetime(now_kst())
    
    if checklist is not None:
        update_data["last_collection_result"] = json.dumps(checklist, ensure_ascii=False, default=str)
        update_data["verification_checklist"] = json.dumps(checklist, ensure_ascii=False, default=str)
    
    if error:
        target = supabase.table("law_collection_target") \
            .select("remarks").eq("id", target_id).single().execute()
        existing_remarks = (target.data.get("remarks") or "") if target.data else ""
        ts = now_kst().strftime("%m-%d %H:%M")
        new_remarks = f"{existing_remarks} | [{ts}] {error[:200]}"
        update_data["remarks"] = new_remarks.strip(" |")
    
    supabase.table("law_collection_target") \
        .update(update_data) \
        .eq("id", target_id) \
        .execute()


# ═══════════════════════════════════════════════════════════
# 핵심: 조문 중심 UPSERT 저장
# ═══════════════════════════════════════════════════════════

def save_law_to_db(
    target: dict,
    law_info: dict,
    matched: dict,
    raw_xml: str,
    articles: list,
    supabase: Any,
    *,
    partial_merge: bool = False,
) -> dict:
    """
    조문 중심 UPSERT 저장:
      TX1: law_master UPSERT + law_version UPSERT + law_content_raw INSERT
      TX2: law_article UPSERT (law_id 기반) + paragraph/item 재구성
           - 조문 UUID는 (law_id, article_internal_key)로 영구 유지
           - paragraph/item은 article 단위로 delete+insert (하위 구조는 재파싱 가능)
      partial_merge=True: 이번 payload에 없는 기존 조문을 DELETED 처리하지 않음
                          (형법·민법 등 인용 Top-N 부분 적재 전용).
    """
    law_mst_no = matched.get("law_mst_no", "") or law_info.get("law_mst_no", "")
    law_api_id = matched.get("law_api_id", "") or law_info.get("law_api_id", "")
    law_name = law_info.get("law_name", "") or target.get("law_name", "")
    law_type_code = target.get("law_type_code") or law_type_name_to_code(
        law_info.get("law_type_name", "")
    )
    raw_hash = make_hash(raw_xml)
    
    version_no = f"{law_info.get('announcement_date', '')}_{law_info.get('law_number', '')}"
    law_key = f"{law_api_id}_{law_mst_no}"
    
    # ─── TX1-1: law_master UPSERT ──────────────────────────
    master_res = supabase.table("law_master").upsert({
        "law_key": law_key,
        "law_api_id": law_api_id,
        "law_mst_no": law_mst_no,
        "law_name": law_name,
        "law_name_short": matched.get("law_name_short", "") or law_info.get("law_name_short", ""),
        "law_type_code": law_type_code,
        "domain_code": target.get("domain_code"),
        "ministry_code": law_info.get("ministry_code", ""),
        "ministry_name": target.get("ministry_name") or law_info.get("ministry_name", ""),
        "law_number": str(law_info.get("law_number", "")),
        "law_status_code": "ACTIVE",
        "announcement_date": str(law_info.get("announcement_date")) if law_info.get("announcement_date") else None,
        "enforcement_date": str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
        "source_system": "law.go.kr/admrul" if _is_admrul(target) else (
            "data.go.kr/law" if os.environ.get("DATA_GOV_SERVICE_KEY") else "law.go.kr"
        ),
        "is_active": True,
        "updated_at": serialize_business_datetime(now_kst()),
    }, on_conflict="law_key").execute()
    
    if not master_res.data:
        raise RuntimeError("law_master upsert 실패")
    law_id = master_res.data[0]["id"]
    
    # ─── TX1-2: law_version UPSERT ─────────────────────────
    existing_version = supabase.table("law_version") \
        .select("id") \
        .eq("law_id", law_id) \
        .eq("version_no", version_no) \
        .execute()
    
    if existing_version.data:
        version_id = existing_version.data[0]["id"]
        supabase.table("law_version").update({
            "law_mst_no": law_mst_no,
            "revision_type_code": matched.get("revision_type", "") or law_info.get("revision_type", ""),
            "announcement_date": str(law_info.get("announcement_date")) if law_info.get("announcement_date") else None,
            "enforcement_date": str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
            "effective_from": str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
            "is_current": True,
            "version_status_code": "ACTIVE",
            "raw_hash": raw_hash,
            "updated_at": serialize_business_datetime(now_kst()),
        }).eq("id", version_id).execute()
        is_new_version = False
    else:
        version_res = supabase.table("law_version").insert({
            "law_id": law_id,
            "version_no": version_no,
            "law_mst_no": law_mst_no,
            "revision_type_code": matched.get("revision_type", "") or law_info.get("revision_type", ""),
            "announcement_date": str(law_info.get("announcement_date")) if law_info.get("announcement_date") else None,
            "enforcement_date": str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
            "effective_from": str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
            "is_current": True,
            "version_status_code": "ACTIVE",
            "raw_hash": raw_hash,
            "updated_at": serialize_business_datetime(now_kst()),
        }).execute()
        version_id = version_res.data[0]["id"]
        is_new_version = True
    
    if is_new_version:
        supabase.table("law_version") \
            .update({"is_current": False}) \
            .eq("law_id", law_id) \
            .neq("id", version_id) \
            .execute()
    
    supabase.table("law_master").update({
        "current_version_id": version_id,
        "current_version_no": version_no,
        "updated_at": serialize_business_datetime(now_kst()),
    }).eq("id", law_id).execute()
    
    # ─── TX1-3: law_content_raw (버전당 1개) ───────────────
    supabase.table("law_content_raw").delete().eq("law_version_id", version_id).execute()
    supabase.table("law_content_raw").insert({
        "law_version_id": version_id,
        "content_type_code": "XML",
        "raw_xml": raw_xml,
        "text_hash": raw_hash,
        "updated_at": serialize_business_datetime(now_kst()),
    }).execute()
    
    # ─── TX2: 조문 UPSERT (UUID 영구 유지) ─────────────────
    # 조문 중심 설계: (law_id, article_internal_key)로 UPSERT
    # 같은 조문은 재수집해도 같은 UUID 유지 → 외부 참조 안 끊김
    
    # 현재 수집된 조문의 internal_key 목록 (나중에 "사라진 조문" 감지용)
    current_keys = set()
    
    article_count = 0
    paragraph_count = 0
    item_count = 0
    preserved_count = 0  # UUID 유지된 조문 (기존 존재)
    new_article_count = 0  # 신규 조문
    
    for art in articles:
        ikey = art["article_internal_key"] or f"__auto_{art['article_no']}_{art['article_sub_no'] or 0}"
        current_keys.add(ikey)
        
        # 기존 조문 조회 (UUID 유지 여부 판단)
        existing = supabase.table("law_article") \
            .select("id") \
            .eq("law_id", law_id) \
            .eq("article_internal_key", ikey) \
            .execute()
        
        article_payload = {
            "law_id": law_id,
            "law_version_id": version_id,
            "article_internal_key": ikey,
            "article_no": art["article_no"],
            "article_sub_no": art["article_sub_no"],
            "article_no_sort": f"{str(art['article_no'] or 0).zfill(4)}-{str(art['article_sub_no'] or 0).zfill(3)}",
            "article_type": art["article_type"],
            "article_title": art["article_title"],
            "article_text": art["article_text"],
            "is_changed": art["is_changed"],
            "enforcement_date": str(art["enforcement_date"]) if art["enforcement_date"] else None,
            "article_status_code": "ACTIVE",
            "updated_at": serialize_business_datetime(now_kst()),
        }
        
        if existing.data:
            # UPDATE (UUID 유지)
            article_id = existing.data[0]["id"]
            supabase.table("law_article").update(article_payload).eq("id", article_id).execute()
            preserved_count += 1
        else:
            # INSERT (신규 조문)
            art_res = supabase.table("law_article").insert(article_payload).execute()
            article_id = art_res.data[0]["id"]
            new_article_count += 1
        
        article_count += 1
        
        # paragraph/item 재구성 (article 단위 delete + insert)
        # 하위 구조는 재파싱으로 동일 결과 생성되므로 UUID 영구 유지 불필요
        supabase.table("law_paragraph").delete().eq("article_id", article_id).execute()
        
        for p_idx, para in enumerate(art["paragraphs"]):
            para_internal_key = f"{ikey}-P{para['paragraph_no']}"
            
            para_res = supabase.table("law_paragraph").insert({
                "law_id": law_id,
                "article_id": article_id,
                "paragraph_internal_key": para_internal_key,
                "paragraph_no": para["paragraph_no"],
                "paragraph_no_sort": p_idx + 1,
                "paragraph_text": para["paragraph_text"],
                "paragraph_status_code": "ACTIVE",
                "updated_at": serialize_business_datetime(now_kst()),
            }).execute()
            paragraph_id = para_res.data[0]["id"]
            paragraph_count += 1
            
            for i_idx, item in enumerate(para["items"]):
                item_internal_key = f"{para_internal_key}-H{item['item_no']}"
                
                item_res = supabase.table("law_item").insert({
                    "law_id": law_id,
                    "paragraph_id": paragraph_id,
                    "item_internal_key": item_internal_key,
                    "item_level_code": "HO",
                    "item_no": item["item_no"],
                    "item_no_sort": i_idx + 1,
                    "item_text": item["item_text"],
                    "item_status_code": "ACTIVE",
                    "updated_at": serialize_business_datetime(now_kst()),
                }).execute()
                item_id = item_res.data[0]["id"]
                item_count += 1
                
                for s_idx, sub in enumerate(item["sub_items"]):
                    sub_internal_key = f"{item_internal_key}-M{sub['item_no']}"
                    
                    supabase.table("law_item").insert({
                        "law_id": law_id,
                        "paragraph_id": paragraph_id,
                        "parent_item_id": item_id,
                        "item_internal_key": sub_internal_key,
                        "item_level_code": "MOK",
                        "item_no": sub["item_no"],
                        "item_no_sort": s_idx + 1,
                        "item_text": sub["item_text"],
                        "item_status_code": "ACTIVE",
                        "updated_at": serialize_business_datetime(now_kst()),
                    }).execute()
                    item_count += 1
    
    # "사라진 조문" 감지: 이번 수집에 없는 기존 조문을 DELETED 상태로 표시
    # (물리 삭제 안 함 - 외부 참조 보존)
    deleted_count = 0
    if current_keys and not partial_merge:
        existing_all = supabase.table("law_article") \
            .select("id,article_internal_key") \
            .eq("law_id", law_id) \
            .execute()
        
        for existing_art in (existing_all.data or []):
            if existing_art["article_internal_key"] not in current_keys:
                supabase.table("law_article").update({
                    "article_status_code": "DELETED",
                    "updated_at": serialize_business_datetime(now_kst()),
                }).eq("id", existing_art["id"]).execute()
                deleted_count += 1
    
    return {
        "law_id": law_id,
        "version_id": version_id,
        "is_new_version": is_new_version,
        "article_count": article_count,
        "paragraph_count": paragraph_count,
        "item_count": item_count,
        "preserved_uuid_count": preserved_count,  # UUID 유지된 조문
        "new_article_count": new_article_count,    # 신규 조문
        "deleted_count": deleted_count,             # 삭제된 조문 (soft delete)
    }


# ═══════════════════════════════════════════════════════════
# 검증 체크리스트
# ═══════════════════════════════════════════════════════════

def verify_one_law(target: dict, save_result: dict, parsed: dict, supabase) -> dict:
    law_id = save_result["law_id"]
    article_count = save_result["article_count"]
    
    # ACTIVE 상태 조문만 검증 대상
    valid_query = supabase.table("law_article") \
        .select("id,article_text", count="exact") \
        .eq("law_id", law_id) \
        .eq("article_status_code", "ACTIVE") \
        .execute()
    
    total_articles = len(valid_query.data or [])
    valid_articles = sum(
        1 for a in (valid_query.data or [])
        if a.get("article_text") and len(a["article_text"]) > 20
    )
    valid_pct = round(valid_articles * 100.0 / total_articles, 1) if total_articles > 0 else 0.0
    
    expected = target.get("expected_article_count")
    if expected and expected > 0:
        article_count_reasonable = article_count >= (expected * 0.5)
    else:
        article_count_reasonable = article_count > 0
    
    checklist = {
        "api_call_success": True,
        "xml_saved": True,
        "parsing_success": True,
        "article_count": article_count,
        "paragraph_count": save_result.get("paragraph_count", 0),
        "item_count": save_result.get("item_count", 0),
        "preserved_uuid_count": save_result.get("preserved_uuid_count", 0),
        "new_article_count": save_result.get("new_article_count", 0),
        "deleted_count": save_result.get("deleted_count", 0),
        "valid_articles": valid_articles,
        "total_articles": total_articles,
        "valid_pct": valid_pct,
        "article_count_reasonable": article_count_reasonable,
        "valid_pct_above_30": valid_pct >= 30.0,
        "no_duplicate_created": True,
        "is_new_version": save_result.get("is_new_version", False),
        "is_admrul": _is_admrul(target),
        "checked_at": serialize_business_datetime(now_kst()),
    }
    
    required_checks = [
        "api_call_success",
        "xml_saved",
        "parsing_success",
        "article_count_reasonable",
    ]
    checklist["all_pass"] = all(checklist.get(k, False) for k in required_checks)
    checklist["valid_pct_warning"] = not checklist["valid_pct_above_30"]
    
    return checklist


# ═══════════════════════════════════════════════════════════
# 1개 법령 수집 유닛
# ═══════════════════════════════════════════════════════════

def collect_one_law(target: dict, supabase) -> dict:
    target_id = target["id"]
    law_name = target["law_name"]
    law_api_id = target.get("law_api_id")
    law_api_mst_no = target.get("law_api_mst_no")
    is_admrul = _is_admrul(target)
    
    result = {
        "target_id": target_id,
        "law_name": law_name,
        "status": "FAILED",
        "error": None,
        "checklist": {},
        "save_result": None,
        "started_at": serialize_business_datetime(now_kst()),
        "source_type": "admrul" if is_admrul else "law",
    }
    
    print(f"\n{'─' * 70}")
    print(f"🎯 {law_name}")
    print(f"   도메인: {target.get('domain_code')} | 유형: {target['law_type_code']} | "
          f"API: {'admrul' if is_admrul else 'law'}")
    print(f"   API_ID: {law_api_id or '(없음)'}")
    
    update_target_status(supabase, target_id, "IN_PROGRESS")
    
    try:
        if is_admrul:
            content_result, matched, parsed = _fetch_and_parse_admrul(
                target, law_name, law_api_id, law_api_mst_no
            )
        else:
            content_result, matched, parsed = _fetch_and_parse_law(
                target, law_name, law_api_id, law_api_mst_no
            )
        
        raw_xml = content_result["xml"]
        print(f"   ▶ XML 수신: {len(raw_xml):,} bytes")
        print(f"   ▶ 파싱: {len(parsed['articles'])}개 조문")
        
        result["checklist"]["api_call_success"] = True
        result["checklist"]["response_size"] = len(raw_xml)
        
        if not law_api_mst_no and matched.get("law_mst_no"):
            supabase.table("law_collection_target").update({
                "law_api_mst_no": matched["law_mst_no"],
                "law_api_id": matched.get("law_api_id") or law_api_id,
            }).eq("id", target_id).execute()
        
        law_info = {
            **parsed["info"],
            "law_mst_no": matched["law_mst_no"],
            "law_name_short": matched.get("law_name_short", ""),
            "revision_type": matched.get("revision_type", ""),
        }
        
        save_result = save_law_to_db(
            target, law_info, matched, raw_xml, parsed["articles"], supabase
        )
        result["save_result"] = save_result
        
        # 조문 중심 설계 효과 출력
        preserved = save_result.get("preserved_uuid_count", 0)
        new = save_result.get("new_article_count", 0)
        deleted = save_result.get("deleted_count", 0)
        print(f"   ▶ DB 저장: article={save_result['article_count']} "
              f"(UUID유지 {preserved}, 신규 {new}, 삭제 {deleted})")
        print(f"            paragraph={save_result['paragraph_count']}, item={save_result['item_count']}")
        
        checklist = verify_one_law(target, save_result, parsed, supabase)
        result["checklist"] = checklist
        
        if checklist["all_pass"]:
            result["status"] = "SUCCESS"
            update_target_status(supabase, target_id, "SUCCESS", checklist=checklist)
            print(f"   ✅ 성공 (valid_pct: {checklist['valid_pct']}%)")
        else:
            result["status"] = "FAILED"
            result["error"] = "검증 체크리스트 일부 실패"
            update_target_status(
                supabase, target_id, "FAILED",
                checklist=checklist, error=result["error"]
            )
            print(f"   ⚠️  검증 실패 (valid_pct: {checklist['valid_pct']}%)")
    
    except Exception as e:
        tb = traceback.format_exc()
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"
        result["error"] = error_msg
        result["checklist"]["error_trace"] = tb[:500]
        update_target_status(
            supabase, target_id, "FAILED",
            checklist=result["checklist"], error=error_msg
        )
        print(f"   ❌ 실패: {error_msg}")
    
    finally:
        result["completed_at"] = serialize_business_datetime(now_kst())
    
    return result


def _fetch_and_parse_law(target, law_name, law_api_id, law_api_mst_no):
    if law_api_mst_no:
        print(f"   ▶ MST 직접 조회: {law_api_mst_no}")
        content_result = fetch_law_content(law_api_mst_no)
        matched = {
            "law_mst_no": law_api_mst_no,
            "law_api_id": law_api_id,
            "law_name": law_name,
            "law_name_short": "",
            "revision_type": "",
        }
    else:
        print(f"   ▶ 이름 검색 (law)")
        list_result = fetch_law_list(query=law_name, display=15)
        if not list_result["ok"]:
            raise RuntimeError(f"검색 API 실패: HTTP {list_result['status']}")
        
        laws = parse_law_list_xml(list_result["xml"])
        if not laws:
            raise RuntimeError("검색 결과 없음")
        
        matched = next(
            (l for l in laws if (l.get("law_name") or "").strip() == law_name),
            None
        )
        if not matched:
            matched = next(
                (l for l in laws if law_name in (l.get("law_name") or "")),
                laws[0]
            )
        
        print(f"   ▶ 매칭: {matched['law_name']} | MST={matched['law_mst_no']}")
        content_result = fetch_law_content(matched["law_mst_no"])
    
    if not content_result["ok"]:
        raise RuntimeError(f"본문 API 실패: HTTP {content_result['status']}")
    if not content_result["xml"] or len(content_result["xml"]) < 100:
        raise RuntimeError(f"응답 너무 짧음: {len(content_result['xml'])} bytes")
    
    parsed = parse_law_content_xml(content_result["xml"])
    return content_result, matched, parsed


def _fetch_and_parse_admrul(target, law_name, law_api_id, law_api_mst_no):
    if law_api_id:
        print(f"   ▶ ID 직접 조회 (admrul): {law_api_id}")
        content_result = fetch_admrul_content(law_api_id)
        matched = {
            "law_mst_no": law_api_mst_no or law_api_id,
            "law_api_id": law_api_id,
            "law_name": law_name,
            "law_name_short": "",
            "revision_type": "",
        }
    else:
        print(f"   ▶ 이름 검색 (admrul)")
        list_result = fetch_admrul_list(query=law_name, display=15)
        if not list_result["ok"]:
            raise RuntimeError(f"admrul 검색 API 실패: HTTP {list_result['status']}")
        
        rules = parse_admrul_list_xml(list_result["xml"])
        if not rules:
            raise RuntimeError("admrul 검색 결과 없음")
        
        norm_target = law_name.replace(" ", "").replace("(", "").replace(")", "")
        matched = next(
            (r for r in rules if r.get("law_name", "").replace(" ", "").replace("(", "").replace(")", "") == norm_target),
            None
        )
        if not matched:
            for keyword in ("NFTC", "NFPC"):
                if keyword in law_name:
                    parts = law_name.split(keyword)
                    if len(parts) > 1:
                        num_part = parts[-1].replace(")", "").strip()
                        matched = next(
                            (r for r in rules if keyword in (r.get("law_name") or "") and num_part in (r.get("law_name") or "")),
                            None
                        )
                        if matched:
                            break
        if not matched:
            matched = rules[0]
        
        print(f"   ▶ 매칭: {matched['law_name']} | ID={matched['law_api_id']}")
        content_result = fetch_admrul_content(matched["law_api_id"])
    
    if not content_result["ok"]:
        raise RuntimeError(f"admrul 본문 API 실패: HTTP {content_result['status']}")
    if not content_result["xml"] or len(content_result["xml"]) < 100:
        raise RuntimeError(f"응답 너무 짧음: {len(content_result['xml'])} bytes")
    
    parsed = parse_admrul_content_xml(content_result["xml"])
    return content_result, matched, parsed


# ═══════════════════════════════════════════════════════════
# 명령 핸들러
# ═══════════════════════════════════════════════════════════

def cmd_test(law_name: str) -> int:
    supabase = get_supabase()
    print(f"\n{'=' * 70}\n🧪 단일 법령 수집 테스트\n{'=' * 70}")
    
    targets = get_targets(supabase, filter_type="name", value=law_name)
    if not targets:
        print(f"❌ 타겟 없음: {law_name}")
        return 1
    
    if len(targets) > 1:
        print(f"⚠️  {len(targets)}개 후보:")
        for t in targets[:10]:
            print(f"   - [{t['domain_code']}] {t['law_name']} ({t['law_type_code']})")
        print(f"\n첫 번째만 수집합니다: {targets[0]['law_name']}")
    
    target = targets[0]
    result = collect_one_law(target, supabase)
    
    print(f"\n{'=' * 70}\n📊 결과\n{'=' * 70}")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    
    return 0 if result["status"] == "SUCCESS" else 1


def cmd_all(rate_limit_sec: float = 0.5) -> int:
    supabase = get_supabase()
    print(f"\n{'=' * 70}\n🚀 전체 수집 시작\n{'=' * 70}")
    
    targets = get_targets(supabase, filter_type="pending")
    total = len(targets)
    
    if total == 0:
        print("✅ PENDING 상태 타겟이 없습니다.")
        return 0
    
    print(f"총 {total}개 타겟 수집 시작...\nRate limit: {rate_limit_sec}초/요청\n")
    
    success_count = 0
    fail_count = 0
    start_time = time.time()
    
    for idx, target in enumerate(targets, 1):
        print(f"\n[{idx}/{total}] ", end="")
        result = collect_one_law(target, supabase)
        
        if result["status"] == "SUCCESS":
            success_count += 1
        else:
            fail_count += 1
        
        elapsed = time.time() - start_time
        avg_time = elapsed / idx
        eta = avg_time * (total - idx)
        print(f"   📈 진행: {idx}/{total} ({idx*100/total:.1f}%) | "
              f"성공 {success_count} / 실패 {fail_count} | ETA {eta/60:.1f}분")
        
        if idx < total:
            time.sleep(rate_limit_sec)
    
    total_elapsed = time.time() - start_time
    print(f"\n{'=' * 70}\n🎉 전체 수집 완료\n{'=' * 70}")
    print(f"총 {total}개 중 성공 {success_count}, 실패 {fail_count}")
    print(f"소요 시간: {total_elapsed/60:.1f}분")
    
    return 0 if fail_count == 0 else 1


def cmd_retry(rate_limit_sec: float = 0.5) -> int:
    supabase = get_supabase()
    print(f"\n{'=' * 70}\n🔄 FAILED 재시도\n{'=' * 70}")
    
    failed_targets = get_targets(supabase, filter_type="failed")
    total = len(failed_targets)
    
    if total == 0:
        print("✅ FAILED 타겟이 없습니다.")
        return 0
    
    print(f"FAILED {total}개 재시도...\n")
    
    for t in failed_targets:
        supabase.table("law_collection_target").update({
            "collection_status": "PENDING",
            "updated_at": serialize_business_datetime(now_kst()),
        }).eq("id", t["id"]).execute()
    
    success_count = 0
    fail_count = 0
    
    for idx, target in enumerate(failed_targets, 1):
        print(f"\n[{idx}/{total}] ", end="")
        result = collect_one_law(target, supabase)
        if result["status"] == "SUCCESS":
            success_count += 1
        else:
            fail_count += 1
        if idx < total:
            time.sleep(rate_limit_sec)
    
    print(f"\n재시도 완료: 성공 {success_count}, 실패 {fail_count}")
    return 0 if fail_count == 0 else 1


def cmd_domain(domain_code: str, rate_limit_sec: float = 0.5) -> int:
    supabase = get_supabase()
    
    valid_domains = [
        "BUILDING", "CONSTRUCTION", "INDUSTRIAL_SAFETY", "FIRE", "GAS",
        "ELECTRIC", "CHEMICAL", "ENERGY", "ENVIRONMENT", "DISASTER", "LABOR"
    ]
    if domain_code not in valid_domains:
        print(f"❌ 유효한 도메인이 아닙니다: {domain_code}")
        print(f"   가능: {', '.join(valid_domains)}")
        return 1
    
    print(f"\n{'=' * 70}\n🎯 도메인 수집: {domain_code}\n{'=' * 70}")
    
    targets = get_targets(supabase, filter_type="domain", value=domain_code)
    pending = [t for t in targets if t["collection_status"] == "PENDING"]
    
    print(f"{domain_code}: 전체 {len(targets)}개 중 PENDING {len(pending)}개 수집\n")
    
    if not pending:
        print("✅ PENDING 타겟 없음")
        return 0
    
    success_count = 0
    fail_count = 0
    for idx, target in enumerate(pending, 1):
        print(f"\n[{idx}/{len(pending)}] ", end="")
        result = collect_one_law(target, supabase)
        if result["status"] == "SUCCESS":
            success_count += 1
        else:
            fail_count += 1
        if idx < len(pending):
            time.sleep(rate_limit_sec)
    
    print(f"\n{domain_code} 수집 완료: 성공 {success_count}, 실패 {fail_count}")
    return 0 if fail_count == 0 else 1


def cmd_monitor() -> int:
    supabase = get_supabase()
    print(f"\n{'=' * 70}\n📊 법령 수집 진행상황 ({now_kst().strftime('%H:%M:%S')})\n{'=' * 70}\n")
    
    all_targets = supabase.table("law_collection_target") \
        .select("collection_status,domain_code,added_in_phase,law_name,law_type_code,remarks") \
        .eq("is_active", True) \
        .execute()
    
    total = len(all_targets.data or [])
    if total == 0:
        print("❌ 타겟이 없습니다.")
        return 1
    
    by_status = {}
    for t in all_targets.data:
        s = t.get("collection_status", "UNKNOWN")
        by_status[s] = by_status.get(s, 0) + 1
    
    print("📈 상태별 현황:")
    for status in ["SUCCESS", "IN_PROGRESS", "PENDING", "FAILED", "SKIPPED"]:
        count = by_status.get(status, 0)
        pct = count * 100 / total if total > 0 else 0
        bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
        print(f"  {status:12} {count:4}/{total} ({pct:5.1f}%) {bar}")
    
    print(f"\n🏛️  도메인별 현황:")
    domain_stats = {}
    for t in all_targets.data:
        d = t.get("domain_code", "UNKNOWN")
        s = t.get("collection_status", "UNKNOWN")
        if d not in domain_stats:
            domain_stats[d] = {"total": 0, "SUCCESS": 0, "FAILED": 0, "PENDING": 0, "IN_PROGRESS": 0}
        domain_stats[d]["total"] += 1
        if s in domain_stats[d]:
            domain_stats[d][s] += 1
    
    print(f"  {'도메인':<20} {'전체':>5} {'성공':>5} {'실패':>5} {'대기':>5} {'진행':>5} {'성공률':>7}")
    print(f"  {'-' * 60}")
    for domain in sorted(domain_stats.keys()):
        s = domain_stats[domain]
        success_rate = (s["SUCCESS"] * 100 / s["total"]) if s["total"] > 0 else 0
        print(f"  {domain:<20} {s['total']:>5} {s['SUCCESS']:>5} {s['FAILED']:>5} "
              f"{s['PENDING']:>5} {s['IN_PROGRESS']:>5} {success_rate:>6.1f}%")
    
    failed = [t for t in all_targets.data if t.get("collection_status") == "FAILED"]
    if failed:
        print(f"\n❌ 실패 목록 (최대 10개):")
        for t in failed[:10]:
            remarks = (t.get("remarks") or "").split("|")[-1].strip()[:80]
            print(f"  - [{t['domain_code']}] {t['law_name']}")
            if remarks:
                print(f"    └─ {remarks}")
    
    print(f"\n📌 전체: {total} | 성공률: {by_status.get('SUCCESS', 0)*100/total:.1f}%")
    return 0


def print_usage():
    print(__doc__)


def main() -> int:
    if len(sys.argv) < 2:
        print_usage()
        return 1
    
    command = sys.argv[1].lower()
    
    if command == "test":
        if len(sys.argv) < 3:
            print("❌ 사용법: python3 scripts/collect_v2.py test \"법령명\"")
            return 1
        return cmd_test(sys.argv[2])
    elif command == "all":
        return cmd_all()
    elif command == "retry":
        return cmd_retry()
    elif command == "domain":
        if len(sys.argv) < 3:
            print("❌ 사용법: python3 scripts/collect_v2.py domain FIRE")
            return 1
        return cmd_domain(sys.argv[2].upper())
    elif command == "monitor":
        return cmd_monitor()
    elif command in ("help", "--help", "-h"):
        print_usage()
        return 0
    else:
        print(f"❌ 알 수 없는 명령: {command}")
        print_usage()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
