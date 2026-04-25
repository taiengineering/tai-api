#!/usr/bin/env python3
"""
법령엔진 마무리 통합 스크립트 — finalize_law_pipeline.py
================================================================

갭 B + C + E 를 단일 Python 프로세스로 동시 처리.

Phase 1 (갭 B + C):
  ai_parsed_at = NULL 인 article 1,462건 (이미 기획창에서 리셋됨)을
  Sonnet 으로 직접 파싱 → law_rule_drafts INSERT →
  confidence ≥ 80 + condition_code 있으면 자동 APPROVED + master INSERT.
  프롬프트는 5개 영역 (산업안전·재난·환경·근로자보호·시설건물).
  로컬에서 Anthropic API 직접 호출 → Railway 부하 0.

Phase 2 (갭 E):
  Railway 의 POST /law-rule-generator/reparse-master 를 sector 별 4번
  순차 호출 + status 폴링. Phase 1 과 병렬 실행 가능.

실행:
  cd ~/Desktop/tai-engineering/tai-api
  git pull origin dev
  pip3 install anthropic supabase httpx tqdm python-dotenv  # 한 번만

  # .env 파일 (프로젝트 루트):
  ANTHROPIC_API_KEY=sk-ant-...
  SUPABASE_URL=https://xntdkrjhgcscmqctdzyo.supabase.co
  SUPABASE_KEY=eyJh...                # 또는 SUPABASE_SERVICE_KEY (service_role 권장)
  INTERNAL_API_SECRET=...

  # 실행 (.env 자동 로드, 두 페이즈 동시, 약 35-45분)
  python3 scripts/finalize_law_pipeline.py

  # 옵션
  python3 scripts/finalize_law_pipeline.py --phase 1     # Phase 1 만
  python3 scripts/finalize_law_pipeline.py --phase 2     # Phase 2 만
  python3 scripts/finalize_law_pipeline.py --dry-run --limit 3 --phase 1
  python3 scripts/finalize_law_pipeline.py --concurrency 3
"""
from __future__ import annotations

import os
import sys
import json
import re
import asyncio
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ──── .env 자동 로드 (project root) ────
try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve().parent
    for cand in [_here.parent / ".env", _here / ".env", Path.cwd() / ".env"]:
        if cand.exists():
            load_dotenv(cand)
            break
except ImportError:
    pass  # python-dotenv 없으면 OS 환경변수만

try:
    from anthropic import AsyncAnthropic
except ImportError:
    print("pip3 install anthropic"); sys.exit(1)

try:
    from supabase import create_client, Client
except ImportError:
    print("pip3 install supabase"); sys.exit(1)

try:
    import httpx
except ImportError:
    print("pip3 install httpx"); sys.exit(1)

try:
    from tqdm.asyncio import tqdm as atqdm
except ImportError:
    print("pip3 install tqdm"); sys.exit(1)


# ──────────────────────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────────────────────
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 2000
DEFAULT_CONCURRENCY = 5
AUTO_APPROVE_THRESHOLD = 80
RETRY_LIMIT = 1

API_URL = os.environ.get("TAI_API_URL", "https://api.taieng.co.kr")
RUN_TS = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.expanduser(f"~/finalize_log_{RUN_TS}.txt")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("finalize")


# ──────────────────────────────────────────────────────────────
# 환경변수 로딩 (여러 이름 폴백)
# ──────────────────────────────────────────────────────────────
def env_first(*keys: str, required: bool = True) -> str | None:
    """여러 환경변수명 중 첫 매치 반환."""
    for k in keys:
        v = os.environ.get(k, "").strip()
        if v:
            return v
    if required:
        log.error(f"환경변수 필요: {' 또는 '.join(keys)}")
        log.error("'.env' 파일을 프로젝트 루트에 두거나, export 로 설정하세요.")
        sys.exit(1)
    return None


def mask(s: str, n: int = 12) -> str:
    if not s:
        return "(없음)"
    return s[:n] + "..." if len(s) > n else s


# ──────────────────────────────────────────────────────────────
# Phase 1 프롬프트 (5영역 확장판 — 갭 B/C 의 핵심)
# ──────────────────────────────────────────────────────────────
PHASE1_SYSTEM = """당신은 한국 사업장 의무 법령 전문가입니다.
법령 조문 텍스트를 분석하여 사업장이 이행해야 할 의무 룰을 추출합니다.

추출 대상 영역 (산업안전 외 영역도 포함 — 갭 B 핵심):
1. 산업안전·보건 의무 (산안법, 산안기준규칙 등)
2. 재난·안전관리 의무 (재난기본법 — 모든 사업장 재난 대비)
3. 환경관리 의무 (탄소중립, 토양환경, 잔류성오염, 악취방지, 소음진동)
4. 근로자 보호 의무 (파견근로자 보호법, 근로기준법)
5. 시설·건물 관리 의무 (주택법, 다중이용업소법, 건축법 등)

추출 대상 의무 유형:
- APPOINT: 안전관리자·재난관리책임자·환경관리자 등 선임 의무
- INSPECT: 정기점검·안전검사·환경측정 의무
- NOTIFY: 신고·보고·제출 의무
- REPORT: 기록·보존 의무
- ACTION: 조치·설치·이행 의무

condition_code (사업장 적용 조건):
worker_count, employee_count, building_area, electric_capacity,
gas_capacity_kg, gas_capacity_m3, boiler_capacity_kw, elevator_count,
is_hazardous_material, annual_energy_toe, construction_amount,
floor_count, is_factory_registered, contractor_count, has_chemical_substance

sector: BUILDING, MANUFACTURING, CONSTRUCTION, COMMON, CONSTRUCTION_MANUFACTURING

⚠️ 사업장 적용 가능 의무만 추출:
- 행정기관·국가 권한 규정 → 빈 배열 []
- 정의·목적·적용범위 → []
- 사업장이 직접 이행해야 하는 의무만

응답은 순수 JSON 배열만. 마크다운/설명 금지. 의무 없으면 [].

각 룰 스키마:
{
  "draft_rule_id": "예: DSAFE-013-CMN (영문코드-번호-섹터약자)",
  "obligation_type": "APPOINT|INSPECT|NOTIFY|REPORT|ACTION",
  "sector": "BUILDING|MANUFACTURING|CONSTRUCTION|COMMON|CONSTRUCTION_MANUFACTURING",
  "condition_code": "worker_count" or null,
  "condition_operator": ">=|>|<=|<|=" or null,
  "condition_value": "50" or null,
  "obligation_summary": "한국어 요약 1~2문장",
  "penalty_summary": "위반 시 ... 과태료" or null,
  "appointment_target": "안전관리자" or null,
  "diagnosis_stage": "INITIAL|PERIODIC|RENEWAL",
  "ai_confidence": 0-100,
  "ai_reasoning": "추출 근거 (어느 항/호 기반인지)"
}
"""

PHASE1_USER_TEMPLATE = """다음 법령 조문에서 사업장 의무를 추출하세요.

법령명: {law_name}
조문번호: 제{article_no}조{article_sub_str} {article_title}
조문 본문:
{article_text}
"""


# ──────────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────────
def extract_json_array(text: str) -> list[dict]:
    """Claude 응답에서 JSON 배열 추출 (마크다운 안전)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return []


def safe_numeric(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if re.match(r"^-?\d+\.?\d*$", s):
        try:
            return float(s)
        except (ValueError, TypeError):
            return None
    return None


# ──────────────────────────────────────────────────────────────
# Phase 1: 로컬 직접 파싱
# ──────────────────────────────────────────────────────────────
async def fetch_pending_articles(supabase: Client, limit: int | None = None) -> list[dict]:
    """ai_parsed_at NULL + 본문 길이 >= 20 인 article + 법령명."""
    q = (
        supabase.table("law_article")
        .select("id, article_no, article_sub_no, article_title, article_text, law_version_id")
        .is_("ai_parsed_at", "null")
    )
    if limit:
        q = q.limit(limit * 3)  # 길이 필터로 일부 빠질 수 있어 여유 잡기
    res = q.execute()
    articles = res.data or []

    # 길이 >= 20 필터 (Python 단)
    articles = [a for a in articles if a.get("article_text") and len(a["article_text"]) >= 20]

    # law_name 매핑 (version_id → law_master.law_name)
    if not articles:
        return []
    version_ids = list({a["law_version_id"] for a in articles if a.get("law_version_id")})
    versions = (
        supabase.table("law_version")
        .select("id, law_id")
        .in_("id", version_ids)
        .execute()
        .data
        or []
    )
    law_ids = list({v["law_id"] for v in versions})
    laws = (
        supabase.table("law_master")
        .select("id, law_name")
        .in_("id", law_ids)
        .execute()
        .data
        or []
    )
    v_to_law = {v["id"]: v["law_id"] for v in versions}
    l_to_name = {l["id"]: l["law_name"] for l in laws}
    for a in articles:
        a["law_name"] = l_to_name.get(v_to_law.get(a["law_version_id"], ""), "(unknown)")

    if limit:
        articles = articles[:limit]
    return articles


async def parse_one_article(
    claude: AsyncAnthropic, article: dict
) -> tuple[bool, list[dict], str | None]:
    """1개 article → Claude → 룰 리스트. (성공여부, 룰들, 에러)."""
    sub_str = (
        f"의{article['article_sub_no']}"
        if article.get("article_sub_no")
        else ""
    )
    user_prompt = PHASE1_USER_TEMPLATE.format(
        law_name=article["law_name"],
        article_no=article.get("article_no", "?"),
        article_sub_str=sub_str,
        article_title=article.get("article_title", "") or "",
        article_text=(article.get("article_text") or "")[:3500],
    )
    last_err = None
    for attempt in range(RETRY_LIMIT + 1):
        try:
            msg = await claude.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=PHASE1_SYSTEM,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = "".join(b.text for b in msg.content if hasattr(b, "text"))
            rules = extract_json_array(text)
            return True, rules, None
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:150]}"
            if attempt < RETRY_LIMIT:
                await asyncio.sleep(2)
    return False, [], last_err


def write_drafts_and_master(
    supabase: Client,
    article: dict,
    rules: list[dict],
    dry_run: bool,
) -> dict:
    """drafts INSERT + (조건 충족 시) master INSERT + ai_parsed_at 업데이트."""
    stats = {"drafts": 0, "approved": 0, "master": 0}

    for r in rules:
        if not isinstance(r, dict):
            continue
        cond_code = r.get("condition_code")
        confidence = r.get("ai_confidence", 0) or 0
        auto_approve = (
            confidence >= AUTO_APPROVE_THRESHOLD
            and cond_code
            and isinstance(cond_code, str)
        )

        draft_payload = {
            "draft_rule_id": r.get("draft_rule_id"),
            "law_name": article["law_name"],
            "law_article": f"제{article.get('article_no')}조",
            "article_id": article["id"],
            "article_text": (article.get("article_text") or "")[:3000],
            "obligation_type": r.get("obligation_type"),
            "sector": r.get("sector"),
            "condition_code": cond_code,
            "condition_operator": r.get("condition_operator"),
            "condition_value": str(r.get("condition_value")) if r.get("condition_value") is not None else None,
            "obligation_summary": r.get("obligation_summary"),
            "penalty_summary": r.get("penalty_summary"),
            "appointment_target": r.get("appointment_target"),
            "diagnosis_stage": r.get("diagnosis_stage"),
            "ai_confidence": int(confidence),
            "ai_reasoning": r.get("ai_reasoning"),
            "raw_ai_response": json.dumps(r, ensure_ascii=False),
            "status": "APPROVED" if auto_approve else "PENDING",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if dry_run:
            log.info(f"[DRY-RUN] draft={draft_payload['draft_rule_id']} status={draft_payload['status']} type={r.get('obligation_type')} sector={r.get('sector')}")
            stats["drafts"] += 1
            if auto_approve:
                stats["approved"] += 1
            continue

        try:
            supabase.table("law_rule_drafts").insert(draft_payload).execute()
            stats["drafts"] += 1
        except Exception as e:
            log.warning(f"draft insert 실패 ({draft_payload['draft_rule_id']}): {e}")
            continue

        if auto_approve:
            stats["approved"] += 1
            master_payload = {
                "rule_id": draft_payload["draft_rule_id"],
                "law_name": article["law_name"],
                "law_article": draft_payload["law_article"],
                "obligation_type": r.get("obligation_type"),
                "sector": r.get("sector"),
                "condition_code": cond_code,
                "condition_operator_code": r.get("condition_operator"),
                "condition_value": safe_numeric(r.get("condition_value")),
                "obligation_summary": r.get("obligation_summary"),
                "penalty_summary": r.get("penalty_summary"),
                "remarks": r.get("ai_reasoning") or r.get("obligation_summary"),
                "executor_type_code": "SAFETY_MANAGER",
                "is_active": True,
                "needs_review": False,
                "source_api": "AI_GENERATED",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                supabase.table("master_building_legal_rules").upsert(
                    master_payload, on_conflict="rule_id"
                ).execute()
                stats["master"] += 1
            except Exception as e:
                log.warning(f"master upsert 실패 ({draft_payload['draft_rule_id']}): {e}")

    # ai_parsed_at = now() (의무 0개여도 파싱 완료로 표시)
    if not dry_run:
        try:
            supabase.table("law_article").update(
                {"ai_parsed_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", article["id"]).execute()
        except Exception as e:
            log.warning(f"ai_parsed_at 업데이트 실패 ({article['id']}): {e}")

    return stats


async def run_phase1(
    supabase: Client,
    claude: AsyncAnthropic,
    concurrency: int,
    dry_run: bool,
    limit: int | None,
) -> dict:
    log.info("=" * 60)
    log.info("Phase 1 시작 — 갭 B + C (Claude Sonnet 직접 호출)")
    log.info("=" * 60)

    articles = await fetch_pending_articles(supabase, limit)
    log.info(f"대상 article: {len(articles)}건")
    if not articles:
        return {"ok": 0, "fail": 0, "drafts": 0, "approved": 0, "master": 0}

    sem = asyncio.Semaphore(concurrency)
    totals = {"ok": 0, "fail": 0, "drafts": 0, "approved": 0, "master": 0}

    async def worker(art: dict):
        async with sem:
            ok, rules, err = await parse_one_article(claude, art)
            if not ok:
                totals["fail"] += 1
                log.warning(f"[{art['law_name'][:20]}/제{art.get('article_no')}조] 실패: {err}")
                return
            stats = await asyncio.to_thread(
                write_drafts_and_master, supabase, art, rules, dry_run
            )
            totals["ok"] += 1
            totals["drafts"] += stats["drafts"]
            totals["approved"] += stats["approved"]
            totals["master"] += stats["master"]

    tasks = [worker(a) for a in articles]
    await atqdm.gather(*tasks, desc="Phase 1 (parse)")

    log.info(
        f"Phase 1 완료 — 처리 {totals['ok']}, 실패 {totals['fail']}, "
        f"drafts +{totals['drafts']}, 자동승인 {totals['approved']}, master +{totals['master']}"
    )
    return totals


# ──────────────────────────────────────────────────────────────
# Phase 2: Railway /reparse-master sector 별 호출 + 폴링
# ──────────────────────────────────────────────────────────────
async def trigger_reparse(
    client: httpx.AsyncClient, sector: str, limit: int, secret: str
) -> str | None:
    payload = {
        "secret": secret,
        "sector": sector,
        "limit": limit,
        "fill_empty_only": True,
    }
    headers = {"X-Internal-Secret": secret, "Content-Type": "application/json"}
    try:
        r = await client.post(
            f"{API_URL}/law-rule-generator/reparse-master",
            json=payload,
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("data", {}).get("job_id") or data.get("job_id")
    except Exception as e:
        log.error(f"[{sector}] reparse 시작 실패: {e}")
        return None


async def poll_reparse(
    client: httpx.AsyncClient, job_id: str, secret: str, sector: str, max_minutes: int = 60
) -> dict:
    headers = {"X-Internal-Secret": secret}
    deadline = asyncio.get_event_loop().time() + max_minutes * 60
    last_progress = -1
    while asyncio.get_event_loop().time() < deadline:
        try:
            r = await client.get(
                f"{API_URL}/law-rule-generator/reparse-master/status/{job_id}",
                headers=headers,
                timeout=15,
            )
            data = r.json().get("data", r.json())
            status = data.get("status")
            processed = data.get("processed", 0)
            total = data.get("total", 0) or data.get("limit", 0)
            modified = data.get("modified", 0)
            if processed != last_progress:
                pct = (processed / total * 100) if total else 0
                log.info(
                    f"[{sector}] {status} {processed}/{total} ({pct:.0f}%) 수정 {modified}"
                )
                last_progress = processed
            if status in ("COMPLETED", "FAILED"):
                return data
        except Exception as e:
            log.warning(f"[{sector}] status 폴링 에러 (재시도): {e}")
        await asyncio.sleep(20)
    log.error(f"[{sector}] 타임아웃 ({max_minutes}분)")
    return {"status": "TIMEOUT"}


async def run_phase2(secret: str, dry_run: bool) -> dict:
    log.info("=" * 60)
    log.info("Phase 2 시작 — 갭 E (Railway /reparse-master sector 순차)")
    log.info("=" * 60)

    if dry_run:
        log.info("[DRY-RUN] Phase 2 스킵")
        return {"sectors": []}

    sectors = [
        ("COMMON", 400),
        ("BUILDING", 260),
        ("MANUFACTURING", 100),
        ("CONSTRUCTION", 60),
    ]

    results = []
    async with httpx.AsyncClient() as client:
        for sector, limit in sectors:
            log.info(f"[{sector}] reparse 시작 (limit={limit})")
            job_id = await trigger_reparse(client, sector, limit, secret)
            if not job_id:
                results.append({"sector": sector, "status": "START_FAILED"})
                continue
            log.info(f"[{sector}] job_id={job_id}, 폴링 시작")
            res = await poll_reparse(client, job_id, secret, sector)
            res["sector"] = sector
            results.append(res)
            log.info(f"[{sector}] 종료: status={res.get('status')} 수정={res.get('modified')}")
            await asyncio.sleep(5)  # sector 간 휴식

    return {"sectors": results}


# ──────────────────────────────────────────────────────────────
# 스코어카드 (전후 비교용)
# ──────────────────────────────────────────────────────────────
def snapshot(supabase: Client) -> dict:
    out = {}
    out["활성 룰"] = (
        supabase.table("master_building_legal_rules")
        .select("id", count="exact")
        .eq("is_active", True)
        .execute()
        .count
    )
    out["커버 법령"] = len(
        {
            r["law_name"]
            for r in supabase.table("master_building_legal_rules")
            .select("law_name")
            .eq("is_active", True)
            .execute()
            .data
            or []
        }
    )
    rules = (
        supabase.table("master_building_legal_rules")
        .select("penalty_summary, condition_code, executor_type_code")
        .eq("is_active", True)
        .execute()
        .data
        or []
    )
    if rules:
        n = len(rules)
        out["penalty 채움률"] = (
            f"{100 * sum(1 for r in rules if r.get('penalty_summary')) / n:.1f}%"
        )
        out["condition 채움률"] = (
            f"{100 * sum(1 for r in rules if r.get('condition_code')) / n:.1f}%"
        )
    out["미파싱 article"] = (
        supabase.table("law_article")
        .select("id", count="exact")
        .is_("ai_parsed_at", "null")
        .execute()
        .count
    )
    return out


# ──────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────
async def main_async(args):
    log.info("=" * 60)
    log.info(f"finalize_law_pipeline 시작 (run_ts={RUN_TS})")
    log.info(f"phase={args.phase} dry_run={args.dry_run} limit={args.limit} concurrency={args.concurrency}")
    log.info(f"로그 파일: {LOG_FILE}")
    log.info("=" * 60)

    # 환경변수 (여러 이름 폴백)
    sb_url = env_first("SUPABASE_URL")
    sb_key = env_first("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY")
    log.info(f"Supabase URL: {sb_url}")
    log.info(f"Supabase Key: {mask(sb_key)} (앞 12자만 표시)")

    supabase: Client = create_client(sb_url, sb_key)

    log.info("\n=== BEFORE 스냅샷 ===")
    try:
        before = snapshot(supabase)
        for k, v in before.items():
            log.info(f"  {k}: {v}")
    except Exception as e:
        log.error(f"스냅샷 실패 (Supabase 연결 또는 권한 확인): {e}")
        log.error("→ SUPABASE_KEY 가 service_role 인지 확인하세요. anon 키는 RLS 때문에 master 쓰기 불가.")
        return 1

    tasks = []
    if args.phase in ("1", "all"):
        ant_key = env_first("ANTHROPIC_API_KEY")
        log.info(f"Anthropic Key: {mask(ant_key)}")
        claude = AsyncAnthropic(api_key=ant_key)
        tasks.append(
            ("phase1", run_phase1(supabase, claude, args.concurrency, args.dry_run, args.limit))
        )
    if args.phase in ("2", "all"):
        secret = env_first("INTERNAL_API_SECRET")
        log.info(f"Internal Secret: {mask(secret)}")
        tasks.append(("phase2", run_phase2(secret, args.dry_run)))

    if not tasks:
        log.error("실행할 phase 없음")
        return 1

    log.info(f"\n병렬 실행: {[name for name, _ in tasks]}")
    results = await asyncio.gather(*[t for _, t in tasks], return_exceptions=True)

    log.info("\n=== Phase 결과 ===")
    for (name, _), res in zip(tasks, results):
        if isinstance(res, Exception):
            log.error(f"[{name}] 예외: {res}")
        else:
            log.info(f"[{name}] {res}")

    log.info("\n=== AFTER 스냅샷 ===")
    after = snapshot(supabase)
    for k, v in after.items():
        b = before.get(k)
        diff = ""
        try:
            if isinstance(v, int) and isinstance(b, int):
                diff = f" ({v - b:+d})"
            elif isinstance(v, str) and v.endswith("%") and isinstance(b, str) and b.endswith("%"):
                diff = f" ({float(v[:-1]) - float(b[:-1]):+.1f}%p)"
        except Exception:
            pass
        log.info(f"  {k}: {b} → {v}{diff}")

    log.info(f"\n완료. 로그: {LOG_FILE}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="법령엔진 마무리 통합 스크립트")
    parser.add_argument("--phase", choices=["1", "2", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Phase 1 article 제한")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
