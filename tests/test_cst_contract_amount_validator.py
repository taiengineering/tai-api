"""WO-CST-CONTRACT-AMOUNT-VALIDATOR-FINAL-015 — site-level history + validator.

H1–H6 history · E1–E5 external · P1/P2 50억 요금 경계 · V1–V2 preservation.
"""
from types import SimpleNamespace

from services.construction_amount_validator import (
    MSG_CROSS_50_MISMATCH,
    MSG_DOWNWARD_RECHECK,
    MSG_UNVERIFIED,
    STATUS_CROSS_50_MISMATCH,
    STATUS_DOWNWARD_RECHECK,
    STATUS_PASS,
    STATUS_UNVERIFIED,
    fetch_external_contract_amount,
    fetch_same_site_amount_history,
    maybe_log_contract_amount_change,
    record_and_validate_site_amount,
    validate_contract_amount,
)
from services.diagnosis_helpers import _auto_tier
from services.construction_sites_svc import build_site_update_payload
from schemas.construction import SitePatch

SITE_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SITE_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class _LogQ:
    def __init__(self, store, fail=False):
        self.store = store
        self.fail = fail
        self._filters = {}
        self._ins = None
        self._order = None
        self.filter_log = store.setdefault("_filters_seen", [])

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        self.filter_log.append((col, val))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def insert(self, payload, *a, **k):
        if self.fail:
            raise RuntimeError("price_change_log unavailable")
        self._ins = dict(payload)
        self.store.setdefault("price_change_log", []).append(dict(payload))
        return self

    def execute(self):
        if self._ins is not None:
            return SimpleNamespace(data=[self._ins])
        rows = list(self.store.get("price_change_log") or [])
        for k, v in self._filters.items():
            rows = [r for r in rows if r.get(k) == v]
        if self._order:
            col, desc = self._order
            rows = sorted(rows, key=lambda r: r.get(col) or "", reverse=bool(desc))
        return SimpleNamespace(data=rows)


class _FakeSB:
    def __init__(self, fail_log=False):
        self.store = {"price_change_log": []}
        self.fail_log = fail_log

    def table(self, name):
        assert name == "price_change_log"
        return _LogQ(self.store, fail=self.fail_log)


def _ext(amount, confidence="HIGH", **kw):
    return {
        "amount_eok": amount,
        "confidence": confidence,
        "is_exact": kw.get("is_exact", True),
        "same_project": kw.get("same_project", True),
        "same_scope": kw.get("same_scope", True),
        "official_source": kw.get("official_source", True),
        "public_reference": kw.get("public_reference", False),
    }


def _hist(old, new, site=SITE_A, ts="2026-09-04T00:00:00+09:00"):
    return {
        "table_name": "construction_sites",
        "field_name": "contract_amount",
        "record_id": site,
        "old_value": str(old),
        "new_value": str(new),
        "changed_at": ts,
    }


# ── HISTORY ────────────────────────────────────────────────────────────────
def test_H1_80_to_49_logs_one_row():
    sb = _FakeSB()
    logged = maybe_log_contract_amount_change(
        sb, site_id=SITE_A, old_amount=80, new_amount=49, amount_in_patch=True,
        changed_by="11111111-1111-1111-1111-111111111111", now_iso="2026-09-04T01:00:00+09:00",
    )
    assert logged is True
    rows = sb.store["price_change_log"]
    assert len(rows) == 1
    assert rows[0]["table_name"] == "construction_sites"
    assert rows[0]["record_id"] == SITE_A
    assert rows[0]["field_name"] == "contract_amount"
    assert float(rows[0]["old_value"]) == 80
    assert float(rows[0]["new_value"]) == 49


def test_H2_same_value_49_to_49_no_log():
    sb = _FakeSB()
    logged = maybe_log_contract_amount_change(
        sb, site_id=SITE_A, old_amount=49, new_amount=49, amount_in_patch=True,
        changed_by=None, now_iso="2026-09-04T01:00:00+09:00",
    )
    assert logged is False
    assert sb.store["price_change_log"] == []


def test_H3_amount_absent_from_patch_no_log():
    sb = _FakeSB()
    logged = maybe_log_contract_amount_change(
        sb, site_id=SITE_A, old_amount=80, new_amount=80, amount_in_patch=False,
        changed_by=None, now_iso="2026-09-04T01:00:00+09:00",
    )
    assert logged is False
    assert sb.store["price_change_log"] == []


def test_H4_cross_site_firewall_no_downward_recheck():
    sb = _FakeSB()
    maybe_log_contract_amount_change(
        sb, site_id=SITE_A, old_amount=80, new_amount=49, amount_in_patch=True,
        changed_by=None, now_iso="2026-09-04T01:00:00+09:00",
    )
    hist_b = fetch_same_site_amount_history(sb, SITE_B)
    assert hist_b == []
    out = validate_contract_amount(49, hist_b)
    assert out["status"] != STATUS_DOWNWARD_RECHECK
    assert out["status"] == STATUS_UNVERIFIED
    cols = {c for c, _ in sb.store["_filters_seen"]}
    assert "company_id" not in cols
    assert "ci_hash" not in cols
    assert "record_id" in cols


def test_H5_same_site_80_to_49_downward_recheck():
    out = validate_contract_amount(49, [_hist(80, 49)])
    assert out["status"] == STATUS_DOWNWARD_RECHECK
    assert out["message"] == MSG_DOWNWARD_RECHECK
    assert out["user_contract_amount"] == 49
    assert out["metadata"]["previous"] == 80


def test_H6_same_site_40_to_30_not_downward_recheck():
    out = validate_contract_amount(30, [_hist(40, 30)])
    assert out["status"] != STATUS_DOWNWARD_RECHECK
    assert out["status"] == STATUS_UNVERIFIED


def test_downward_50_to_49_is_crossing():
    assert validate_contract_amount(49, [_hist(50, 49)])["status"] == STATUS_DOWNWARD_RECHECK


def test_80_to_60_not_crossing():
    assert validate_contract_amount(60, [_hist(80, 60)])["status"] != STATUS_DOWNWARD_RECHECK


# ── EXTERNAL ───────────────────────────────────────────────────────────────
def test_E1_user49_official_high_49_pass():
    out = validate_contract_amount(49, [], _ext(49))
    assert out["status"] == STATUS_PASS
    assert out["user_contract_amount"] == 49
    assert out["message"] is None


def test_E2_user49_official_high_80_cross_50():
    out = validate_contract_amount(49, [], _ext(80))
    assert out["status"] == STATUS_CROSS_50_MISMATCH
    assert out["message"] == MSG_CROSS_50_MISMATCH
    assert out["user_contract_amount"] == 49


def test_E3_user80_official_high_49_mismatch_no_overwrite():
    user = 80
    out = validate_contract_amount(user, [], _ext(49))
    assert out["status"] == STATUS_CROSS_50_MISMATCH
    assert out["user_contract_amount"] == 80
    assert out["user_contract_amount"] == user
    assert out["metadata"]["external"]["amount_eok"] == 49


def test_E4_low_confidence_not_cross_50_hard_status():
    out = validate_contract_amount(49, [], _ext(80, confidence="LOW"))
    assert out["status"] != STATUS_CROSS_50_MISMATCH
    assert out["status"] == STATUS_UNVERIFIED


def test_E5_no_external_unverified():
    out = validate_contract_amount(49, [])
    assert out["status"] == STATUS_UNVERIFIED
    assert out["message"] == MSG_UNVERIFIED


def test_external_provider_not_wired():
    assert fetch_external_contract_amount({"id": SITE_A, "contract_amount": 49}) is None


def test_priority_cross_50_beats_downward_recheck():
    out = validate_contract_amount(49, [_hist(80, 49)], _ext(80))
    assert out["status"] == STATUS_CROSS_50_MISMATCH


# ── POLICY 50eok (기존 _auto_tier, 무수정) ────────────────────────────────
def test_P1_49_standard():
    assert _auto_tier("CONSTRUCTION", 0.0, 49) == "CONSTRUCTION"


def test_P2_50_premium():
    assert _auto_tier("CONSTRUCTION", 0.0, 50) == "CONSTRUCTION_PREMIUM"


# ── PRESERVATION ───────────────────────────────────────────────────────────
def test_V1_validator_does_not_overwrite_user_amount():
    user = 49.0
    out = validate_contract_amount(user, [_hist(80, 49)], _ext(80))
    assert out["user_contract_amount"] == user
    payload = build_site_update_payload(
        SitePatch(contract_amount=49),
        {"site_type": "BUILDING", "contract_amount": 80, "total_workers": 10},
        lambda: "2026-09-04T00:00:00+09:00",
    )
    assert payload["contract_amount"] == 49


def test_V2_other_site_history_not_mixed():
    sb = _FakeSB()
    record_and_validate_site_amount(
        sb, site_id=SITE_A, old_amount=80, new_amount=49, amount_in_patch=True,
        changed_by=None, now_iso="2026-09-04T01:00:00+09:00",
    )
    out_b = record_and_validate_site_amount(
        sb, site_id=SITE_B, old_amount=40, new_amount=49, amount_in_patch=True,
        changed_by=None, now_iso="2026-09-04T01:01:00+09:00",
    )
    assert out_b["status"] != STATUS_DOWNWARD_RECHECK
    rows_a = [r for r in sb.store["price_change_log"] if r["record_id"] == SITE_A]
    rows_b = [r for r in sb.store["price_change_log"] if r["record_id"] == SITE_B]
    assert len(rows_a) == 1 and float(rows_a[0]["old_value"]) == 80
    assert len(rows_b) == 1 and float(rows_b[0]["old_value"]) == 40
    assert fetch_same_site_amount_history(sb, SITE_B)[0]["record_id"] == SITE_B


def test_log_insert_failure_does_not_raise():
    sb = _FakeSB(fail_log=True)
    logged = maybe_log_contract_amount_change(
        sb, site_id=SITE_A, old_amount=80, new_amount=49, amount_in_patch=True,
        changed_by=None, now_iso="2026-09-04T01:00:00+09:00",
    )
    assert logged is False
