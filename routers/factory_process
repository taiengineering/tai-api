# routers/factory_process.py
# 시설 → 공정 → 설비 연결 API
# - GET  /factory-process/{factory_id}/processes      시설의 공정 목록 조회
# - POST /factory-process/{factory_id}/processes      공정 선택 저장
# - DELETE /factory-process/{factory_id}/processes/{process_id}  공정 삭제
# - GET  /factory-process/{factory_id}/recommend-processes  KSIC 기반 공정 추천
# - GET  /factory-process/{factory_id}/recommend-equipment  선택된 공정 기반 설비 추천
# - POST /factory-process/{factory_id}/register-equipment   추천 설비 일괄 등록

from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

router = APIRouter(tags=["factory_process"])

# ============================================================
# 요청 모델
# ============================================================

class ProcessSelectRequest(BaseModel):
    process_ids: List[str]          # 선택한 process_id 목록
    is_primary: Optional[bool] = False

class EquipmentRegisterRequest(BaseModel):
    facility_names: List[str]       # 등록할 설비 표준명 목록
    process_id: Optional[str] = None


# ============================================================
# facility_name_std → equipment_type_code 매핑
# ============================================================

FACILITY_TO_EQUIPMENT_TYPE = {
    "변압기":"001","수변전반":"001","수배전반":"006","배전반":"006",
    "분전반":"007","전동기":"008","모터":"008","UPS":"009",
    "무정전전원장치":"009","비상발전기":"010","발전기":"010",
    "차단기":"002","기중차단기":"002","진공차단기":"003",
    "배선용차단기":"004","누전차단기":"005",
    "펌프":"011","압축기":"012","컴프레서":"012","열교환기":"013",
    "보일러":"014","증기보일러":"014","온수보일러":"014",
    "탱크":"015","저장탱크":"015","밸브":"016","배관":"017",
    "팬":"018","송풍기":"018","냉동기":"019","냉장기":"019","칠러":"020",
    "크레인":"021","천장크레인":"021","이동식크레인":"021",
    "호이스트":"022","프레스":"023","유압프레스":"023",
    "컨베이어":"024","컨베이어벨트":"024",
    "승강기":"025","엘리베이터":"025","에스컬레이터":"026",
    "가스탱크":"027","고압가스탱크":"027","LPG탱크":"028",
    "화학물질탱크":"029","유류탱크":"030","경유탱크":"030",
    "스프링클러":"031","자동화재탐지":"032","화재감지기":"032",
    "소화기":"033","소화전":"034","옥내소화전":"034",
    "배기시설":"035","집진기":"036","집진장치":"036",
    "오수처리시설":"037","하수처리시설":"037","압력용기":"038",
    "냉동냉각기":"039","냉각탑":"039","공조기":"039",
    "프레스설비":"023","절단기":"023","절곡기":"023",
    "노칭기":"023","슬리터":"023","권취기":"023","적층기":"023","실링설비":"023",
    "물류자동화설비":"024","물류설비":"024",
    "건조설비":"014","건조기":"014","가열설비":"014","에이징 설비":"014",
    "제품저장탱크":"015","버퍼탱크":"015","혼합탱크":"015","원료저장탱크":"015",
    "위험물 옥외탱크저장소":"015","고압가스 저장탱크":"027",
    "고압가스 저장시설":"027","산업용배관망":"017","위험물 이송배관":"017",
    "위험물 밸브":"016","공정펌프":"011","이송펌프":"011","급수펌프":"011",
    "공정압축기":"012","압축공기공급설비":"012",
    "접지설비":"001","전력계측장치":"001","전력감시장치":"001",
    "가스감지설비":"032","화재감지설비":"032","가스누출감지기":"032",
    "위험물 방유제":"030","연료저장탱크":"030",
    "위험물 이송설비":"029","위험물 간이저장소":"029",
    "도장부스":"036","흡입설비":"036","국소배기장치":"036",
    "산업용배수설비":"037","폐수처리설비":"037",
    "냉각수공급설비":"039","공정압축기":"012",
    "산업용로봇":"023","사출성형기":"023","분쇄설비":"012",
    "혼합설비":"011","교반기":"011","원심분리기":"011",
    "반응기":"015","증류탑":"015","흡수탑":"015",
    "생산라인설비":"024","전극 코팅기":"023","전극 압연기":"023",
    "용접전원장치":"008","산업안전설비":"034",
}

def get_equipment_type(facility_name: str) -> Optional[str]:
    if not facility_name:
        return None
    if facility_name in FACILITY_TO_EQUIPMENT_TYPE:
        return FACILITY_TO_EQUIPMENT_TYPE[facility_name]
    for key, code in FACILITY_TO_EQUIPMENT_TYPE.items():
        if key in facility_name or facility_name in key:
            return code
    return None


# ============================================================
# 1. 시설의 등록된 공정 목록 조회
# ============================================================

@router.get("/{factory_id}/processes")
def get_factory_processes(factory_id: str):
    """시설에 등록된 공정 목록 조회"""
    supabase = get_supabase()

    procs = supabase.table("factory_process")\
        .select("*")\
        .eq("factory_id", factory_id)\
        .eq("is_active", True)\
        .order("is_primary", desc=True)\
        .execute()

    return {
        "status": "success",
        "factory_id": factory_id,
        "count": len(procs.data or []),
        "data": procs.data or [],
    }


# ============================================================
# 2. KSIC 기반 공정 추천 (선택 전 미리보기)
# ============================================================

@router.get("/{factory_id}/recommend-processes")
def recommend_processes(factory_id: str, limit: int = 20):
    """KSIC 코드 기반 공정 추천 목록 반환"""
    supabase = get_supabase()

    # factory 조회
    factory_res = supabase.table("factories")\
        .select("id, name, ksic_code, ksic_name")\
        .eq("id", factory_id)\
        .single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    factory = factory_res.data
    ksic_code = factory.get("ksic_code")

    if not ksic_code:
        return {
            "status": "warning",
            "message": "KSIC 코드가 등록되지 않았습니다",
            "data": []
        }

    # ksic_process_map에서 공정 목록 조회
    proc_res = supabase.table("ksic_process_map")\
        .select("process_id, process_lv1, process_lv2, process_lv3, process_lv4, process_path")\
        .eq("industry_code_full", ksic_code)\
        .limit(limit).execute()

    # 3자리 코드로 재시도
    if not proc_res.data:
        proc_res = supabase.table("ksic_process_map")\
            .select("process_id, process_lv1, process_lv2, process_lv3, process_lv4, process_path")\
            .like("industry_code_full", f"{ksic_code[:3]}%")\
            .limit(limit).execute()

    # 중복 process_id 제거
    seen = {}
    for p in proc_res.data or []:
        pid = p.get("process_id")
        if pid and pid not in seen:
            seen[pid] = p

    processes = list(seen.values())

    # 이미 등록된 공정 표시
    existing_res = supabase.table("factory_process")\
        .select("process_id")\
        .eq("factory_id", factory_id)\
        .eq("is_active", True)\
        .execute()
    existing_ids = {e["process_id"] for e in (existing_res.data or [])}

    for p in processes:
        p["is_registered"] = p.get("process_id") in existing_ids

    return {
        "status": "success",
        "factory_id": factory_id,
        "factory_name": factory.get("name"),
        "ksic_code": ksic_code,
        "ksic_name": factory.get("ksic_name"),
        "count": len(processes),
        "data": processes,
    }


# ============================================================
# 3. 공정 선택 저장
# ============================================================

@router.post("/{factory_id}/processes")
def select_processes(factory_id: str, req: ProcessSelectRequest):
    """공정 선택 저장 — process_id 목록을 factory_process에 등록"""
    supabase = get_supabase()

    # factory 존재 확인
    factory_res = supabase.table("factories")\
        .select("id, name, ksic_code")\
        .eq("id", factory_id)\
        .single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    # 공정 상세 정보 조회
    proc_res = supabase.table("ksic_process_map")\
        .select("process_id, process_lv1, process_lv2, process_lv3, process_lv4, process_path")\
        .in_("process_id", req.process_ids)\
        .execute()

    # 중복 process_id 제거
    proc_map = {}
    for p in proc_res.data or []:
        pid = p.get("process_id")
        if pid not in proc_map:
            proc_map[pid] = p

    saved = []
    skipped = []
    now = datetime.now().isoformat()

    for pid in req.process_ids:
        # 이미 등록됐는지 확인
        existing = supabase.table("factory_process")\
            .select("id")\
            .eq("factory_id", factory_id)\
            .eq("process_id", pid)\
            .limit(1).execute()

        if existing.data:
            skipped.append(pid)
            continue

        proc = proc_map.get(pid, {})
        supabase.table("factory_process").insert({
            "factory_id":   factory_id,
            "process_id":   pid,
            "process_lv1":  proc.get("process_lv1"),
            "process_lv2":  proc.get("process_lv2"),
            "process_lv3":  proc.get("process_lv3"),
            "process_lv4":  proc.get("process_lv4"),
            "process_path": proc.get("process_path"),
            "is_primary":   req.is_primary,
            "is_active":    True,
            "created_at":   now,
        }).execute()
        saved.append(pid)

    return {
        "status": "success",
        "factory_id": factory_id,
        "saved_count": len(saved),
        "skipped_count": len(skipped),
        "saved_process_ids": saved,
    }


# ============================================================
# 4. 공정 삭제
# ============================================================

@router.delete("/{factory_id}/processes/{process_id}")
def delete_process(factory_id: str, process_id: str):
    """시설에서 공정 삭제"""
    supabase = get_supabase()

    supabase.table("factory_process")\
        .update({"is_active": False})\
        .eq("factory_id", factory_id)\
        .eq("process_id", process_id)\
        .execute()

    return {"status": "success", "message": f"공정 {process_id} 삭제 완료"}


# ============================================================
# 5. 등록된 공정 기반 설비 추천
# ============================================================

@router.get("/{factory_id}/recommend-equipment")
def recommend_equipment_by_process(
    factory_id: str,
    match_bands: str = "MUST,CORE,CORE_PLUS"
):
    """
    시설에 등록된 공정 기반 설비 추천
    등록된 공정이 없으면 → KSIC 기반으로 fallback
    """
    supabase = get_supabase()

    factory_res = supabase.table("factories")\
        .select("id, name, ksic_code, ksic_name")\
        .eq("id", factory_id)\
        .single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    factory = factory_res.data
    bands = [b.strip() for b in match_bands.split(",")]

    # 등록된 공정 조회
    proc_res = supabase.table("factory_process")\
        .select("process_id, process_path")\
        .eq("factory_id", factory_id)\
        .eq("is_active", True)\
        .execute()

    registered_processes = proc_res.data or []
    process_ids = [p["process_id"] for p in registered_processes]

    # 설비 조회
    if process_ids:
        # 공정 기반 설비 추천
        source = "process"
        equip_res = supabase.table("process_equipment_map")\
            .select("facility_name_std, match_band, match_score, category_path, process_id, process_path")\
            .in_("process_id", process_ids)\
            .in_("match_band", bands)\
            .order("match_score", desc=True)\
            .limit(200).execute()
    else:
        # KSIC 기반 fallback
        source = "ksic_fallback"
        ksic_code = factory.get("ksic_code")
        if not ksic_code:
            return {
                "status": "warning",
                "message": "공정과 KSIC 코드 모두 미등록",
                "data": []
            }
        equip_res = supabase.table("process_equipment_map")\
            .select("facility_name_std, match_band, match_score, category_path, process_id, process_path")\
            .eq("industry_code_full", ksic_code)\
            .in_("match_band", bands)\
            .order("match_score", desc=True)\
            .limit(200).execute()

    # 중복 제거 (facility_name_std 기준)
    seen = {}
    for e in equip_res.data or []:
        name = e.get("facility_name_std", "")
        if name and name not in seen:
            seen[name] = e
        elif name and e.get("match_score", 0) > seen[name].get("match_score", 0):
            seen[name] = e

    equipments = list(seen.values())

    # 현재 등록된 설비
    existing_res = supabase.table("equipment_assets")\
        .select("asset_name, equipment_type_code")\
        .eq("factory_id", factory_id)\
        .execute()
    existing_types = {e.get("equipment_type_code") for e in (existing_res.data or []) if e.get("equipment_type_code")}

    # 결과 구성
    result_equipments = []
    for e in equipments:
        name = e.get("facility_name_std", "")
        eq_type = get_equipment_type(name)
        result_equipments.append({
            "facility_name_std":   name,
            "equipment_type_code": eq_type,
            "match_band":          e.get("match_band"),
            "match_score":         e.get("match_score"),
            "category_path":       e.get("category_path"),
            "process_path":        e.get("process_path"),
            "is_mapped":           eq_type is not None,
            "is_registered":       eq_type in existing_types if eq_type else False,
        })

    must_count  = sum(1 for e in result_equipments if e["match_band"] == "MUST")
    core_count  = sum(1 for e in result_equipments if e["match_band"] in ["CORE","CORE_PLUS"])
    mapped      = sum(1 for e in result_equipments if e["is_mapped"])
    registered  = sum(1 for e in result_equipments if e["is_registered"])

    return {
        "status":       "success",
        "factory_id":   factory_id,
        "factory_name": factory.get("name"),
        "source":       source,
        "registered_processes": len(process_ids),
        "summary": {
            "total":       len(result_equipments),
            "must":        must_count,
            "core":        core_count,
            "mapped":      mapped,
            "registered":  registered,
            "not_registered": mapped - registered,
        },
        "equipments": result_equipments,
    }


# ============================================================
# 6. 추천 설비 일괄 등록
# ============================================================

@router.post("/{factory_id}/register-equipment")
def register_equipment(factory_id: str, req: EquipmentRegisterRequest):
    """
    추천 설비를 equipment_assets에 일괄 등록
    이미 동일한 equipment_type_code가 있는 설비는 스킵
    """
    supabase = get_supabase()

    factory_res = supabase.table("factories")\
        .select("id, name")\
        .eq("id", factory_id)\
        .single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    # 현재 등록된 설비 타입
    existing_res = supabase.table("equipment_assets")\
        .select("equipment_type_code")\
        .eq("factory_id", factory_id)\
        .execute()
    existing_types = {e.get("equipment_type_code") for e in (existing_res.data or []) if e.get("equipment_type_code")}

    saved   = []
    skipped = []
    now     = datetime.now().isoformat()

    for facility_name in req.facility_names:
        eq_type = get_equipment_type(facility_name)
        if not eq_type:
            skipped.append({"name": facility_name, "reason": "equipment_type_code 매핑 없음"})
            continue

        if eq_type in existing_types:
            skipped.append({"name": facility_name, "reason": "이미 등록된 설비 유형"})
            continue

        # equipment_assets 등록
        supabase.table("equipment_assets").insert({
            "factory_id":          factory_id,
            "asset_name":          facility_name,
            "asset_code":          f"AUTO-{factory_id[:8]}-{eq_type}",
            "equipment_type_code": eq_type,
            "is_operating":        True,
            "is_legal_target":     True,
            "description":         f"KSIC/공정 기반 자동 등록 — {req.process_id or 'AUTO'}",
            "updated_at":          now,
        }).execute()

        existing_types.add(eq_type)
        saved.append({"name": facility_name, "equipment_type_code": eq_type})

    return {
        "status":        "success",
        "factory_id":    factory_id,
        "saved_count":   len(saved),
        "skipped_count": len(skipped),
        "saved":         saved,
        "skipped":       skipped,
    }


@router.get("/test")
def test():
    return {"message": "factory process engine alive", "version": "1.0.0"}
