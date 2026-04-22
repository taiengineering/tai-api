#!/usr/bin/env python3
"""
법령 수집 v2 — 재수집 통합 스크립트

설계 문서: docs/LAW_COLLECTION_STORAGE_DESIGN_2026-04-22.md
타겟 테이블: law_collection_target_new (184개)
저장 테이블: law_master_new, law_version_new, law_content_raw_new,
            law_article_new, law_paragraph_new, law_item_new, law_attachment_new

핵심 설계:
  - 기존 routers/law_collector.py의 파싱 로직 재사용
  - _new 테이블에 저장 (기존 테이블 영향 없음)
  - 원본 XML 먼저 저장 (TX1) → 파싱 결과는 재파싱 가능
  - 파싱 결과는 cascade delete 후 재삽입 (TX2)
  - collection_status로 진행 추적 (재실행 가능)

사용법:
    cd ~/dev/tai-api
    set -a; source .env; set +a
    
    # 1. 단일 법령 테스트 (권장: 전체 실행 전)
    python3 scripts/collect_v2.py test "산업안전보건법"
    
    # 2. PENDING 상태 전체 수집 (실패 시 FAILED로 기록)
    python3 scripts/collect_v2.py all
    
    # 3. 실시간 모니터링 (다른 터미널에서)
    python3 scripts/collect_v2.py monitor
    
    # 4. FAILED만 재시도
    python3 scripts/collect_v2.py retry
    
    # 5. 특정 도메인만 수집
    python3 scripts/collect_v2.py domain BUILDING
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Optional

# ─── 루트 import 경로 ──────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.database import get_supabase
from routers.law_collector import (
    fetch_law_list,
    fetch_law_content,
    parse_law_list_xml,
    parse_law_content_xml,
    law_type_name_to_code,
    make_hash,
)


# ═══════════════════════════════════════════════════════════
# 유틸: 타겟 조회
# ═══════════════════════════════════════════════════════════

def get_targets(supabase, filter_type: str = "pending", value: str = None) -> list[dict]:
    """
    law_collection_target_new 에서 타겟 조회.
    
    Args:
        filter_type: 'pending' | 'all' | 'failed' | 'domain' | 'name'
        value: filter_type='domain'일 때 도메인 코드, 'name'일 때 법령명
    """
    query = supabase.table("law_collection_target_new") \
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
    # 'all'은 추가 필터 없음
    
    result = query.order("collection_priority") \
        .order("added_in_phase") \
        .order("law_name") \
        .execute()
    
    return result.data or []


# ═══════════════════════════════════════════════════════════
# 상태 업데이트 헬퍼
# ═══════════════════════════════════════════════════════════

def update_target_status(
    supabase, target_id: str, status: str,
    checklist: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    """law_collection_target_new 상태 업데이트."""
    update_data = {
        "collection_status": status,
        "updated_at": datetime.now().isoformat(),
    }
    
    if status in ("SUCCESS", "FAILED", "SKIPPED"):
        update_data["last_collected_at"] = datetime.now().isoformat()
    
    if checklist is not None:
        update_data["last_collection_result"] = json.dumps(checklist, ensure_ascii=False, default=str)
        update_data["verification_checklist"] = json.dumps(checklist, ensure_ascii=False, default=str)
    
    # error를 remarks에 append
    if error:
        target = supabase.table("law_collection_target_new") \
            .select("remarks").eq("id", target_id).single().execute()
        existing_remarks = (target.data.get("remarks") or "") if target.data else ""
        ts = datetime.now().strftime("%m-%d %H:%M")
        new_remarks = f"{existing_remarks} | [{ts}] {error[:200]}"
        update_data["remarks"] = new_remarks.strip(" |")
    
    supabase.table("law_collection_target_new") \
        .update(update_data) \
        .eq("id", target_id) \
        .execute()


# ═══════════════════════════════════════════════════════════
# 핵심: _new 테이블 저장 함수
# ═══════════════════════════════════════════════════════════

def save_law_to_new_db(
    target: dict,
    law_info: dict,
    matched: dict,
    raw_xml: str,
    articles: list,
    supabase: Any,
) -> dict:
    """
    법령을 _new 테이블에 저장.
    
    저장 전략:
      TX1: law_master_new + law_version_new + law_content_raw_new
      TX2: law_article_new + law_paragraph_new + law_item_new
           (기존 version의 article들 cascade delete 후 재삽입)
    
    Returns:
      {law_id, version_id, is_new_version, article_count, paragraph_count, item_count}
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
    
    # ─── TX1-1: law_master_new UPSERT ──────────────────────
    master_res = supabase.table("law_master_new").upsert({
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
        "source_system": "data.go.kr/law" if os.environ.get("DATA_GOV_SERVICE_KEY") else "law.go.kr",
        "is_active": True,
        "updated_at": datetime.now().isoformat(),
    }, on_conflict="law_key").execute()
    
    if not master_res.data:
        raise RuntimeError("law_master_new upsert 실패")
    law_id = master_res.data[0]["id"]
    
    # ─── TX1-2: law_version_new UPSERT ─────────────────────
    # 기존 버전 확인
    existing_version = supabase.table("law_version_new") \
        .select("id") \
        .eq("law_id", law_id) \
        .eq("version_no", version_no) \
        .execute()
    
    if existing_version.data:
        version_id = existing_version.data[0]["id"]
        # 업데이트
        supabase.table("law_version_new").update({
            "law_mst_no": law_mst_no,
            "revision_type_code": matched.get("revision_type", "") or law_info.get("revision_type", ""),
            "announcement_date": str(law_info.get("announcement_date")) if law_info.get("announcement_date") else None,
            "enforcement_date": str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
            "effective_from": str(law_info.get("enforcement_date")) if law_info.get("enforcement_date") else None,
            "is_current": True,
            "version_status_code": "ACTIVE",
            "raw_hash": raw_hash,
            "updated_at": datetime.now().isoformat(),
        }).eq("id", version_id).execute()
        is_new_version = False
    else:
        version_res = supabase.table("law_version_new").insert({
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
            "updated_at": datetime.now().isoformat(),
        }).execute()
        version_id = version_res.data[0]["id"]
        is_new_version = True
    
    # is_current 다른 버전 false 처리
    if is_new_version:
        supabase.table("law_version_new") \
            .update({"is_current": False}) \
            .eq("law_id", law_id) \
            .neq("id", version_id) \
            .execute()
    
    # law_master_new.current_version_id 업데이트
    supabase.table("law_master_new").update({
        "current_version_id": version_id,
        "current_version_no": version_no,
        "updated_at": datetime.now().isoformat(),
    }).eq("id", law_id).execute()
    
    # ─── TX1-3: law_content_raw_new (원본 XML) ──────────────
    # 기존 원본 삭제 후 재삽입 (UNIQUE: law_version_id)
    supabase.table("law_content_raw_new").delete().eq("law_version_id", version_id).execute()
    supabase.table("law_content_raw_new").insert({
        "law_version_id": version_id,
        "content_type_code": "XML",
        "raw_xml": raw_xml,
        "text_hash": raw_hash,
        "updated_at": datetime.now().isoformat(),
    }).execute()
    
    # ─── TX2: 기존 article cascade delete + 새 파싱 결과 삽입 ──
    # CASCADE FK로 paragraph/item도 자동 삭제됨
    supabase.table("law_article_new").delete().eq("law_version_id", version_id).execute()
    
    article_count = 0
    paragraph_count = 0
    item_count = 0
    
    for art in articles:
        art_res = supabase.table("law_article_new").insert({
            "law_version_id": version_id,
            "article_internal_key": art["article_internal_key"],
            "article_no": art["article_no"],
            "article_sub_no": art["article_sub_no"],
            "article_no_sort": f"{str(art['article_no'] or 0).zfill(4)}-{str(art['article_sub_no'] or 0).zfill(3)}",
            "article_type": art["article_type"],
            "article_title": art["article_title"],
            "article_text": art["article_text"],
            "is_changed": art["is_changed"],
            "enforcement_date": str(art["enforcement_date"]) if art["enforcement_date"] else None,
            "article_status_code": "ACTIVE",
            "updated_at": datetime.now().isoformat(),
        }).execute()
        article_id = art_res.data[0]["id"]
        article_count += 1
        
        for p_idx, para in enumerate(art["paragraphs"]):
            # paragraph_internal_key 생성 (기존 파서가 안 주므로)
            para_internal_key = f"{art['article_internal_key']}-P{para['paragraph_no']}" if art['article_internal_key'] else ""
            
            para_res = supabase.table("law_paragraph_new").insert({
                "article_id": article_id,
                "paragraph_internal_key": para_internal_key,
                "paragraph_no": para["paragraph_no"],
                "paragraph_no_sort": p_idx + 1,
                "paragraph_text": para["paragraph_text"],
                "paragraph_status_code": "ACTIVE",
                "updated_at": datetime.now().isoformat(),
            }).execute()
            paragraph_id = para_res.data[0]["id"]
            paragraph_count += 1
            
            for i_idx, item in enumerate(para["items"]):
                # item_internal_key 생성
                item_internal_key = f"{para_internal_key}-H{item['item_no']}" if para_internal_key else ""
                
                item_res = supabase.table("law_item_new").insert({
                    "paragraph_id": paragraph_id,
                    "item_internal_key": item_internal_key,
                    "item_level_code": "HO",
                    "item_no": item["item_no"],
                    "item_no_sort": i_idx + 1,
                    "item_text": item["item_text"],
                    "item_status_code": "ACTIVE",
                    "updated_at": datetime.now().isoformat(),
                }).execute()
                item_id = item_res.data[0]["id"]
                item_count += 1
                
                for s_idx, sub in enumerate(item["sub_items"]):
                    sub_internal_key = f"{item_internal_key}-M{sub['item_no']}" if item_internal_key else ""
                    
                    supabase.table("law_item_new").insert({
                        "paragraph_id": paragraph_id,
                        "parent_item_id": item_id,
                        "item_internal_key": sub_internal_key,
                        "item_level_code": "MOK",
                        "item_no": sub["item_no"],
                        "item_no_sort": s_idx + 1,
                        "item_text": sub["item_text"],
                        "item_status_code": "ACTIVE",
                        "updated_at": datetime.now().isoformat(),
                    }).execute()
                    item_count += 1
    
    return {
        "law_id": law_id,
        "version_id": version_id,
        "is_new_version": is_new_version,
        "article_count": article_count,
        "paragraph_count": paragraph_count,
        "item_count": item_count,
    }


# ═══════════════════════════════════════════════════════════
# 유닛 검증 체크리스트
# ═══════════════════════════════════════════════════════════

def verify_one_law(target: dict, save_result: dict, parsed: dict, supabase) -> dict:
    """
    수집된 법령의 품질 검증.
    
    Returns:
      체크리스트 dict (JSONB 저장용)
    """
    version_id = save_result["version_id"]
    article_count = save_result["article_count"]
    
    # valid_pct 계산: article_text 길이 20자 이상인 비율
    valid_query = supabase.table("law_article_new") \
        .select("id,article_text", count="exact") \
        .eq("law_version_id", version_id) \
        .execute()
    
    total_articles = len(valid_query.data or [])
    valid_articles = sum(
        1 for a in (valid_query.data or [])
        if a.get("article_text") and len(a["article_text"]) > 20
    )
    valid_pct = round(valid_articles * 100.0 / total_articles, 1) if total_articles > 0 else 0.0
    
    # expected_article_count와 비교 (있으면)
    expected = target.get("expected_article_count")
    if expected and expected > 0:
        article_count_reasonable = article_count >= (expected * 0.5)
    else:
        # 최소 1개 이상
        article_count_reasonable = article_count > 0
    
    checklist = {
        "api_call_success": True,
        "xml_saved": True,
        "parsing_success": True,
        "article_count": article_count,
        "paragraph_count": save_result.get("paragraph_count", 0),
        "item_count": save_result.get("item_count", 0),
        "valid_articles": valid_articles,
        "total_articles": total_articles,
        "valid_pct": valid_pct,
        "article_count_reasonable": article_count_reasonable,
        "valid_pct_above_30": valid_pct >= 30.0,
        "no_duplicate_created": True,  # UPSERT 사용 = 중복 불가
        "is_new_version": save_result.get("is_new_version", False),
        "checked_at": datetime.now().isoformat(),
    }
    
    # 전체 통과 여부
    required_checks = [
        "api_call_success",
        "xml_saved",
        "parsing_success",
        "article_count_reasonable",
    ]
    checklist["all_pass"] = all(checklist.get(k, False) for k in required_checks)
    # valid_pct_above_30은 경고 수준 (실패로 안 치지만 기록은 함)
    checklist["valid_pct_warning"] = not checklist["valid_pct_above_30"]
    
    return checklist


# ═══════════════════════════════════════════════════════════
# 핵심: 1개 법령 수집 (유닛)
# ═══════════════════════════════════════════════════════════

def collect_one_law(target: dict, supabase) -> dict:
    """
    1개 법령 수집 — 완전한 유닛.
    
    흐름:
      1. 상태 PENDING → IN_PROGRESS
      2. API 호출 (search → content)
      3. TX1: 원본 XML 저장 (law_master_new + law_version_new + law_content_raw_new)
      4. TX2: 파싱 결과 저장 (article + paragraph + item)
      5. 검증 체크리스트
      6. 상태 SUCCESS/FAILED 업데이트
    
    Returns:
      {target_id, law_name, status, error, checklist, save_result}
    """
    target_id = target["id"]
    law_name = target["law_name"]
    law_api_id = target.get("law_api_id")
    law_api_mst_no = target.get("law_api_mst_no")
    
    result = {
        "target_id": target_id,
        "law_name": law_name,
        "status": "FAILED",
        "error": None,
        "checklist": {},
        "save_result": None,
        "started_at": datetime.now().isoformat(),
    }
    
    print(f"\n{'─' * 70}")
    print(f"🎯 {law_name}")
    print(f"   도메인: {target.get('domain_code')} | 유형: {target['law_type_code']}")
    print(f"   API_ID: {law_api_id or '(없음, 검색 필요)'}")
    
    # Step 0: IN_PROGRESS
    update_target_status(supabase, target_id, "IN_PROGRESS")
    
    try:
        # Step 1: API 호출
        #   - law_api_mst_no가 있으면 직접 본문 API
        #   - 없으면 검색 API부터 (이름 기반)
        
        if law_api_mst_no:
            # 마스터번호 있으면 바로 본문 조회
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
            # 이름으로 검색 → 매칭 → 본문
            print(f"   ▶ 이름 검색")
            list_result = fetch_law_list(query=law_name, display=15)
            if not list_result["ok"]:
                raise RuntimeError(f"검색 API 실패: HTTP {list_result['status']}")
            
            laws = parse_law_list_xml(list_result["xml"])
            if not laws:
                raise RuntimeError("검색 결과 없음")
            
            # 정확 매칭 우선
            matched = next(
                (l for l in laws if (l.get("law_name") or "").strip() == law_name),
                None
            )
            if not matched:
                # 부분 매칭
                matched = next(
                    (l for l in laws if law_name in (l.get("law_name") or "")),
                    laws[0]
                )
            
            print(f"   ▶ 매칭: {matched['law_name']} | MST={matched['law_mst_no']}")
            
            content_result = fetch_law_content(matched["law_mst_no"])
        
        if not content_result["ok"]:
            raise RuntimeError(f"본문 API 실패: HTTP {content_result['status']}")
        
        raw_xml = content_result["xml"]
        if not raw_xml or len(raw_xml) < 100:
            raise RuntimeError(f"응답 너무 짧음: {len(raw_xml)} bytes")
        
        print(f"   ▶ XML 수신: {len(raw_xml):,} bytes")
        result["checklist"]["api_call_success"] = True
        result["checklist"]["response_size"] = len(raw_xml)
        
        # Step 2: 파싱
        parsed = parse_law_content_xml(raw_xml)
        print(f"   ▶ 파싱: {len(parsed['articles'])}개 조문")
        
        # law_api_mst_no가 비어있으면 검색 결과에서 가져온 것으로 업데이트
        if not law_api_mst_no and matched.get("law_mst_no"):
            supabase.table("law_collection_target_new").update({
                "law_api_mst_no": matched["law_mst_no"],
                "law_api_id": matched.get("law_api_id") or law_api_id,
            }).eq("id", target_id).execute()
        
        # Step 3: _new 테이블 저장
        law_info = {
            **parsed["info"],
            "law_mst_no": matched["law_mst_no"],
            "law_name_short": matched.get("law_name_short", ""),
            "revision_type": matched.get("revision_type", ""),
        }
        
        save_result = save_law_to_new_db(
            target, law_info, matched, raw_xml, parsed["articles"], supabase
        )
        result["save_result"] = save_result
        
        print(f"   ▶ DB 저장: article={save_result['article_count']}, "
              f"paragraph={save_result['paragraph_count']}, item={save_result['item_count']}")
        
        # Step 4: 검증 체크리스트
        checklist = verify_one_law(target, save_result, parsed, supabase)
        result["checklist"] = checklist
        
        # Step 5: 상태 업데이트
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
        result["completed_at"] = datetime.now().isoformat()
    
    return result


# ═══════════════════════════════════════════════════════════
# 명령 핸들러: test (단일 수집 테스트)
# ═══════════════════════════════════════════════════════════

def cmd_test(law_name: str) -> int:
    """단일 법령 수집 테스트. 전체 실행 전 검증용."""
    supabase = get_supabase()
    
    print(f"\n{'=' * 70}")
    print(f"🧪 단일 법령 수집 테스트")
    print(f"{'=' * 70}")
    
    targets = get_targets(supabase, filter_type="name", value=law_name)
    if not targets:
        print(f"❌ 타겟 없음: {law_name}")
        print(f"   law_collection_target_new에 {law_name}을 포함하는 법령이 없습니다.")
        return 1
    
    if len(targets) > 1:
        print(f"⚠️  {len(targets)}개 후보:")
        for t in targets[:10]:
            print(f"   - [{t['domain_code']}] {t['law_name']} ({t['law_type_code']})")
        print(f"\n첫 번째만 수집합니다: {targets[0]['law_name']}")
    
    target = targets[0]
    result = collect_one_law(target, supabase)
    
    print(f"\n{'=' * 70}")
    print(f"📊 결과")
    print(f"{'=' * 70}")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    
    return 0 if result["status"] == "SUCCESS" else 1


# ═══════════════════════════════════════════════════════════
# 명령 핸들러: all (PENDING 전체 수집)
# ═══════════════════════════════════════════════════════════

def cmd_all(rate_limit_sec: float = 0.5) -> int:
    """PENDING 상태 전체 수집. rate_limit_sec 초 대기."""
    supabase = get_supabase()
    
    print(f"\n{'=' * 70}")
    print(f"🚀 전체 수집 시작")
    print(f"{'=' * 70}")
    
    targets = get_targets(supabase, filter_type="pending")
    total = len(targets)
    
    if total == 0:
        print("✅ PENDING 상태 타겟이 없습니다. (이미 전부 수집됨)")
        print("\n재시도하려면: python3 scripts/collect_v2.py retry")
        return 0
    
    print(f"총 {total}개 타겟 수집 시작...")
    print(f"Rate limit: {rate_limit_sec}초/요청")
    print(f"예상 시간: 약 {total * (3 + rate_limit_sec) / 60:.1f}분\n")
    
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
        
        # 진행률 표시
        elapsed = time.time() - start_time
        avg_time = elapsed / idx
        eta = avg_time * (total - idx)
        print(f"   📈 진행: {idx}/{total} ({idx*100/total:.1f}%) | "
              f"성공 {success_count} / 실패 {fail_count} | "
              f"ETA {eta/60:.1f}분")
        
        # Rate limit
        if idx < total:
            time.sleep(rate_limit_sec)
    
    total_elapsed = time.time() - start_time
    
    print(f"\n{'=' * 70}")
    print(f"🎉 전체 수집 완료")
    print(f"{'=' * 70}")
    print(f"총 {total}개 중 성공 {success_count}, 실패 {fail_count}")
    print(f"소요 시간: {total_elapsed/60:.1f}분")
    print(f"\n실패 목록 확인: python3 scripts/collect_v2.py monitor")
    print(f"재시도: python3 scripts/collect_v2.py retry")
    
    return 0 if fail_count == 0 else 1


# ═══════════════════════════════════════════════════════════
# 명령 핸들러: retry (FAILED 재시도)
# ═══════════════════════════════════════════════════════════

def cmd_retry(rate_limit_sec: float = 0.5) -> int:
    """FAILED 상태 타겟만 재시도."""
    supabase = get_supabase()
    
    print(f"\n{'=' * 70}")
    print(f"🔄 FAILED 재시도")
    print(f"{'=' * 70}")
    
    failed_targets = get_targets(supabase, filter_type="failed")
    total = len(failed_targets)
    
    if total == 0:
        print("✅ FAILED 타겟이 없습니다.")
        return 0
    
    print(f"FAILED {total}개 재시도...\n")
    
    # FAILED를 PENDING으로 리셋
    for t in failed_targets:
        supabase.table("law_collection_target_new").update({
            "collection_status": "PENDING",
            "updated_at": datetime.now().isoformat(),
        }).eq("id", t["id"]).execute()
    
    # all과 동일하게 진행
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


# ═══════════════════════════════════════════════════════════
# 명령 핸들러: domain (특정 도메인만)
# ═══════════════════════════════════════════════════════════

def cmd_domain(domain_code: str, rate_limit_sec: float = 0.5) -> int:
    """특정 도메인 타겟만 수집 (PENDING 상태만)."""
    supabase = get_supabase()
    
    valid_domains = [
        "BUILDING", "CONSTRUCTION", "INDUSTRIAL_SAFETY", "FIRE", "GAS",
        "ELECTRIC", "CHEMICAL", "ENERGY", "ENVIRONMENT", "DISASTER", "LABOR"
    ]
    if domain_code not in valid_domains:
        print(f"❌ 유효한 도메인이 아닙니다: {domain_code}")
        print(f"   가능: {', '.join(valid_domains)}")
        return 1
    
    print(f"\n{'=' * 70}")
    print(f"🎯 도메인 수집: {domain_code}")
    print(f"{'=' * 70}")
    
    targets = get_targets(supabase, filter_type="domain", value=domain_code)
    total = len(targets)
    
    if total == 0:
        print(f"✅ {domain_code} 도메인에 타겟이 없습니다.")
        return 0
    
    # PENDING만 필터
    pending = [t for t in targets if t["collection_status"] == "PENDING"]
    print(f"{domain_code}: 전체 {total}개 중 PENDING {len(pending)}개 수집\n")
    
    if not pending:
        print("✅ PENDING 타겟 없음 (전부 이미 수집됨)")
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


# ═══════════════════════════════════════════════════════════
# 명령 핸들러: monitor (진행상황 확인)
# ═══════════════════════════════════════════════════════════

def cmd_monitor() -> int:
    """전체 수집 진행상황 모니터링."""
    supabase = get_supabase()
    
    print(f"\n{'=' * 70}")
    print(f"📊 법령 수집 진행상황 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"{'=' * 70}\n")
    
    # 전체 통계
    all_targets = supabase.table("law_collection_target_new") \
        .select("collection_status,domain_code,added_in_phase,law_name,remarks") \
        .eq("is_active", True) \
        .execute()
    
    total = len(all_targets.data or [])
    if total == 0:
        print("❌ 타겟이 없습니다. law_collection_target_new 확인 필요")
        return 1
    
    # 상태별 집계
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
    
    # 도메인별 현황
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
    
    # 최근 FAILED 10개
    failed = [t for t in all_targets.data if t.get("collection_status") == "FAILED"]
    if failed:
        print(f"\n❌ 최근 실패 목록 (최대 10개):")
        for t in failed[:10]:
            remarks = (t.get("remarks") or "").split("|")[-1].strip()[:80]
            print(f"  - [{t['domain_code']}] {t['law_name']}")
            if remarks:
                print(f"    └─ {remarks}")
    
    # 통계 요약
    print(f"\n📌 전체: {total} | 성공률: {by_status.get('SUCCESS', 0)*100/total:.1f}%")
    
    return 0


# ═══════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════

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
            print("❌ 사용법: python3 scripts/collect_v2.py domain BUILDING")
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
