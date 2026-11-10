"""services/doc_rule_supplier.py — 운영 규칙 공급 경계.

Owner 승인된 버전 관리 JSON 파일에서 운영 규칙 설정을 로드한다.
D-R3·D-R5 승인 범위 (2026-11-10).
WO: WO-DOC-G7-B1-APPROVED-CONNECTION-IMPLEMENTATION-001

차단 조건:
  config_missing:           DOC_RULE_CONFIG_PATH 미설정
  config_not_found:         JSON 파일 없음
  config_invalid:           JSON 파싱 오류 또는 필수 필드 형식 오류
  unapproved_config:        owner_approved ≠ true
  unapproved_digest:        DOC_RULE_APPROVED_SHA256 미설정 또는 파일 SHA256 불일치
  unverified_contract:      contract_registered ≠ true
  missing_approval_version: approved_rule_version 없음 또는 빈 문자열
  no_active_rules:          rules 없음, 빈 배열, 또는 active 규칙 0건

현재 운영 활성 계약:
  APPROVED_RULE_SET=NONE — 활성화된 운영 규칙 없음 (D-R2 계약 등록 대기)
  미승인 계약 사용 차단, 테스트 규칙 자동 활성화 차단.

DOC_RULE_APPROVED_SHA256:
  Owner가 특정 규칙 JSON 파일 버전을 승인한 뒤 배포 단계에서만 설정.
  JSON 파일 내부에서 자기 승인하는 방식 금지.
  이 값이 없거나 파일 SHA256과 불일치하면 로드 차단.

JSON 설정 파일 형식:
  {
    "owner_approved": true,
    "approved_at": "2026-11-10",
    "approved_rule_version": "v1.0.0",
    "contract_id": "CT-XXX-V1",
    "contract_registered": true,
    "target_field_ids": ["field_a", "field_b"],
    "grouping_config": {
      "contract_id": "CT-XXX-V1",
      "mode": "EXPLICIT_KEY",
      "key_field": "field_a",
      "field_roles": []
    },
    "rules": [
      {
        "rule_id": "r-001",
        "rule_version": "v1.0.0",
        "status": "active",
        "source": {"field_path": "원본컬럼명", "field_type": "string"},
        "target": {"contract_id": "CT-XXX-V1", "field_path": "field_a", "field_type": "string"},
        "transform": {"type": "direct_copy"},
        "null_handling": {"source_missing_strategy": "error", "required": true}
      }
    ]
  }

MAP-02의 JsonFileRuleRepository·fetchRuleSnapshot 기능을 대체하지 않는다.
이 모듈은 DOC 호출 전 공급 경계 검증에만 사용한다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

_ENV_CONFIG_PATH    = "DOC_RULE_CONFIG_PATH"
_ENV_APPROVED_SHA256 = "DOC_RULE_APPROVED_SHA256"


# ── 오류 계층 ──────────────────────────────────────────────────────────────────

class DocRuleSupplyError(Exception):
    """운영 규칙 공급 차단 — 모든 차단 조건은 이 예외로 raise된다."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


# ── 결과 모델 ──────────────────────────────────────────────────────────────────

@dataclass
class DocRuleConfig:
    """Owner 승인된 규칙 공급 설정.

    Attributes:
        contract_id:           대상 계약 ID (federation-contracts 등록 완료 필수)
        approved_rule_version: Owner 승인 버전 태그
        target_field_ids:      매핑 대상 필드 ID 목록
        grouping_config:       GroupingConfig-compatible dict (MAP-02 형식)
        rules:                 MappingRule-compatible dict 목록 (status='active' 한정)
    """
    contract_id: str
    approved_rule_version: str
    target_field_ids: list[str]
    grouping_config: dict[str, Any]
    rules: list[dict[str, Any]]


# ── 내부 검증 ─────────────────────────────────────────────────────────────────

def _validate(cfg: dict[str, Any]) -> DocRuleConfig:
    # D-R5: owner_approved=true 필수 — status='active'만으로 Owner 승인 불인정
    if cfg.get("owner_approved") is not True:
        raise DocRuleSupplyError(
            "unapproved_config",
            "owner_approved=true 없음 — 운영 규칙 사용 차단",
        )

    # D-R2: 계약 등록 확인
    if cfg.get("contract_registered") is not True:
        raise DocRuleSupplyError(
            "unverified_contract",
            "contract_registered=true 없음 — 미등록 계약 사용 차단",
        )

    contract_id = str(cfg.get("contract_id") or "").strip()
    if not contract_id:
        raise DocRuleSupplyError("config_invalid", "contract_id 누락")

    # D-R5: 승인 버전 필수 — 버전 없는 규칙 활성화 차단
    approved_rule_version = str(cfg.get("approved_rule_version") or "").strip()
    if not approved_rule_version:
        raise DocRuleSupplyError(
            "missing_approval_version",
            "approved_rule_version 없음 — 승인 버전 없이 운영 규칙 사용 차단",
        )

    tfi = cfg.get("target_field_ids")
    if not isinstance(tfi, list) or len(tfi) == 0:
        raise DocRuleSupplyError("config_invalid", "target_field_ids 없음 또는 빈 배열")

    gc = cfg.get("grouping_config")
    if not isinstance(gc, dict):
        raise DocRuleSupplyError("config_invalid", "grouping_config 없음 또는 형식 오류")

    # MAP-02 GroupingConfig 필수 항목: mode 존재, EXPLICIT_KEY 모드 → key_field 필수
    gc_mode = str(gc.get("mode") or "").strip()
    if not gc_mode:
        raise DocRuleSupplyError("config_invalid", "grouping_config.mode 없음")
    if gc_mode == "EXPLICIT_KEY":
        if not str(gc.get("key_field") or "").strip():
            raise DocRuleSupplyError(
                "config_invalid",
                "grouping_config.key_field 없음 (EXPLICIT_KEY 모드 필수)",
            )

    raw_rules = cfg.get("rules")
    if not isinstance(raw_rules, list) or len(raw_rules) == 0:
        raise DocRuleSupplyError("no_active_rules", "rules 없음 또는 빈 배열")

    active_rules = [r for r in raw_rules if isinstance(r, dict) and r.get("status") == "active"]
    if not active_rules:
        raise DocRuleSupplyError(
            "no_active_rules",
            "active 상태 규칙 없음 — 운영 규칙 사용 차단",
        )

    # D-R5: grouping_config.contract_id 교차 검증
    gc_contract = str(gc.get("contract_id") or "").strip()
    if gc_contract != contract_id:
        raise DocRuleSupplyError(
            "config_invalid",
            f"grouping_config.contract_id({gc_contract!r}) ≠ contract_id({contract_id!r})",
        )

    # D-R5: 각 active 규칙의 버전·계약·target 형식 교차 검증
    for rule in active_rules:
        rid = rule.get("rule_id", "?")

        rv = str(rule.get("rule_version") or "").strip()
        if rv != approved_rule_version:
            raise DocRuleSupplyError(
                "config_invalid",
                f"규칙 {rid!r}의 rule_version({rv!r}) ≠ approved_rule_version({approved_rule_version!r})",
            )

        tgt = rule.get("target")
        if not isinstance(tgt, dict):
            raise DocRuleSupplyError(
                "config_invalid",
                f"규칙 {rid!r}의 target이 사전형이 아님",
            )

        tgt_contract = str(tgt.get("contract_id") or "").strip()
        if tgt_contract != contract_id:
            raise DocRuleSupplyError(
                "config_invalid",
                f"규칙 {rid!r}의 target.contract_id({tgt_contract!r}) ≠ contract_id({contract_id!r})",
            )

    return DocRuleConfig(
        contract_id=contract_id,
        approved_rule_version=approved_rule_version,
        target_field_ids=[str(f) for f in tfi if str(f).strip()],
        grouping_config=gc,
        rules=active_rules,
    )


# ── 공개 API ──────────────────────────────────────────────────────────────────

def load_rule_config() -> DocRuleConfig:
    """DOC_RULE_CONFIG_PATH에서 Owner 승인 운영 규칙 설정을 로드한다.

    Returns:
        DocRuleConfig — Owner 승인·파일 무결성·계약 등록·active 규칙이 모두 충족된 경우에만 반환

    Raises:
        DocRuleSupplyError: 차단 조건 중 하나라도 미충족 시
    """
    config_path = os.environ.get(_ENV_CONFIG_PATH, "").strip()
    if not config_path:
        raise DocRuleSupplyError(
            "config_missing",
            f"{_ENV_CONFIG_PATH} 미설정 — 운영 규칙 공급 불가",
        )

    # D-R5: 파일 로드 전 승인 식별값 존재 확인 (JSON 내부 자기 승인 방지)
    approved_sha256 = os.environ.get(_ENV_APPROVED_SHA256, "").strip().lower()
    if not approved_sha256:
        raise DocRuleSupplyError(
            "unapproved_digest",
            f"{_ENV_APPROVED_SHA256} 미설정 — 승인 식별값 없이 규칙 로드 차단",
        )

    try:
        with open(config_path, "rb") as f:
            raw_bytes = f.read()
    except FileNotFoundError:
        raise DocRuleSupplyError(
            "config_not_found",
            f"규칙 설정 파일 없음: {config_path}",
        )

    # D-R5: 파일 SHA256과 승인 식별값 비교
    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest().lower()
    if actual_sha256 != approved_sha256:
        raise DocRuleSupplyError(
            "unapproved_digest",
            "규칙 파일 SHA256 불일치 — 승인 외 파일 로드 차단",
        )

    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise DocRuleSupplyError(
            "config_invalid",
            f"규칙 설정 JSON 파싱 오류: {exc}",
        )

    if not isinstance(raw, dict):
        raise DocRuleSupplyError("config_invalid", "규칙 설정 파일이 JSON 객체가 아님")

    return _validate(raw)
