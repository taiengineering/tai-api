"""
KOSHA 데이터 수집 — DB 저장 + 크론 갱신
prefix: /kosha-collect

v1.7.0 (2026-08-10):
  [FIX] _collect_guide() 신 KOSHA GUIDE 전용 API 전환 — kosha_guide 0건 해소.
        폐기된 srch/smartSearch 키워드 우회 → getKoshaGuide(koshaguide) 전용 API.
        callApiId=1050 필수. 응답 body.items.item[] (techGdlnNm/No/OfancYmd/fileDownloadUrl).

v1.6.0 (2026-05-02):
  [FIX] MAX_PAGES 100→500 (10,000건 한도 해제)
  [ADD] _collect_safety_materials()에 start_page 파라미터 추가
  [ADD] /run 엔드포인트에 start_page 쿼리 파라미터 추가 (이어받기 가능)

v1.5.0 (2026-04-30):
  [ADD] _classify_material() — 제목 기반 자동 카테고리/업종 분류
  [ADD] _collect_safety_materials()에 수집 시 category/sector 자동 적용

v1.4.0: KoshaAPI.items() 파싱 + 필드명 변경 대응
v1.3.1: _log() 버그 수정
v1.3.0: callApiId 추가
"""
from __future__ import annotations
import os, logging, httpx, json, hashlib, re
from datetime import datetime, timezone
from fastapi import APIRouter, Query, BackgroundTasks
from typing import Optional, Tuple
from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/kosha-collect", tags=["KOSHA데이터수집"])

def _get_service_key() -> str:
    return (
        os.getenv("DATA_GO_KR_SERVICE_KEY")
        or os.getenv("KOSHA_SERVICE_KEY")
        or os.getenv("BUILDING_API_KEY", "")
    )


def _build_proxy_url() -> Optional[str]:
    """
    아웃바운드 프록시 URL 조합 — data.go.kr 고정 IP 경유용.
    OUTBOUND_PROXY(예: http://1.234.79.95) + PROXY_USER/PROXY_PASS + 포트(기본 8080).
    - 인증 정보(PROXY_USER/PASS)는 URL 에 합쳐 넣되, 값은 절대 로그/응답에 노출하지 않는다.
    - OUTBOUND_PROXY 에 포트가 없으면 PROXY_PORT(기본 8080)를 붙인다.
    - OUTBOUND_PROXY 미설정이면 None → 호출부는 프록시 없이 직접 나간다.
    """
    from urllib.parse import urlparse, quote
    raw = os.getenv("OUTBOUND_PROXY") or ""
    if not raw:
        return None
    if "://" not in raw:
        raw = "http://" + raw
    p = urlparse(raw)
    scheme = p.scheme or "http"
    host = p.hostname
    if not host:
        return None
    port = p.port or int(os.getenv("PROXY_PORT", "8080"))
    user = os.getenv("PROXY_USER") or ""
    pw = os.getenv("PROXY_PASS") or ""
    if user and pw:
        auth = f"{quote(user, safe='')}:{quote(pw, safe='')}@"
    else:
        auth = ""
    return f"{scheme}://{auth}{host}:{port}"


BASE      = "https://apis.data.go.kr/B552468"
MAX_ROWS  = 100
MAX_PAGES = 500   # v1.6.0: 100→500 (10,000건 한도 해제. 실 totalCount 기반으로 자동 중단됨)
INIT_DATE = "2024-01-01"


# ─────────────────────────────────────────────────────
# 자동 분류 — v1.5.0
# ─────────────────────────────────────────────────────

# 카테고리 분류 규칙 (우선순위 순)
_CATEGORY_RULES: list[Tuple[str, str]] = [
    # 외국인자료 (다른 카테고리와 중복되므로 먼저)
    (r'(외국인|다문화|foreign)', 'FOREIGN'),
    (r'\((몽골|라오스|미얀마|캄보디아|키르기스|네팔|태국|베트남|중국|우즈베|필리핀|인도네|파키스|방글라|스리랑카|티모르|영어|일본|러시아)', 'FOREIGN'),
    # 영상·VR
    (r'(VR|메타버스|HMD용|동영상|숙폼|현장르포|당신의 선택|UCC)', 'VIDEO_VR'),
    # 교육자료
    (r'(SIF 교안|SIF교안|\(교안\)|교재|교육과정|위탁과정|교육프로그램|관리자용|이러닝|e-learning)', 'EDUCATION'),
    # 사고사례
    (r'(OPL|스토리텔링|사고사례|재해사례|재해예방 OPS|\[OPS\])', 'CASE_STUDY'),
    # 포스터·홍보물
    (r'(포스터|스티커|픽토그램|안전보건표지|리플릿|리플렛|브로슈어|홍보물|배너|현수막)', 'POSTER'),
    # 가이드·매뉴얼
    (r'(가이드|GUIDE|guide|매뉴얼|manual|안전수칙|작업절차|바로알기|편람)', 'GUIDE'),
    # 체크리스트
    (r'(체크리스트|점검표|자율점검)', 'CHECKLIST'),
    # 연구·보고서
    (r'(연구|보고서|논문|학술|조사|분석|평가|검토|통계|현황|연보|연감|요약집)', 'RESEARCH'),
    # 보건·건강
    (r'(건강|보건|검진|직업병|질환|화학물질|유해물질|MSDS|작업환경|소음|분진|석면)', 'HEALTH'),
    # 법령
    (r'(법령|규정|고시|시행령|시행규칙)', 'REGULATION'),
    # 교육 (넓은 범위)
    (r'(교육|교안|학습)', 'EDUCATION'),
    # 사고·재해 관련
    (r'(사고|사례|재해|재해예방)', 'CASE_STUDY'),
]

# 업종 분류 규칙
_SECTOR_RULES: list[Tuple[str, str]] = [
    (r'(건설|건설업|건설현장|콘크리트|타워크레인|비계|거푸집|굴착|항타|갱폼|공사)', 'CONSTRUCTION'),
    (r'(제조|제조업|프레스|선반|절단기|용접|사출|전단기|절곡기|컨베이어|크레인|지게차|보일러|압력용기)', 'MANUFACTURING'),
    (r'(서비스|배달|이륨차|물류|운반|운송|택배|청소|조리)', 'SERVICE'),
]


def _classify_material(title: str) -> Tuple[str, str]:
    """
    제목 기반 카테고리 + 업종 자동 분류.
    Returns (category, sector)
    """
    t = title or ""
    category = "OTHER"
    sector = "COMMON"
    for pattern, cat in _CATEGORY_RULES:
        if re.search(pattern, t):
            category = cat
            break
    for pattern, sec in _SECTOR_RULES:
        if re.search(pattern, t):
            sector = sec
            break
    return category, sector


def _parse_kosha_text(text: str) -> dict:
    """KOSHA 응답 텍스트 → dict. JSON 우선, 실패 시 XML 파싱(기존 동작 유지)."""
    try:
        data = json.loads(text)
        if "response" in data and isinstance(data["response"], dict):
            return data["response"]
        return data
    except Exception:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text)
        items = []
        for items_el in root.findall(".//items"):
            for item_el in items_el:
                item = {c.tag: c.text or "" for c in item_el}
                if item:
                    items.append(item)
        return {"body": {
            "items": items,
            "totalCount": int(root.findtext(".//totalCount") or 0)
        }}


class KoshaAPI:
    @staticmethod
    async def get(path: str, params: dict) -> dict:
        params["serviceKey"] = _get_service_key()
        # data.go.kr 은 고정 IP 화이트리스트 — 아웃바운드 프록시 경유(있으면).
        # 프록시 미설정이면 직접 나간다(하위호환). 인증 정보는 _build_proxy_url 이 조합.
        proxy = _build_proxy_url()
        url = f"{BASE}/{path}"
        try:
            if proxy:
                # 프록시 경유 HTTPS 는 requests(동기)로 — Squid 는 TCP_TUNNEL(내용 무변형)이라
                # 프록시 무관하나, tai-api 의 requests params= 인코딩이 서버 curl 과 달라
                # data.go.kr 이 코드10 을 주는 문제. 서버 curl 과 100% 동일하게 쿼리스트링을
                # 직접 조립해 URL 에 붙인다(params= 미사용). trust_env=False 로 시스템 프록시
                # env 차단. asyncio.to_thread 로 async 논블로킹.
                import asyncio, requests
                from urllib.parse import urlencode
                full_url = f"{url}?{urlencode(params)}"
                def _blocking_get():
                    s = requests.Session()
                    s.trust_env = False
                    rr = s.get(full_url,
                               proxies={"http": proxy, "https": proxy},
                               timeout=30)
                    return rr.status_code, rr.text
                _status, text = await asyncio.to_thread(_blocking_get)
                if _status >= 400:
                    log.error("[KOSHA] %s 프록시 HTTP %s", path, _status)
                return _parse_kosha_text(text)
            else:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    return _parse_kosha_text(resp.text)
        except Exception as e:
            log.error("[KOSHA] %s 호출 실패: %s", path, e)
            return {"body": {"items": [], "totalCount": 0}}

    @staticmethod
    def items(resp: dict) -> list:
        body = resp.get("body") or resp.get("data") or {}
        if isinstance(body, dict):
            it = body.get("items", [])
            if isinstance(it, list):
                return it
            if isinstance(it, dict):
                inner = it.get("item", [])
                if isinstance(inner, list):
                    return inner
                if isinstance(inner, dict):
                    return [inner]
                return []
        return []

    @staticmethod
    def total(resp: dict) -> int:
        body = resp.get("body") or resp.get("data") or {}
        return int(body.get("totalCount", 0)) if isinstance(body, dict) else 0


def _log(target: str, status: str, rows: int = 0, err: str = ""):
    try:
        sb = get_supabase()
        sb.table("kosha_collect_log").insert({
            "target": target, "status": status,
            "rows_upserted": rows,
            "error_msg": err or None,
        }).execute()
    except Exception:
        pass


def _get_last_collected(target: str) -> Optional[str]:
    try:
        sb = get_supabase()
        r = (sb.table("kosha_collect_log")
               .select("collected_at")
               .eq("target", target)
               .eq("status", "success")
               .order("collected_at", desc=True)
               .limit(1)
               .execute())
        if r.data:
            return r.data[0]["collected_at"][:10]
    except Exception:
        pass
    return INIT_DATE


def _parse_date(val: str) -> Optional[str]:
    if not val: return None
    v = str(val).strip().replace("/", "-")
    if len(v) == 8 and v.isdigit():
        return f"{v[:4]}-{v[4:6]}-{v[6:8]}"
    return v[:10] if len(v) >= 10 else v


def _after_since(date_str: str, since_date: str) -> bool:
    d = _parse_date(date_str)
    if not d: return True
    return d >= since_date


def _make_id(prefix: str, *parts) -> str:
    raw = "|".join(str(p) for p in parts if p)
    if raw:
        return hashlib.md5(raw.encode()).hexdigest()[:16]
    return f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}"


# ─────────────────────────────────────────────────────
# 수집함수
# ─────────────────────────────────────────────────────

async def _collect_accident_cases(since_date: str = INIT_DATE, full_refresh: bool = False) -> dict:
    sb = get_supabase()
    since = INIT_DATE if full_refresh else since_date
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        params = {"callApiId": "1040", "pageNo": page, "numOfRows": MAX_ROWS}
        resp  = await KoshaAPI.get("disaster_api02/getdisaster_api02", params)
        items = KoshaAPI.items(resp)
        if not items: break
        rows, stop_early = [], False
        for i, it in enumerate(items):
            dt = str(it.get("regDt") or it.get("REG_DT") or it.get("writeDate") or "")
            if dt and not _after_since(dt, since):
                stop_early = True
                continue
            rid = str(it.get("boardNo") or it.get("BOARD_NO") or it.get("bbsNo") or _make_id("ac", page, i))
            rows.append({
                "id": rid,
                "title": it.get("title") or it.get("TITLE") or it.get("bbsTitle") or it.get("BBS_TITLE") or "",
                "business": it.get("business") or it.get("BUSINESS") or "",
                "content": it.get("content") or it.get("CONTENT") or it.get("bbsContent") or "",
                "board_no": rid,
                "reg_dt": dt,
                "file_url": it.get("fileUrl") or it.get("FILE_URL") or "",
                "raw_json": it,
            })
        if rows:
            sb.table("kosha_accident_cases").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if stop_early or len(items) < MAX_ROWS: break
    _log("accident_cases", "success", total_upserted)
    return {"target": "accident_cases", "since": since, "upserted": total_upserted}


async def _collect_safety_materials(
    since_date: str = INIT_DATE,
    full_refresh: bool = False,
    start_page: int = 1,        # v1.6.0: 이어받기용 — 101부터 시작하면 기존 10,000건 건너뜀
) -> dict:
    """
    v1.6.0: start_page 파라미터 추가 — 101 이상 지정 시 기존 수집분 건너뛰고 추가분만 수집.
    v1.5.0: 수집 시 category/sector 자동 분류 적용.
    UPSERT(on_conflict=id) 방식이라 중복 걱정 없음.
    """
    sb = get_supabase()
    total_upserted = 0
    for page in range(start_page, MAX_PAGES + 1):
        resp  = await KoshaAPI.get(
            "selectMediaList01/getselectMediaList01",
            {"callApiId": "1030", "pageNo": page, "numOfRows": MAX_ROWS}
        )
        items = KoshaAPI.items(resp)
        if not items: break
        rows = []
        for i, it in enumerate(items):
            title = it.get("MED_SJ_NM") or it.get("title") or it.get("mediaTitle") or ""
            url   = it.get("MED_URL") or it.get("url") or it.get("mediaUrl") or ""
            rid   = it.get("mediaId") or it.get("MED_SEQ") or _make_id("mat", url, title)
            category, sector = _classify_material(title)
            rows.append({
                "id": str(rid),
                "title": title,
                "product_type": it.get("productType") or it.get("MED_CL_NM") or "",
                "industry": it.get("industry") or "",
                "accident_type": it.get("accidentType") or "",
                "url": url,
                "category": category,
                "sector": sector,
                "raw_json": it,
            })
        if rows:
            sb.table("kosha_safety_materials").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if len(items) < MAX_ROWS: break
    _log("safety_materials", "success", total_upserted)
    return {"target": "safety_materials", "start_page": start_page, "upserted": total_upserted}


async def _collect_construction_accidents(since_date: str = INIT_DATE, full_refresh: bool = False) -> dict:
    sb = get_supabase()
    since = INIT_DATE if full_refresh else since_date
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get(
            "constDsstr01/getconstDsstr01",
            {"callApiId": "1050", "pageNo": page, "numOfRows": MAX_ROWS}
        )
        items = KoshaAPI.items(resp)
        if not items: break
        rows, stop_early = [], False
        for i, it in enumerate(items):
            dt = str(it.get("occurrenceDate") or it.get("dsstrDt") or it.get("DSSTR_DT") or "")
            if dt and not _after_since(dt, since):
                stop_early = True
                continue
            rid = str(it.get("id") or it.get("seq") or it.get("SEQ") or _make_id("ca", page, i))
            rows.append({
                "id": rid,
                "accident_type": it.get("accidentType") or it.get("dsstrKnd") or it.get("DSSTR_KND") or "",
                "work_type": it.get("workType") or it.get("workKnd") or it.get("WORK_KND") or "",
                "causative": it.get("causative") or it.get("crtrFtr") or it.get("CRTR_FTR") or "",
                "occurrence_date": dt,
                "accident_summary": it.get("accidentSummary") or it.get("dsstrOutl") or it.get("DSSTR_OUTL") or "",
                "risk_reduction": it.get("riskReduction") or it.get("rskRdcMsr") or it.get("RSK_RDC_MSR") or "",
                "raw_json": it,
            })
        if rows:
            sb.table("kosha_construction_accidents").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if stop_early or len(items) < MAX_ROWS: break
    _log("construction_accidents", "success", total_upserted)
    return {"target": "construction_accidents", "since": since, "upserted": total_upserted}


async def _collect_safety_light(full_refresh: bool = True) -> dict:
    sb = get_supabase()
    rows_all: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get(
            "constplan/getconstplan",
            {"callApiId": "1020", "pageNo": page, "numOfRows": MAX_ROWS}
        )
        items = KoshaAPI.items(resp)
        if not items: break
        for i, it in enumerate(items):
            rid = str(it.get("id") or it.get("siteId") or it.get("SITE_ID") or it.get("sno") or _make_id("sl", page, i))
            rows_all.append({
                "id": rid,
                "site_nm": it.get("siteNm") or it.get("SITE_NM") or it.get("siteName") or "",
                "sido": it.get("sido") or it.get("SIDO") or "",
                "sigungu": it.get("sigungu") or it.get("SIGUNGU") or "",
                "signal": it.get("signal") or it.get("SIGNAL") or it.get("signalColor") or "",
                "guide_dt": it.get("guideDt") or it.get("GUIDE_DT") or it.get("inspDate") or "",
                "guide_org": it.get("guideOrg") or it.get("GUIDE_ORG") or it.get("orgName") or "",
                "raw_json": it,
            })
        if len(items) < MAX_ROWS: break
    total_upserted = 0
    if rows_all:
        sb.table("kosha_construction_safety_light").delete().neq("id", "__never__").execute()
        sb.table("kosha_construction_safety_light").upsert(rows_all, on_conflict="id").execute()
        total_upserted = len(rows_all)
    _log("construction_safety_light", "success", total_upserted)
    return {"target": "construction_safety_light", "upserted": total_upserted}


async def _collect_risk_assessment(since_date: str = INIT_DATE, full_refresh: bool = False) -> dict:
    sb = get_supabase()
    since = INIT_DATE if full_refresh else since_date
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get(
            "riskAssmt/getRiskAssmtAccdtInfo",
            {"pageNo": page, "numOfRows": MAX_ROWS}
        )
        items = KoshaAPI.items(resp)
        if not items: break
        rows, stop_early = [], False
        for i, it in enumerate(items):
            dt = str(it.get("certDate") or it.get("acptDt") or it.get("ACPT_DT") or "")
            if dt and not _after_since(dt, since):
                stop_early = True
                continue
            rid = str(it.get("id") or it.get("seq") or it.get("SEQ") or _make_id("ra", page, i))
            rows.append({
                "id": rid,
                "company_nm": it.get("companyNm") or it.get("COMPANY_NM") or it.get("siteNm") or "",
                "sido": it.get("sido") or it.get("SIDO") or "",
                "cert_date": dt,
                "expiry_date": it.get("expiryDate") or it.get("vlddDt") or it.get("VLDD_DT") or "",
                "industry": it.get("industry") or it.get("INDUSTRY") or "",
                "labor_office": it.get("laborOffice") or it.get("LABOR_OFFICE") or "",
                "raw_json": it,
            })
        if rows:
            sb.table("kosha_risk_assessment").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if stop_early or len(items) < MAX_ROWS: break
    _log("risk_assessment", "success", total_upserted)
    return {"target": "risk_assessment", "since": since, "upserted": total_upserted}


async def _collect_guide(full_refresh: bool = False, call_api_id: str = "1050") -> dict:
    """
    v1.7.0: 신 KOSHA GUIDE 전용 API(getKoshaGuide) 전환.
    - 엔드포인트: koshaguide/getKoshaGuide (Base apis.data.go.kr/B552468)
    - 필수: callApiId (미입력시 에러99). serviceKey 는 KoshaAPI.get 이 주입.
    - 응답: body.items.item[] — techGdlnNm(규정명)/techGdlnNo(규정번호)/
            techGdlnOfancYmd(공표일자)/fileDownloadUrl(다운로드링크).
    - kosha_guide 스키마(guide_no/guide_title/category/guide_url/regist_date/raw_json) 매핑.
    - 폐기된 srch/smartSearch 키워드 우회 제거(0건 원인).

    call_api_id: 기본 "1050". debug 조사(G-msmq1ip1)로 올바른 값 확정 시까지 오버라이드 가능.
    """
    sb = get_supabase()
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        resp = await KoshaAPI.get(
            "koshaguide/getKoshaGuide",
            {"callApiId": call_api_id, "pageNo": page, "numOfRows": MAX_ROWS}
        )
        items = KoshaAPI.items(resp)
        if not items:
            break
        rows = []
        for i, it in enumerate(items):
            no  = str(it.get("techGdlnNo") or "").strip()
            rid = no if no else _make_id("guide", page, i)
            rows.append({
                "id": rid,
                "guide_no": no,
                "guide_title": it.get("techGdlnNm") or "",
                # 신 API 는 분야코드 필드가 없음 — 빈값(필요 시 techGdlnNo 접두로 후분류).
                "category": "",
                "guide_url": it.get("fileDownloadUrl") or "",
                "regist_date": it.get("techGdlnOfancYmd") or "",
                "raw_json": it,
            })
        if rows:
            sb.table("kosha_guide").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if len(items) < MAX_ROWS:
            break
    _log("guide", "success", total_upserted)
    return {"target": "guide", "upserted": total_upserted}


# ─────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────

@router.post("/run")
async def collect_all(
    background_tasks: BackgroundTasks,
    target:       Optional[str] = Query(None),
    since_date:   str  = Query(INIT_DATE),
    full_refresh: bool = Query(False),
    background:   bool = Query(False),
    start_page:   int  = Query(1, ge=1, description="safety-materials 이어받기용 시작 페이지 (기본 1, 추가수집 시 101 지정)"),
):
    targets = [target] if target else [
        "accident-cases", "safety-materials", "construction-accidents",
        "construction-safety-light", "risk-assessment", "guide"
    ]

    async def run_all():
        for t in targets:
            try:
                since = since_date if full_refresh else _get_last_collected(t)
                await _dispatch(t, since, full_refresh, start_page)
            except Exception as e:
                _log(t, "fail", 0, str(e)[:300])

    if background:
        background_tasks.add_task(run_all)
        return {"status": "queued", "targets": targets,
                "since_date": since_date, "full_refresh": full_refresh,
                "start_page": start_page}

    results = []
    for t in targets:
        try:
            since = since_date if full_refresh else _get_last_collected(t)
            r = await _dispatch(t, since, full_refresh, start_page)
            results.append(r)
        except Exception as e:
            _log(t, "fail", 0, str(e)[:300])
            results.append({"target": t, "error": str(e)[:200]})
    return {"status": "done", "results": results}


async def _dispatch(target: str, since_date: str, full_refresh: bool, start_page: int = 1):
    if target == "accident-cases":            return await _collect_accident_cases(since_date, full_refresh)
    elif target == "safety-materials":        return await _collect_safety_materials(since_date, full_refresh, start_page)
    elif target == "construction-accidents":  return await _collect_construction_accidents(since_date, full_refresh)
    elif target == "construction-safety-light": return await _collect_safety_light()
    elif target == "risk-assessment":         return await _collect_risk_assessment(since_date, full_refresh)
    elif target == "guide":                   return await _collect_guide(full_refresh)
    raise ValueError(f"Unknown target: {target}")


@router.get("/debug-guide")
async def debug_guide(
    call_api_id: str = Query("1050", description="callApiId 고정값 (명세: 1050)"),
    path: str = Query("koshaguide/getKoshaGuide", description="KOSHA API 경로"),
    page_no: int = Query(1, ge=1),
    num_rows: int = Query(5, ge=1, le=20),
):
    """
    [임시 · 조사용 · 읽기 전용] 프록시 경유 requests URL직접 vs params 실측.
    G-msmq1ip1: Squid TCP_TUNNEL/200(프록시 무변형)인데 tai-api requests params= 는
    코드10, 서버 curl(URL직접)은 NORMAL_CODE. URL직접 조립 방식 실측 확정용.
    serviceKey 마스킹. DB 쓰기 없음. 확정 후 제거.
    """
    key_src, key_len = None, 0
    for name in ("DATA_GO_KR_SERVICE_KEY", "KOSHA_SERVICE_KEY", "BUILDING_API_KEY"):
        v = os.getenv(name)
        if v:
            key_src, key_len = name, len(v)
            break
    svc_key = _get_service_key()
    proxy = _build_proxy_url()

    url = f"{BASE}/{path}"
    params = {"callApiId": call_api_id, "pageNo": page_no,
              "numOfRows": num_rows, "serviceKey": svc_key}

    def _summarize(status, text):
        masked = text or ""
        if svc_key and svc_key in masked:
            masked = masked.replace(svc_key, "<KEY>")
        try:
            j = json.loads(masked)
            body = j.get("body") if isinstance(j, dict) else None
            tc = body.get("totalCount") if isinstance(body, dict) else None
            hdr = j.get("header") if isinstance(j, dict) else None
            return {"http_status": status, "totalCount": tc,
                    "resultCode": (hdr or {}).get("resultCode") if isinstance(hdr, dict) else None,
                    "head": masked[:300]}
        except Exception:
            return {"http_status": status, "parsed": "not-json(xml?)", "head": masked[:300]}

    proxy_display = None
    if proxy:
        try:
            from urllib.parse import urlparse as _up
            _p = _up(proxy)
            proxy_display = f"{_p.scheme}://{_p.hostname}:{_p.port}"
        except Exception:
            proxy_display = "set"

    out = {"proxy_present": bool(proxy), "proxy_host_port": proxy_display}

    # 1) requests + params= (기존 실패 방식, 대조)
    if proxy:
        try:
            import asyncio as _aio, requests as _req
            def _rget():
                s = _req.Session(); s.trust_env = False
                rr = s.get(url, params=params,
                           proxies={"http": proxy, "https": proxy}, timeout=25)
                return rr.status_code, rr.text
            _st, _tx = await _aio.to_thread(_rget)
            out["guide_via_proxy_params"] = _summarize(_st, _tx)
        except Exception as e:
            out["guide_via_proxy_params"] = {"exception": f"{type(e).__name__}: {str(e)[:200]}"}

    # 2) requests + URL 직접 조립 (서버 curl 동일, 성공 기대)
    if proxy:
        try:
            import asyncio as _aio2, requests as _req2
            from urllib.parse import urlencode as _ue
            _full = f"{url}?{_ue(params)}"
            def _rget2():
                s = _req2.Session(); s.trust_env = False
                rr = s.get(_full, proxies={"http": proxy, "https": proxy}, timeout=25)
                return rr.status_code, rr.text
            _st2, _tx2 = await _aio2.to_thread(_rget2)
            out["guide_via_proxy_urlstr"] = _summarize(_st2, _tx2)
        except Exception as e:
            out["guide_via_proxy_urlstr"] = {"exception": f"{type(e).__name__}: {str(e)[:200]}"}

    return {
        "path": path,
        "service_key": {"present": bool(svc_key), "source_env": key_src, "length": key_len},
        "results": out,
    }


@router.get("/status")
def collect_status(limit: int = Query(30, ge=1, le=100)):
    sb = get_supabase()
    logs = (sb.table("kosha_collect_log")
              .select("*")
              .order("collected_at", desc=True)
              .limit(limit)
              .execute())
    counts = {}
    for tbl, dbname in [
        ("accident-cases",            "kosha_accident_cases"),
        ("safety-materials",          "kosha_safety_materials"),
        ("construction-accidents",    "kosha_construction_accidents"),
        ("construction-safety-light", "kosha_construction_safety_light"),
        ("risk-assessment",           "kosha_risk_assessment"),
        ("guide",                     "kosha_guide"),
    ]:
        try:
            r = sb.table(dbname).select("id", count="exact").execute()
            counts[tbl] = r.count or 0
        except Exception:
            counts[tbl] = -1
    return {"status": "success",
            "db_counts": counts, "recent_logs": logs.data or []}
