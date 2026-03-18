# routers/law_collector.py
# 법령 수집기 라우터
# - POST /law-collector/collect/all        전체 수집 (최초 1회)
# - POST /law-collector/collect/{law_name} 단건 수집
# - POST /law-collector/check-updates      변경 감지 (증분 수집)
# - GET  /law-collector/status             수집 상태 조회

import os
import hashlib
import requests
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from db.database import get_supabase

router = APIRouter(prefix="/law-collector", tags=["법령 수집기"])

# ============================================================
# 설정
# ============================================================

LAW_API_OC   = os.environ.get("LAW_API_OC")
LAW_API_BASE = "http://www.law.go.kr/DRF"


# ============================================================
# 유틸 함수
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
    if not text:
        return ""
    return text.strip()


def _safe_int(val: str) -> Optional[int]:
    try:
        return int(val.strip()) if val and val.strip() else None
    except:
        return None


def law_type_name_to_code(name: str) -> str:
    mapping = {
        "법률":     "LAW",
        "대통령령":  "ENFORCEMENT_DECREE",
        "총리령":   "ENFORCEMENT_RULE",
        "부령":     "ENFORCEMENT_RULE",
        "고시":     "NOTICE",
        "훈령":     "NOTICE",
        "예규":     "NOTICE",
        "기술기준": "STANDARD",
        "규정":     "STANDARD",
    }
    for key, code in mapping.items():
        if key in name:
            return code
    return "OTHER"


# ============================================================
# API 호출 함수 (requests 사용 - 동기)
# ============================================================

def fetch_law_content(mst_no: str) -> dict:
    """법령 본문 조회 API"""
    url = f"{LAW_API_BASE}/lawService.do"
    params = {
        "OC": LAW_API_OC,
        "target": "law",
        "MST": mst_no,
        "type": "XML",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=60)
    resp.encoding = "utf-8"
    resp.raise_for_status()
    return {"xml": resp.text, "status": resp.status_code}


def fetch_law_content(mst_no: str) -> dict:
    """법령 본문 조회 API (조문 포함)"""
    url = f"{LAW_API_BASE}/lawService.do"
    params = {
        "OC": LAW_API_OC,
        "target": "law",
        "MST": mst_no,
        "type": "XML",
    }
    resp = requests.get(url, params=params, timeout=60)
    resp.encoding = "utf-8"
    resp.raise_for_status()
    return {"xml": resp.text, "status": resp.status_code}


# ============================================================
# XML 파싱 함수
# ============================================================

def parse_law_list_xml(xml_text: str) -> list:
    """법령 목록 XML 파싱"""
    root = ET.fromstring(xml_text)
    laws = []
    for law in root.findall("law"):
        laws.append({
            "law_mst_no":        law.findtext("법령일련번호", ""),
            "law_api_id":        law.findtext("법령ID", ""),
            "law_name":          clean_cdata(law.findtext("법령명한글", "")),
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
    """법령 본문 XML 파싱 (기본정보 + 조문)"""
    root = ET.fromstring(xml_text)

    # 기본정보
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

    # 조문 파싱
    articles = []
    for jo in root.findall(".//조문단위"):
        article = {
            "article_internal_key": jo.get("조문키", ""),
            "article_no":           _safe_int(jo.findtext("조문번호", "")),
            "article_sub_no":       _safe_int(jo.findtext("조문가지번호", "")),
            "article_type":         jo.findtext("조문여부", ""),
            "article_title":        clean_cdata(jo.findtext("조문제목", "")),
            "article_text":         clean_cdata(jo.findtext("조문내용", "")),
            "enforcement_date":     parse_date(jo.findtext("조문시행일자", "")),
            "is_changed":           jo.findtext("조문변경여부", "N") == "Y",
            "paragraphs":           [],
        }

        # 항 파싱
        for hang in jo.findall("항"):
            paragraph = {
                "paragraph_no":   clean_cdata(hang.findtext("항번호", "")),
                "paragraph_text": clean_cdata(hang.findtext("항내용", "")),
                "items":          [],
            }

            # 호 파싱
            for ho in hang.findall("호"):
                item = {
                    "item_level_code": "HO",
                    "item_no":         clean_cdata(ho.findtext("호번호", "")),
                    "item_text":       clean_cdata(ho.findtext("호내용", "")),
                    "sub_items":       [],
                }

                # 목 파싱
                for mok in ho.findall("목"):
                    item["sub_items"].append({
                        "item_level_code": "MOK",
                        "item_no":         clean_cdata(mok.findtext("목번호", "")),
                        "item_text":       clean_cdata(mok.findtext("목내용", "")),
                    })

                paragraph["items"].append(item)

            article["paragraphs"].append(paragraph)

        articles.append(article)

    return {"info": info, "articles": articles, "raw_xml": xml_text}


# ============================================================
# DB 저장 함수
# ============================================================

def save_law_to_db(law_info: dict, raw_xml: str, articles: list, supabase) -> dict:
    """법령 전체를 DB에 저장"""

    law_mst_no    = law_info.get("law_mst_no", "")
    law_api_id    = law_info.get("law_api_id", "")
    law_name      = law_info.get("law_name", "")
    law_type_code = law_type_name_to_code(law_info.get("law_type_name", ""))
    raw_hash      = make_hash(raw_xml)
    version_no    = f"{law_info.get('announcement_date', '')}_{law_info.get('law_number', '')}"
    law_key       = f"{law_api_id}_{law_mst_no}"

    # 1) law_master upsert
    master_data = {
        "law_key":           law_key,
        "law_api_id":        law_api_id,
        "law_mst_no":        law_mst_no,
        "law_name":          law_name,
        "law_name_short":    law_info.get("law_name_short", ""),
        "law_type_code":     law_type_code,
        "ministry_code":     law_info.get("ministry_code", ""),
        "ministry_name":     law_info.get("ministry_name", ""),
        "law_number":        str(law_info.get("law_number", "")),
        "law_status_code":   "ACTIVE",
        "announcement_date": str(law_info.get("announcement_date")) if law_info.get("announcement_date") else None,
        "enforcement_date":  str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
        "source_system":     "law.go.kr",
        "is_active":         True,
        "updated_at":        datetime.now().isoformat(),
    }
    master_res = supabase.table("law_master").upsert(
        master_data, on_conflict="law_key"
    ).execute()
    law_id = master_res.data[0]["id"]

    # 2) law_version INSERT (중복 방지)
    existing_version = supabase.table("law_version")\
        .select("id")\
        .eq("law_id", law_id)\
        .eq("law_mst_no", law_mst_no)\
        .execute()

    if existing_version.data:
        version_id = existing_version.data[0]["id"]
        is_new_version = False
    else:
        version_data = {
            "law_id":              law_id,
            "version_no":          version_no,
            "law_mst_no":          law_mst_no,
            "revision_type_code":  law_info.get("revision_type", ""),
            "announcement_date":   str(law_info.get("announcement_date")) if law_info.get("announcement_date") else None,
            "enforcement_date":    str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
            "effective_from":      str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
            "is_current":          True,
            "version_status_code": "ACTIVE",
            "raw_hash":            raw_hash,
            "updated_at":          datetime.now().isoformat(),
        }
        version_res = supabase.table("law_version").insert(version_data).execute()
        version_id = version_res.data[0]["id"]
        is_new_version = True

        # 이전 버전 is_current = false 처리
        supabase.table("law_version")\
            .update({"is_current": False})\
            .eq("law_id", law_id)\
            .neq("id", version_id)\
            .execute()

        # law_master current_version_id 업데이트
        supabase.table("law_master")\
            .update({"current_version_id": version_id, "current_version_no": version_no})\
            .eq("id", law_id)\
            .execute()

    # 3) law_content_raw 저장
    if is_new_version:
        content_data = {
            "law_version_id":    version_id,
            "content_type_code": "XML",
            "raw_xml":           raw_xml,
            "text_hash":         raw_hash,
            "updated_at":        datetime.now().isoformat(),
        }
        supabase.table("law_content_raw").insert(content_data).execute()

    # 4) 조문 저장
    article_count = 0
    if is_new_version:
        for art in articles:
            article_data = {
                "law_version_id":       version_id,
                "article_internal_key": art["article_internal_key"],
                "article_no":           art["article_no"],
                "article_sub_no":       art["article_sub_no"],
                "article_no_sort":      f"{str(art['article_no'] or 0).zfill(4)}-{str(art['article_sub_no'] or 0).zfill(3)}",
                "article_type":         art["article_type"],
                "article_title":        art["article_title"],
                "article_text":         art["article_text"],
                "is_changed":           art["is_changed"],
                "enforcement_date":     str(art["enforcement_date"]) if art["enforcement_date"] else None,
                "article_status_code":  "ACTIVE",
                "updated_at":           datetime.now().isoformat(),
            }
            art_res = supabase.table("law_article").insert(article_data).execute()
            article_id = art_res.data[0]["id"]
            article_count += 1

            # 항 저장
            for p_idx, para in enumerate(art["paragraphs"]):
                para_data = {
                    "article_id":            article_id,
                    "paragraph_no":          para["paragraph_no"],
                    "paragraph_no_sort":     p_idx + 1,
                    "paragraph_text":        para["paragraph_text"],
                    "paragraph_status_code": "ACTIVE",
                    "updated_at":            datetime.now().isoformat(),
                }
                para_res = supabase.table("law_paragraph").insert(para_data).execute()
                paragraph_id = para_res.data[0]["id"]

                # 호 저장
                for i_idx, item in enumerate(para["items"]):
                    item_data = {
                        "paragraph_id":     paragraph_id,
                        "item_level_code":  "HO",
                        "item_no":          item["item_no"],
                        "item_no_sort":     i_idx + 1,
                        "item_text":        item["item_text"],
                        "item_status_code": "ACTIVE",
                        "updated_at":       datetime.now().isoformat(),
                    }
                    item_res = supabase.table("law_item").insert(item_data).execute()
                    item_id = item_res.data[0]["id"]

                    # 목 저장
                    for s_idx, sub in enumerate(item["sub_items"]):
                        sub_data = {
                            "paragraph_id":     paragraph_id,
                            "parent_item_id":   item_id,
                            "item_level_code":  "MOK",
                            "item_no":          sub["item_no"],
                            "item_no_sort":     s_idx + 1,
                            "item_text":        sub["item_text"],
                            "item_status_code": "ACTIVE",
                            "updated_at":       datetime.now().isoformat(),
                        }
                        supabase.table("law_item").insert(sub_data).execute()

    # 5) law_update_tracking upsert
    tracking_data = {
        "law_id":                    law_id,
        "last_checked_at":           datetime.now().isoformat(),
        "last_source_mst_no":        law_mst_no,
        "last_source_hash":          raw_hash,
        "last_collected_version_id": version_id,
        "update_needed":             False,
        "job_status_code":           "SUCCESS",
        "job_message":               f"수집완료 - 조문 {article_count}개",
        "updated_at":                datetime.now().isoformat(),
    }
    supabase.table("law_update_tracking").upsert(
        tracking_data, on_conflict="law_id"
    ).execute()

    return {
        "law_id":         law_id,
        "version_id":     version_id,
        "is_new_version": is_new_version,
        "article_count":  article_count,
    }


# ============================================================
# 변경 감지 함수
# ============================================================

def check_law_update(law_tracking: dict, supabase) -> dict:
    """단일 법령 변경 감지"""
    law_id      = law_tracking["law_id"]
    last_mst_no = law_tracking.get("last_source_mst_no", "")
    last_hash   = law_tracking.get("last_source_hash", "")

    master = supabase.table("law_master")\
        .select("law_name, law_api_id, law_mst_no")\
        .eq("id", law_id)\
        .single()\
        .execute()

    if not master.data:
        return {"changed": False, "reason": "법령 마스터 없음"}

    law_name = master.data["law_name"]

    list_result = fetch_law_list(query=law_name, display=5)
    laws = parse_law_list_xml(list_result["xml"])

    if not laws:
        return {"changed": False, "reason": "API 결과 없음"}

    current = laws[0]
    current_mst_no = current["law_mst_no"]

    if current_mst_no == last_mst_no:
        supabase.table("law_update_tracking")\
            .update({
                "last_checked_at": datetime.now().isoformat(),
                "update_needed":   False,
                "job_status_code": "SUCCESS",
                "job_message":     "변경 없음",
                "updated_at":      datetime.now().isoformat(),
            })\
            .eq("law_id", law_id)\
            .execute()
        return {"changed": False, "law_name": law_name}

    content_result = fetch_law_content(current_mst_no)
    parsed = parse_law_content_xml(content_result["xml"])
    new_hash = make_hash(content_result["xml"])

    if new_hash == last_hash:
        return {"changed": False, "law_name": law_name, "reason": "해시 동일"}

    old_version = supabase.table("law_version")\
        .select("id")\
        .eq("law_id", law_id)\
        .eq("is_current", True)\
        .execute()
    old_version_id = old_version.data[0]["id"] if old_version.data else None

    law_info = {**parsed["info"], "law_mst_no": current_mst_no}
    save_result = save_law_to_db(law_info, content_result["xml"], parsed["articles"], supabase)

    changed_article_count = sum(1 for a in parsed["articles"] if a.get("is_changed"))
    supabase.table("law_change_log").insert({
        "law_id":                law_id,
        "old_version_id":        old_version_id,
        "new_version_id":        save_result["version_id"],
        "change_detected_date":  datetime.now().isoformat(),
        "change_scope_code":     "FULL" if current.get("revision_type") == "전부개정" else "PARTIAL",
        "changed_article_count": changed_article_count,
        "change_summary":        f"{current.get('revision_type', '')} - {current_mst_no}",
        "processed_status_code": "DETECTED",
        "updated_at":            datetime.now().isoformat(),
    }).execute()

    supabase.table("law_update_tracking")\
        .update({
            "last_checked_at":           datetime.now().isoformat(),
            "last_source_mst_no":        current_mst_no,
            "last_source_hash":          new_hash,
            "last_collected_version_id": save_result["version_id"],
            "update_needed":             False,
            "job_status_code":           "SUCCESS",
            "job_message":               "변경 감지 및 수집 완료",
            "updated_at":                datetime.now().isoformat(),
        })\
        .eq("law_id", law_id)\
        .execute()

    return {
        "changed":    True,
        "law_name":   law_name,
        "old_mst_no": last_mst_no,
        "new_mst_no": current_mst_no,
        "articles":   save_result["article_count"],
    }


# ============================================================
# 라우터 엔드포인트
# ============================================================

@router.post("/collect/all")
async def collect_all_laws(background_tasks: BackgroundTasks):
    """전체 법령 수집 (최초 1회)"""
    background_tasks.add_task(_run_collect_all)
    return {
        "status":  "started",
        "message": "전체 법령 수집이 백그라운드에서 시작됐습니다. /law-collector/status 에서 확인하세요."
    }


def _run_collect_all():
    """전체 수집 백그라운드 작업"""
    supabase = get_supabase()
    targets = supabase.table("law_collection_target")\
        .select("*")\
        .eq("is_active", True)\
        .eq("collection_method", "API")\
        .order("collection_priority")\
        .execute()

    results = {"success": 0, "failed": 0, "skipped": 0, "errors": []}

    for target in targets.data:
        try:
            list_result = fetch_law_list(query=target["law_name"], display=5)
            laws = parse_law_list_xml(list_result["xml"])

            if not laws:
                results["skipped"] += 1
                continue

            matched = next(
                (l for l in laws if target["law_name"] in l["law_name"]),
                laws[0]
            )

            content_result = fetch_law_content(matched["law_mst_no"])
            parsed = parse_law_content_xml(content_result["xml"])

            law_info = {
                **parsed["info"],
                "law_mst_no":     matched["law_mst_no"],
                "law_name_short": matched.get("law_name_short", ""),
                "revision_type":  matched.get("revision_type", ""),
            }

            save_law_to_db(law_info, content_result["xml"], parsed["articles"], supabase)
            results["success"] += 1
            print(f"수집완료: {target['law_name']}")

        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"law_name": target["law_name"], "error": str(e)})
            print(f"수집실패: {target['law_name']} - {str(e)}")

    print(f"전체수집 완료: {results}")
    return results


@router.post("/collect/{law_name}")
async def collect_single_law(law_name: str):
    """단건 법령 수집"""
    supabase = get_supabase()
    try:
        list_result = fetch_law_list(query=law_name, display=5)
        laws = parse_law_list_xml(list_result["xml"])

        if not laws:
            raise HTTPException(status_code=404, detail=f"법령을 찾을 수 없습니다: {law_name}")

        matched = next(
            (l for l in laws if law_name in l["law_name"]),
            laws[0]
        )

        content_result = fetch_law_content(matched["law_mst_no"])
        parsed = parse_law_content_xml(content_result["xml"])

        law_info = {
            **parsed["info"],
            "law_mst_no":     matched["law_mst_no"],
            "law_name_short": matched.get("law_name_short", ""),
            "revision_type":  matched.get("revision_type", ""),
        }

        result = save_law_to_db(law_info, content_result["xml"], parsed["articles"], supabase)

        return {
            "status":         "success",
            "law_name":       matched["law_name"],
            "law_mst_no":     matched["law_mst_no"],
            "is_new_version": result["is_new_version"],
            "article_count":  result["article_count"],
        }

    except HTTPException:
        raise
    except Exception as e:
        error_detail = traceback.format_exc()
        print(f"ERROR: {error_detail}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-updates")
async def check_all_updates(background_tasks: BackgroundTasks):
    """전체 변경 감지 (증분 수집)"""
    background_tasks.add_task(_run_check_updates)
    return {
        "status":  "started",
        "message": "변경 감지가 백그라운드에서 시작됐습니다."
    }


def _run_check_updates():
    """변경 감지 백그라운드 작업"""
    supabase = get_supabase()
    trackings = supabase.table("law_update_tracking").select("*").execute()

    results = {"checked": 0, "changed": 0, "errors": []}

    for tracking in trackings.data:
        try:
            result = check_law_update(tracking, supabase)
            results["checked"] += 1
            if result.get("changed"):
                results["changed"] += 1
        except Exception as e:
            results["errors"].append({"law_id": tracking["law_id"], "error": str(e)})

    return results


@router.get("/status")
async def get_collection_status():
    """수집 상태 전체 조회"""
    supabase = get_supabase()

    total     = supabase.table("law_master").select("id", count="exact").execute()
    collected = supabase.table("law_update_tracking").select("id", count="exact").execute()
    changed   = supabase.table("law_change_log").select("id", count="exact").execute()
    pending   = supabase.table("law_parsing_result")\
        .select("id", count="exact")\
        .eq("parse_status_code", "PENDING")\
        .execute()

    failed = supabase.table("law_update_tracking")\
        .select("law_id, job_message, updated_at")\
        .eq("job_status_code", "FAILED")\
        .order("updated_at", desc=True)\
        .limit(10)\
        .execute()

    return {
        "collected_law_count":  total.count,
        "tracked_law_count":    collected.count,
        "change_log_count":     changed.count,
        "pending_parse_count":  pending.count,
        "recent_failed":        failed.data,
    }
