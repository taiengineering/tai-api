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


# ── PATCH-1: R1 INTEGRATION deep-equal at run_leg_diagnosis level ──
def _fake_rtm_data():
    return {
        "status": "OK",
        "obligations": [
            {"atom_id": "274f72ca-8a26-5da6-8937-c1b5e340dcee", "law_name": "L1", "law_article": "1", "evidence": "e", "source_atom_ids": ["274f72ca-8a26-5da6-8937-c1b5e340dcee"]},
            {"atom_id": "006c122a-8b95-5c40-b225-b8c4639280c4", "law_name": "L2", "law_article": "2", "evidence": "e", "source_atom_ids": ["006c122a-8b95-5c40-b225-b8c4639280c4"]},
        ],
        "obligation_count": 2,
        "review_required": [],
        "provenance": {"x": 1},
        "contract": {"y": 2},
        "trace_id": "t-1",
    }


class _Body:
    sector = "MANUFACTURING"


def _run_full_result(monkeypatch, flag_value):
    import importlib
    import services.leg_diagnosis_svc as svc
    import clients.leg_runtime_client as client
    if flag_value is None:
        monkeypatch.delenv("ACTOR_CENSUS_SHADOW_ENABLED", raising=False)
    else:
        monkeypatch.setenv("ACTOR_CENSUS_SHADOW_ENABLED", flag_value)
    _reset()
    monkeypatch.setattr(client, "build_facility", lambda b: {"f": 1})
    monkeypatch.setattr(client, "evaluate_rtm", lambda facility, **kw: _fake_rtm_data())
    return svc.run_leg_diagnosis(_Body())


def test_R1_off_on_full_result_deep_equal(monkeypatch):
    off = _run_full_result(monkeypatch, None)
    on = _run_full_result(monkeypatch, "true")
    assert off == on, "shadow ON must not change full_result"
    # consumer/full_result에 shadow metadata가 없어야 함
    assert not any(str(k).lower().startswith("shadow") or "actor_shadow" in str(k).lower() for k in on.keys())


def test_R1_flag_off_no_file_io(monkeypatch):
    import services.actor_census_shadow as sh2
    monkeypatch.delenv("ACTOR_CENSUS_SHADOW_ENABLED", raising=False)
    _reset()
    calls = {"n": 0}
    orig = sh2._load
    def _spy():
        calls["n"] += 1
        return orig()
    monkeypatch.setattr(sh2, "_load", _spy)
    out = sh2.shadow_lookup([{"atom_id": "274f72ca-8a26-5da6-8937-c1b5e340dcee"}])
    assert out is None
    assert calls["n"] == 0, "flag OFF must not trigger loader/file IO"


# ── PATCH-2: frozen mapping SHA enforcement ──
def test_P2_expected_mapping_sha_constant():
    import services.actor_census_shadow as sh3
    assert sh3._EXPECTED_MAPPING_SHA == "3885cbf729772e58e0bd86e8d289e6fe8bbf58e5d768ca0dd90b520fc8edde1e"
    # 실제 map 파일 SHA도 frozen 상수와 일치해야 한다
    assert sh3._sha256_file(sh3._MAP_PATH) == sh3._EXPECTED_MAPPING_SHA


def test_P2_manifest_mapping_sha_tampered_disables(monkeypatch, tmp_path):
    import json, shutil, services.actor_census_shadow as sh3
    # data 디렉토리를 tmp로 복제 후 manifest의 mapping_sha256만 위조
    dst = tmp_path / "actor_census"
    shutil.copytree(sh3._DATA_DIR, dst)
    m = json.load(open(dst / "manifest.json", encoding="utf-8"))
    m["mapping_sha256"] = "0" * 64
    json.dump(m, open(dst / "manifest.json", "w", encoding="utf-8"))
    monkeypatch.setenv("ACTOR_CENSUS_SHADOW_ENABLED", "true")
    monkeypatch.setattr(sh3, "_DATA_DIR", str(dst))
    monkeypatch.setattr(sh3, "_MAP_PATH", str(dst / "actor_shadow_map_v1.jsonl"))
    monkeypatch.setattr(sh3, "_MANIFEST_PATH", str(dst / "manifest.json"))
    _reset()
    out = sh3.shadow_lookup([{"atom_id": "274f72ca-8a26-5da6-8937-c1b5e340dcee"}])
    assert out is None  # manifest 위조 → 3-way 불일치 → shadow disabled, 예외 없음


def test_P2_map_file_tampered_disables(monkeypatch, tmp_path):
    import json, shutil, services.actor_census_shadow as sh3
    dst = tmp_path / "actor_census"
    shutil.copytree(sh3._DATA_DIR, dst)
    # map 파일에 한 줄 추가(내용 변조) + manifest도 그 새 SHA로 맞춰줌(공모 시나리오)
    mp = dst / "actor_shadow_map_v1.jsonl"
    with open(mp, "a", encoding="utf-8") as f:
        f.write('{"atom_id": "00000000-0000-0000-0000-000000000000", "scope_status": "OUTSIDE_ACTOR_CENSUS_SCOPE", "family_root_id": null}\n')
    new_sha = sh3._sha256_file(str(mp))
    m = json.load(open(dst / "manifest.json", encoding="utf-8"))
    m["mapping_sha256"] = new_sha  # manifest도 공모 변경
    json.dump(m, open(dst / "manifest.json", "w", encoding="utf-8"))
    monkeypatch.setenv("ACTOR_CENSUS_SHADOW_ENABLED", "true")
    monkeypatch.setattr(sh3, "_DATA_DIR", str(dst))
    monkeypatch.setattr(sh3, "_MAP_PATH", str(mp))
    monkeypatch.setattr(sh3, "_MANIFEST_PATH", str(dst / "manifest.json"))
    _reset()
    out = sh3.shadow_lookup([{"atom_id": "274f72ca-8a26-5da6-8937-c1b5e340dcee"}])
    # manifest+map 공모 변경이어도 frozen 상수(_EXPECTED_MAPPING_SHA)와 불일치 → disabled
    assert out is None
