"""GitHub Actions Dispatch — WO-QA-CONTROL-PHASE2E-001 / WO-QA-CROSS-REPO-CONDITIONAL-CONTRACT-001.

tai-qa workflow_dispatch: run_id + scenario_ids + allow_conditional 전달.

Secret contract:
  QA_GITHUB_TOKEN   — PAT with workflow scope (절대 log 출력 금지)
  QA_GITHUB_OWNER   — repo 소유자 (default: taiengineering)
  QA_GITHUB_REPO    — tai-qa repo name (default: tai-qa)
  QA_GITHUB_WORKFLOW — workflow file id (default: p0-smoke.yml)
  QA_GITHUB_REF     — branch to dispatch on (default: main)
"""
from __future__ import annotations

import logging
import os
from typing import List

import httpx

log = logging.getLogger("github_dispatch")

_GITHUB_API = "https://api.github.com"


def _cfg() -> dict:
    token = os.environ.get("QA_GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("QA_GITHUB_TOKEN 미설정 — GitHub dispatch 불가")
    return {
        "token":    token,
        "owner":    os.environ.get("QA_GITHUB_OWNER", "taiengineering"),
        "repo":     os.environ.get("QA_GITHUB_REPO", "tai-qa"),
        "workflow": os.environ.get("QA_GITHUB_WORKFLOW", "p0-smoke.yml"),
        "ref":      os.environ.get("QA_GITHUB_REF", "main"),
    }


async def dispatch_qa_run(
    run_id: str,
    scenario_ids: List[str],
    *,
    allow_conditional: bool = False,
) -> None:
    """tai-qa workflow_dispatch 호출.

    allow_conditional: True = Admin 명시적 요청 (Manual path 전용).
                       False = 기본값 / Scheduler path (fail-close).
    실패 시 RuntimeError. 호출자가 run_status=ERROR 처리 담당.
    token은 절대 log에 출력하지 않는다.
    """
    cfg = _cfg()
    url = (
        f"{_GITHUB_API}/repos/{cfg['owner']}/{cfg['repo']}"
        f"/actions/workflows/{cfg['workflow']}/dispatches"
    )
    payload = {
        "ref": cfg["ref"],
        "inputs": {
            "run_id":            run_id,
            "scenario_ids":      ",".join(scenario_ids),
            "allow_conditional": "true" if allow_conditional else "false",
        },
    }
    headers = {
        "Authorization": f"Bearer {cfg['token']}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code not in (200, 204):
        # status / body 만 로그 — token 절대 포함 금지
        log.error(
            "[github_dispatch] dispatch failed: status=%s run_id=%s",
            resp.status_code, run_id,
        )
        raise RuntimeError(
            f"GitHub dispatch failed: HTTP {resp.status_code}"
        )

    log.info("[github_dispatch] dispatched: run_id=%s scenarios=%d", run_id, len(scenario_ids))
