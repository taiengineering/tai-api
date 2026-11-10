"""WO-DOC-G7-B1 Work A — doc_rule_supplier 단위 테스트.

RS-01: DOC_RULE_CONFIG_PATH 미설정 → config_missing
RS-02: 파일 없음 → config_not_found
RS-03: JSON 파싱 오류 → config_invalid
RS-04: JSON 객체 아님(배열) → config_invalid
RS-05: owner_approved=false → unapproved_config
RS-06: owner_approved 필드 없음 → unapproved_config
RS-07: contract_registered=false → unverified_contract
RS-08: contract_id 빈 문자열 → config_invalid
RS-09: approved_rule_version 없음 → missing_approval_version
RS-10: target_field_ids 빈 배열 → config_invalid
RS-11: grouping_config 문자열(비딕셔너리) → config_invalid
RS-12: rules 빈 배열 → no_active_rules
RS-13: rules 전부 'draft' → no_active_rules
RS-14: rules 혼합(active+draft) → active 규칙만 반환, DocRuleConfig 정상
RS-15: 유효한 전체 설정 → DocRuleConfig 모든 필드 확인
RS-16: rule_version 불일치 → config_invalid  (D-R5 교차 검증)
RS-17: target.contract_id 불일치 → config_invalid  (D-R5 교차 검증)
RS-18: grouping_config.contract_id 불일치 → config_invalid  (D-R5 교차 검증)
RS-19: DOC_RULE_APPROVED_SHA256 미설정 → unapproved_digest  (R1-01)
RS-20: SHA256 불일치 → unapproved_digest  (R1-01)
RS-21: SHA256 일치 + 유효 설정 → PASS  (R1-01)
RS-22: 활성 규칙 target 비-dict → config_invalid  (R1-02)
RS-23: grouping_config mode 없음 → config_invalid  (R1-02)
RS-24: EXPLICIT_KEY 모드 key_field 없음 → config_invalid  (R1-02)

Production DB write = 0 (파일 I/O + 환경변수 조작만).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile

import pytest

from services.doc_rule_supplier import (
    DocRuleConfig,
    DocRuleSupplyError,
    load_rule_config,
)


# ── 최소 유효 설정 픽스처 ─────────────────────────────────────────────────────

def _valid_rule() -> dict:
    return {
        "rule_id": "r-001",
        "rule_version": "v1.0.0",
        "status": "active",
        "source": {"field_path": "공장명", "field_type": "string"},
        "target": {"contract_id": "CT-TEST-V1", "field_path": "name", "field_type": "string"},
        "transform": {"type": "direct_copy"},
        "null_handling": {"source_missing_strategy": "error", "required": True},
    }


def _valid_config() -> dict:
    return {
        "owner_approved": True,
        "approved_at": "2026-11-10",
        "approved_rule_version": "v1.0.0",
        "contract_id": "CT-TEST-V1",
        "contract_registered": True,
        "target_field_ids": ["name"],
        "grouping_config": {
            "contract_id": "CT-TEST-V1",
            "mode": "EXPLICIT_KEY",
            "key_field": "name",
            "field_roles": [],
        },
        "rules": [_valid_rule()],
    }


def _write_config(cfg) -> str:
    """임시 파일에 JSON을 UTF-8 bytes로 저장 후 경로 반환."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "wb") as f:
        f.write(json.dumps(cfg, ensure_ascii=False).encode("utf-8"))
    return path


def _sha256_file(path: str) -> str:
    """파일 내용의 SHA256 hex digest 반환."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ── RS-01: 환경변수 미설정 ─────────────────────────────────────────────────────

def test_RS01_missing_env(monkeypatch):
    monkeypatch.delenv("DOC_RULE_CONFIG_PATH", raising=False)
    monkeypatch.delenv("DOC_RULE_APPROVED_SHA256", raising=False)
    with pytest.raises(DocRuleSupplyError) as exc:
        load_rule_config()
    assert exc.value.code == "config_missing"


# ── RS-02: 파일 없음 ──────────────────────────────────────────────────────────

def test_RS02_file_not_found(monkeypatch):
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", "/nonexistent/path/rules.json")
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", "a" * 64)
    with pytest.raises(DocRuleSupplyError) as exc:
        load_rule_config()
    assert exc.value.code == "config_not_found"


# ── RS-03: JSON 파싱 오류 ─────────────────────────────────────────────────────

def test_RS03_invalid_json(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".json")
    content = b"not-valid-json{{{"
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    sha256 = hashlib.sha256(content).hexdigest()
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "config_invalid"
    finally:
        os.unlink(path)


# ── RS-04: JSON 배열(객체 아님) ───────────────────────────────────────────────

def test_RS04_json_array(monkeypatch):
    path = _write_config([{"owner_approved": True}])
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "config_invalid"
    finally:
        os.unlink(path)


# ── RS-05: owner_approved=false ───────────────────────────────────────────────

def test_RS05_owner_approved_false(monkeypatch):
    cfg = _valid_config()
    cfg["owner_approved"] = False
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "unapproved_config"
    finally:
        os.unlink(path)


# ── RS-06: owner_approved 필드 없음 ──────────────────────────────────────────

def test_RS06_owner_approved_missing(monkeypatch):
    cfg = _valid_config()
    del cfg["owner_approved"]
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "unapproved_config"
    finally:
        os.unlink(path)


# ── RS-07: contract_registered=false ─────────────────────────────────────────

def test_RS07_contract_not_registered(monkeypatch):
    cfg = _valid_config()
    cfg["contract_registered"] = False
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "unverified_contract"
    finally:
        os.unlink(path)


# ── RS-08: contract_id 빈 문자열 ─────────────────────────────────────────────

def test_RS08_empty_contract_id(monkeypatch):
    cfg = _valid_config()
    cfg["contract_id"] = "   "
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "config_invalid"
    finally:
        os.unlink(path)


# ── RS-09: approved_rule_version 없음 ────────────────────────────────────────

def test_RS09_missing_rule_version(monkeypatch):
    cfg = _valid_config()
    del cfg["approved_rule_version"]
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "missing_approval_version"
    finally:
        os.unlink(path)


# ── RS-10: target_field_ids 빈 배열 ──────────────────────────────────────────

def test_RS10_empty_target_field_ids(monkeypatch):
    cfg = _valid_config()
    cfg["target_field_ids"] = []
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "config_invalid"
    finally:
        os.unlink(path)


# ── RS-11: grouping_config 비딕셔너리 ─────────────────────────────────────────

def test_RS11_grouping_config_not_dict(monkeypatch):
    cfg = _valid_config()
    cfg["grouping_config"] = "EXPLICIT_KEY"
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "config_invalid"
    finally:
        os.unlink(path)


# ── RS-12: rules 빈 배열 ──────────────────────────────────────────────────────

def test_RS12_empty_rules(monkeypatch):
    cfg = _valid_config()
    cfg["rules"] = []
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "no_active_rules"
    finally:
        os.unlink(path)


# ── RS-13: rules 전부 'draft' ─────────────────────────────────────────────────

def test_RS13_all_draft_rules(monkeypatch):
    cfg = _valid_config()
    cfg["rules"] = [
        {**_valid_rule(), "status": "draft"},
        {**_valid_rule(), "rule_id": "r-002", "status": "review"},
    ]
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "no_active_rules"
    finally:
        os.unlink(path)


# ── RS-14: rules 혼합 → active만 반환 ─────────────────────────────────────────

def test_RS14_mixed_rules_active_only(monkeypatch):
    cfg = _valid_config()
    cfg["rules"] = [
        _valid_rule(),
        {**_valid_rule(), "rule_id": "r-002", "status": "draft"},
        {**_valid_rule(), "rule_id": "r-003", "status": "deprecated"},
    ]
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        result = load_rule_config()
        assert len(result.rules) == 1
        assert result.rules[0]["rule_id"] == "r-001"
        assert result.rules[0]["status"] == "active"
    finally:
        os.unlink(path)


# ── RS-15: 유효한 전체 설정 ───────────────────────────────────────────────────

def test_RS15_valid_full_config(monkeypatch):
    cfg = _valid_config()
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        result = load_rule_config()
        assert isinstance(result, DocRuleConfig)
        assert result.contract_id == "CT-TEST-V1"
        assert result.approved_rule_version == "v1.0.0"
        assert result.target_field_ids == ["name"]
        assert result.grouping_config["mode"] == "EXPLICIT_KEY"
        assert len(result.rules) == 1
        assert result.rules[0]["status"] == "active"
    finally:
        os.unlink(path)


# ── RS-16: rule_version 불일치 (D-R5 교차 검증) ───────────────────────────────

def test_RS16_rule_version_mismatch(monkeypatch):
    cfg = _valid_config()
    cfg["rules"] = [{**_valid_rule(), "rule_version": "v0.9.0-draft"}]
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "config_invalid"
        assert "rule_version" in exc.value.detail
    finally:
        os.unlink(path)


# ── RS-17: target.contract_id 불일치 (D-R5 교차 검증) ────────────────────────

def test_RS17_target_contract_id_mismatch(monkeypatch):
    cfg = _valid_config()
    rule = _valid_rule()
    rule["target"] = {**rule["target"], "contract_id": "CT-OTHER-V1"}
    cfg["rules"] = [rule]
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "config_invalid"
        assert "target.contract_id" in exc.value.detail
    finally:
        os.unlink(path)


# ── RS-18: grouping_config.contract_id 불일치 (D-R5 교차 검증) ───────────────

def test_RS18_grouping_contract_id_mismatch(monkeypatch):
    cfg = _valid_config()
    cfg["grouping_config"] = {**cfg["grouping_config"], "contract_id": "CT-OTHER-V1"}
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "config_invalid"
        assert "grouping_config.contract_id" in exc.value.detail
    finally:
        os.unlink(path)


# ── RS-19: DOC_RULE_APPROVED_SHA256 미설정 (R1-01) ───────────────────────────

def test_RS19_approved_sha256_missing(monkeypatch):
    cfg = _valid_config()
    path = _write_config(cfg)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.delenv("DOC_RULE_APPROVED_SHA256", raising=False)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "unapproved_digest"
    finally:
        os.unlink(path)


# ── RS-20: SHA256 불일치 (R1-01) ─────────────────────────────────────────────

def test_RS20_sha256_mismatch(monkeypatch):
    cfg = _valid_config()
    path = _write_config(cfg)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", "0" * 64)  # 의도적 불일치
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "unapproved_digest"
    finally:
        os.unlink(path)


# ── RS-21: SHA256 일치 + 유효 설정 → PASS (R1-01) ────────────────────────────

def test_RS21_sha256_match_valid_config(monkeypatch):
    cfg = _valid_config()
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        result = load_rule_config()
        assert isinstance(result, DocRuleConfig)
        assert result.contract_id == "CT-TEST-V1"
    finally:
        os.unlink(path)


# ── RS-22: 활성 규칙 target 비-dict (R1-02) ──────────────────────────────────

def test_RS22_rule_target_not_dict(monkeypatch):
    cfg = _valid_config()
    rule = _valid_rule()
    rule["target"] = "CT-TEST-V1"  # dict가 아닌 문자열
    cfg["rules"] = [rule]
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "config_invalid"
        assert "target" in exc.value.detail
    finally:
        os.unlink(path)


# ── RS-23: grouping_config mode 없음 (R1-02) ─────────────────────────────────

def test_RS23_grouping_config_mode_missing(monkeypatch):
    cfg = _valid_config()
    gc = dict(cfg["grouping_config"])
    del gc["mode"]
    cfg["grouping_config"] = gc
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "config_invalid"
        assert "mode" in exc.value.detail
    finally:
        os.unlink(path)


# ── RS-24: EXPLICIT_KEY 모드 key_field 없음 (R1-02) ──────────────────────────

def test_RS24_explicit_key_no_key_field(monkeypatch):
    cfg = _valid_config()
    gc = dict(cfg["grouping_config"])
    del gc["key_field"]
    cfg["grouping_config"] = gc
    path = _write_config(cfg)
    sha256 = _sha256_file(path)
    monkeypatch.setenv("DOC_RULE_CONFIG_PATH", path)
    monkeypatch.setenv("DOC_RULE_APPROVED_SHA256", sha256)
    try:
        with pytest.raises(DocRuleSupplyError) as exc:
            load_rule_config()
        assert exc.value.code == "config_invalid"
        assert "key_field" in exc.value.detail
    finally:
        os.unlink(path)
