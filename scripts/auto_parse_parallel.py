#!/usr/bin/env python3
"""
TAI 병렬 auto-parse v2 — 10배 빠름
================================
Supabase + Claude API 직접 호출, asyncio 병렬 처리.

사용법:
  export ANTHROPIC_API_KEY='...'
  export SUPABASE_SERVICE_KEY='...'
  python3 scripts/auto_parse_parallel.py

환경변수:
  WORKERS=10              # 동시 처리 수 (기본 10)
  SUPABASE_URL=https://xntdkrjhgcscmqctdzyo.supabase.co
  DRY_RUN=1               # 테스트 모드
"""
import os, sys, json, time, re, asyncio, logging
from datetime import datetime, timezone

try:
    import httpx
    from supabase import create_client
except ImportError:
    print("pip3 install httpx supabase"); sys.exit(1)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://xntdkrjhgcscmqctdzyo.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
WORKERS = int(os.environ.get("WORKERS", "10"))
DRY_RUN = os.environ.get("DRY_RUN", "") == "1"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

if not SUPABASE_KEY: print("SUPABASE_SERVICE_KEY 필요"); sys.exit(1)
if not ANTHROPIC_KEY: print("ANTHROPIC_API_KEY 필요"); sys.exit(1)

log = logging.getLogger("parse")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

EXCLUDED = {"SPECIAL_FACILITY","SPECIAL","CONSTRUCTION_SPECIAL","MANUFACTURING_SPECIAL"}

SYS_PROMPT = """당신은 한국 산업안전 법령 전문가입니다.
법령 원문을 분석하여 안전관리 판정 룰을 JSON 배열로 추출합니다.
추출 대상: APPOINT(선임), INSPECT(점검), NOTIFY(신고), REPORT(기록), ACTION(조치)
섹터: BUILDING / MANUFACTURING / CONSTRUCTION / COMMON
condition_code: building_area, worker_count, electric_capacity, gas_capacity_kg, gas_capacity_m3, boiler_capacity_kw, elevator_count, is_hazardous_material, annual_energy_toe, construction_amount, floor_count, employee_count, has_chemical_substance, is_multi_use, has_high_pressure_gas, has_boiler 등
응답은 순수 JSON 배열만. 의무가 없으면 []. 학교/병원/복지시설 전용이면 []."""

USR_TPL = """법령명: {law_name}\n조문: {text}\n위 조문에서 안전관리 의무를 JSON 배열로 추출: [{{"draft_rule_id":"","obligation_type":"","sector":"","condition_code":null,"condition_operator":null,"condition_value":null,"obligation_summary":"","remarks":"","penalty_summary":null,"penalty_value":null,"ai_confidence":0,"ai_reasoning":""}}]"""


def get_unparsed():
    log.info("미파싱 조문 조회...")
    articles, page = [], 0
    while True:
        res = (sb.table("law_article")
               .select("id,article_no,article_title,article_text,law_version_id")
               .is_("ai_parsed_at","null").not_.is_("article_text","null")
               .order("article_no_sort").range(page*1000,(page+1)*1000-1).execute())
        if not res.data: break
        articles.extend([a for a in res.data if len(a.get("article_text",""))>=20])
        if len(res.data)<1000: break
        page += 1
    # version→law mapping
    vids = list(set(a["law_version_id"] for a in articles))
    vmap = {}
    for i in range(0,len(vids),50):
        vs = sb.table("law_version").select("id,law_id").in_("id",vids[i:i+50]).execute()
        for v in (vs.data or []): vmap[v["id"]] = v["law_id"]
    lids = list(set(vmap.values()))
    lmap = {}
    for i in range(0,len(lids),50):
        ls = sb.table("law_master").select("id,law_name").in_("id",lids[i:i+50]).execute()
        for l in (ls.data or []): lmap[l["id"]] = l["law_name"]
    enriched = []
    for a in articles:
        lid = vmap.get(a["law_version_id"])
        nm = lmap.get(lid,"")
        if nm: a["law_name"]=nm; enriched.append(a)
    log.info(f"  {len(enriched)}개 조문")
    return enriched


async def call_claude(client, law_name, text):
    try:
        r = await client.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key":ANTHROPIC_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},
            json={"model":CLAUDE_MODEL,"max_tokens":2200,"system":SYS_PROMPT,
                  "messages":[{"role":"user","content":USR_TPL.format(law_name=law_name,text=text[:3000])}]},
            timeout=60)
        if r.status_code != 200: return []
        raw = "".join(b["text"] for b in r.json().get("content",[]) if b.get("type")=="text")
        cleaned = re.sub(r"```json\s*","",raw.strip()); cleaned = re.sub(r"```\s*","",cleaned).strip()
        try: result = json.loads(cleaned); return result if isinstance(result,list) else []
        except: m = re.search(r"\[.*\]",cleaned,re.DOTALL); return json.loads(m.group()) if m else []
    except Exception as e:
        return []


async def process(client, art, stats, sem):
    async with sem:
        try:
            rules = await call_claude(client, art["law_name"], art.get("article_text",""))
            now = datetime.now(timezone.utc).isoformat()
            label = f"제{art.get('article_no','')}조{art.get('article_title','') or ''}"
            if not DRY_RUN:
                sb.table("law_article").update({"ai_parsed_at":now}).eq("id",art["id"]).execute()
            stats["parsed"] += 1
            for rule in rules:
                sec = (rule.get("sector") or "").upper()
                if sec in EXCLUDED: continue
                draft = {"law_name":art["law_name"],"law_article":label,"article_id":art["id"],
                         "article_text":art.get("article_text","")[:2000],
                         "draft_rule_id":rule.get("draft_rule_id"),"obligation_type":rule.get("obligation_type"),
                         "sector":sec,"condition_code":rule.get("condition_code"),
                         "condition_operator":rule.get("condition_operator","gte"),
                         "condition_value":str(rule["condition_value"]) if rule.get("condition_value") is not None else None,
                         "obligation_summary":rule.get("obligation_summary"),"penalty_summary":rule.get("penalty_summary"),
                         "ai_confidence":rule.get("ai_confidence"),"ai_reasoning":rule.get("ai_reasoning"),
                         "ai_flags":rule.get("ai_flags"),"status":"PENDING"}
                if not DRY_RUN: sb.table("law_rule_drafts").insert(draft).execute()
                stats["drafts"] += 1
        except Exception as e:
            stats["errors"] += 1
        total = stats["parsed"]+stats["errors"]
        if total % 100 == 0 and total > 0:
            el = (time.time()-stats["start"])/60
            eta = el/total*(stats["total"]-total) if total else 0
            log.info(f"  [{total}/{stats['total']}] 초안{stats['drafts']} 에러{stats['errors']} ({el:.0f}분, ETA {eta:.0f}분)")


async def main():
    start = time.time()
    log.info(f"TAI 병렬 auto-parse v2 ({WORKERS} workers)")
    arts = get_unparsed()
    if not arts: log.info("완료"); return
    stats = {"total":len(arts),"parsed":0,"drafts":0,"errors":0,"start":start}
    sem = asyncio.Semaphore(WORKERS)
    async with httpx.AsyncClient(timeout=90) as client:
        await asyncio.gather(*[process(client,a,stats,sem) for a in arts])
    el = (time.time()-start)/60
    log.info(f"완료: {stats['parsed']}/{stats['total']} 파싱, 초안{stats['drafts']}, 에러{stats['errors']}, {el:.1f}분")
    json.dump({**stats,"elapsed":round(el,1),"workers":WORKERS},open("parse_result.json","w"),indent=2)

if __name__=="__main__": asyncio.run(main())
