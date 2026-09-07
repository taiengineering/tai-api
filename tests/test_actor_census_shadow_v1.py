"""WO-ACTOR-SHADOW-INTEGRATION-IMPLEMENT-001 regression.

R1 CONTROL: flag off/on 시 shadow_lookup은 legal result를 바꾸지 않는다(어댑터는 순수 관측).
R2 OUTSIDE: 현 OUTSIDE atom → OUTSIDE_ACTOR_CENSUS_SCOPE, NOT_APPLICABLE 전환 없음.
R3 MATCHED: 274f72ca… → family_root 30521086… (frozen census exact).
R4 MATCHED2: 625e6e77… → faf34817….
R5 FAILURE ISOLATION: 로드 실패 강제 → shadow None, 예외 없음(진단 계속).
R6 POPULATION: 337/2/335/0/0.
"""
import importlib
import json
import os

import pytest

import services.actor_census_shadow as sh

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "actor_census")


def _reset():
    sh._STATE.update({"loaded": False, "ok": False, "map": {}, "manifest": {}})


def _enable(monkeypatch):
    monkeypatch.setenv("ACTOR_CENSUS_SHADOW_ENABLED", "true")
    _reset()


def test_R6_population_contract():
    manifest = json.load(open(os.path.join(DATA, "manifest.json"), encoding="utf-8"))
    c = manifest["counts"]
    assert c["TOTAL_ATOMS"] == 337
    assert c["MATCHED_ACTOR_CENSUS"] == 2
    assert c["OUTSIDE_ACTOR_CENSUS_SCOPE"] == 335
    assert c["ACTOR_CENSUS_ROW_MISSING"] == 0
    assert c["ATOM_MAPPING_BROKEN"] == 0
    assert manifest["actor_census_sha256"] == "3a6965d07ff156e89c7a9f9ec31adaff49143f6826fdc12666b2a0dad7328628"


def test_R1_control_disabled_returns_none(monkeypatch):
    monkeypatch.delenv("ACTOR_CENSUS_SHADOW_ENABLED", raising=False)
    _reset()
    assert sh.is_enabled() is False
    assert sh.shadow_lookup([{"atom_id": "274f72ca-8a26-5da6-8937-c1b5e340dcee"}]) is None


def test_R3_matched(monkeypatch):
    _enable(monkeypatch)
    out = sh.shadow_lookup([{"atom_id": "274f72ca-8a26-5da6-8937-c1b5e340dcee"}])
    assert out is not None
    r = out["records"][0]
    assert r["shadow_status"] == sh.MATCHED
    assert r["family_root_id"] == "30521086-854c-4391-8711-f9a31cf13d63"
    assert out["actor_census_sha256"] == "3a6965d07ff156e89c7a9f9ec31adaff49143f6826fdc12666b2a0dad7328628"


def test_R4_matched2(monkeypatch):
    _enable(monkeypatch)
    out = sh.shadow_lookup([{"atom_id": "625e6e77-6c76-5231-b707-f5155824a67a"}])
    r = out["records"][0]
    assert r["shadow_status"] == sh.MATCHED
    assert r["family_root_id"] == "faf34817-ab56-47a5-9341-2808bdfe50b8"


def test_R2_outside(monkeypatch):
    _enable(monkeypatch)
    # 006c122a… = 실측 OUTSIDE atom
    out = sh.shadow_lookup([{"atom_id": "006c122a-8b95-5c40-b225-b8c4639280c4"}])
    r = out["records"][0]
    assert r["shadow_status"] == sh.OUTSIDE
    assert r["family_root_id"] is None
    # OUTSIDE는 NOT_APPLICABLE/PASS/FAIL 아님
    assert r["shadow_status"] not in ("NOT_APPLICABLE", "PASS", "FAIL", "REVIEW", "ERROR")


def test_R5_failure_isolation(monkeypatch):
    _enable(monkeypatch)
    # 로드 강제 실패: manifest 경로를 존재하지 않게 monkeypatch
    monkeypatch.setattr(sh, "_MANIFEST_PATH", "/nonexistent/manifest.json")
    out = sh.shadow_lookup([{"atom_id": "274f72ca-8a26-5da6-8937-c1b5e340dcee"}])
    assert out is None  # shadow 비활성이나 예외 없음(진단 계속 가능)


def test_R5b_exception_never_raises(monkeypatch):
    _enable(monkeypatch)
    # obligations에 비정상 입력을 줘도 예외가 밖으로 나가지 않는다
    out = sh.shadow_lookup([{"atom_id": None}, {}])
    # broken 관측이거나 None(비활성)일 수 있으나 예외는 없어야 한다
    assert out is None or "records" in out
