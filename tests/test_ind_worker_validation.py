"""WO-IND-WORKER-API-VALIDATION-001 — 상시인원 검증 (실호출 없이 fixture).

T1–T10 compare · T11 XML select · T9 API_ERROR 진단계속 · T10 NO OVERWRITE.
"""
from types import SimpleNamespace

from clients.comwel_worker_client import (
    ComwelApiError,
    address_match,
    get_worker_reference,
    normalize_address,
    parse_items,
    pick_reference,
    select_latest,
)
from services.ind_worker_validator import (
    STATUS_API_ERROR,
    STATUS_NO_DATA,
    STATUS_PASS,
    STATUS_RECHECK_REQUIRED,
    api_error_payload,
    build_worker_validation,
    compare,
)
from services import diagnosis_integrated_svc as SVC


def _ref(count, date="20200101", fg="1", blanket=False):
    return {
        "external_reference_count": count,
        "reference_date": date,
        "saeop_fg": fg,
        "is_blanket": blanket,
        "saeopjang_nm": "테스트",
        "source": "근로복지공단",
    }


ADDR_SEOUL = "서울특별시 강남구 테헤란로 152"
ADDR_CHEONAN = "충남 천안시 서북구 번영로 465"
ADDR_SUWON = "경기 수원시 영통구 삼성로 129"
ADDR_GIHEUNG = "경기 용인시 기흥구 삼성로 1"
ADDR_GWANGJU = "광주광역시 광산구 하남산단6번로 107"
ADDR_AMKOR = "광주광역시 광산구 앰코로 10"
ADDR_GUMI = "경북 구미시 3공단3로 302"
ADDR_ASAN = "충남 아산시 배방읍 배방로 123"
ADDR_HWASEONG = "경기 화성시 삼성로 1120"
ADDR_BUSAN = "부산광역시 해운대구 센텀중앙로 79"


def _item(cnt, dt, fg, name="사업장", addr="서울"):
    return (
        "<item><sangsiInwonCnt>{}</sangsiInwonCnt><seongripDt>{}</seongripDt>"
        "<saeopFg>{}</saeopFg><saeopjangNm>{}</saeopjangNm>"
        "<addr>{}</addr></item>"
    ).format(cnt, dt, fg, name, addr)


def _xml(*items, code="00"):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<response><header><resultCode>{}</resultCode>"
        "<resultMsg>NORMAL SERVICE.</resultMsg></header>"
        "<body><items>{}</items></body></response>"
    ).format(code, "".join(items))


# ── T1–T8 compare ──────────────────────────────────────────────────────────
def test_T1_50_50_pass():
    out = compare(50, _ref(50))
    assert out["status"] == STATUS_PASS
    assert out["user_worker_count"] == 50
    assert out["external_reference_count"] == 50
    assert out["difference_rate"] == 0.0


def test_T2_46_50_pass():
    out = compare(46, _ref(50))
    assert out["status"] == STATUS_PASS
    assert abs(out["difference_rate"] - 0.08) < 1e-12


def test_T3_45_50_recheck():
    out = compare(45, _ref(50))
    assert out["status"] == STATUS_RECHECK_REQUIRED
    assert out["difference_rate"] == 0.10


def test_T4_40_50_recheck():
    assert compare(40, _ref(50))["status"] == STATUS_RECHECK_REQUIRED


def test_T5_55_50_recheck():
    out = compare(55, _ref(50))
    assert out["status"] == STATUS_RECHECK_REQUIRED
    assert out["difference_rate"] == 0.10


def test_T6_56_50_recheck():
    assert compare(56, _ref(50))["status"] == STATUS_RECHECK_REQUIRED


def test_T7_ref_none_no_data():
    out = compare(50, None)
    assert out["status"] == STATUS_NO_DATA
    assert out["user_worker_count"] == 50


def test_T8_ref_zero_no_data():
    assert compare(50, _ref(0))["status"] == STATUS_NO_DATA


# ── T9 / T10 ───────────────────────────────────────────────────────────────
class _CoQ:
    def __init__(self, bn="1248100998"):
        self._bn = bn
        self._ins = None

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def update(self, *a, **k):
        return self

    def insert(self, payload):
        self._ins = payload
        return self

    def execute(self):
        if self._ins is not None:
            row = dict(self._ins)
            row.setdefault("id", "R1")
            return SimpleNamespace(data=[row])
        return SimpleNamespace(data=[{"id": "C1", "business_number": self._bn, "ci_hash": "H",
                                      "agreed": True, "free_count": 0, "free_limit": 3,
                                      "status": "ACTIVE", "linked_user_id": None}])


class _PaidSB:
    def table(self, name):
        return _CoQ()


class _PaidBody:
    model_fields = {}
    sector = "INDUSTRIAL"
    auth_token = "tok"
    payment_ref = "PR1"
    disclaimer_log_id = None
    company_id = "C1"
    form_data = {"worker_count": 40, "address": ADDR_SUWON}
    worker_count = 40
    direct_workers = None
    employee_count = None
    floor_area = None
    contract_amount_eok = None
    user_tier = "INDUSTRY_STANDARD"
    process_list = None
    equipment_list = None
    ksic_list = None
    factory_id = None
    region = None
    construction_type = None
    ksic_major = None
    invoice_requested = False
    invoice_biz_no = None
    invoice_email = None
    electric_capacity = None
    elevator_count = None
    has_boiler = None
    has_hazardous_material = None
    has_high_pressure_gas = None
    has_chemical_substance = None
    input = None

    def __getattr__(self, name):
        return None


def test_T9_comwel_error_api_error_diagnosis_continues():
    def boom(*a, **k):
        raise ComwelApiError("timeout")
    out = build_worker_validation(
        _PaidSB(), _PaidBody(), {"id": "U1", "company_id": "C1"}, 40, fetch_ref=boom,
    )
    assert out["status"] == STATUS_API_ERROR
    assert out["user_worker_count"] == 40


def test_T10_external_diff_does_not_overwrite_user():
    user = 40
    out = compare(user, _ref(50))
    assert out["user_worker_count"] == 40
    assert out["external_reference_count"] == 50
    assert out["user_worker_count"] != out["external_reference_count"]


def test_T9_payload_helper():
    assert api_error_payload(12)["status"] == STATUS_API_ERROR
    assert api_error_payload(12)["user_worker_count"] == 12


# ── T11 XML fixture ────────────────────────────────────────────────────────
def test_T11a_continue_preferred_over_newer_blanket():
    xml = _xml(
        _item(10, "20200101", "3"),
        _item(20, "20230101", "4"),
        _item(30, "20210101", "1"),
        _item(40, "20190101", "1"),
        _item(99, "20250101", "7"),
    )
    recs = parse_items(xml)
    picked = select_latest(recs)
    assert picked["external_reference_count"] == 30
    assert picked["reference_date"] == "20210101"
    assert picked["saeop_fg"] == "1"
    assert picked["is_blanket"] is False


def test_T11b_no_continue_latest_is_blanket():
    xml = _xml(
        _item(10, "20200101", "3"),
        _item(20, "20230101", "4"),
        _item(0, "20250101", "7"),
        _item(15, "20220101", "7"),
    )
    recs = parse_items(xml)
    assert all(r["sangsiInwonCnt"] > 0 for r in recs)
    picked = select_latest(recs)
    assert picked["external_reference_count"] == 20
    assert picked["reference_date"] == "20230101"
    assert picked["is_blanket"] is True


def test_T11c_samsung_like_13_items_select_one():
    items = [
        _item(0, "19720101", "7", "삼성전자(주)"),
        _item(128093, "19950701", "1", "삼성전자(주)"),
        _item(1155, "19860101", "4", "삼성전자(주)"),
        _item(120563, "20110101", "3", "삼성전자(주)"),
        _item(4954, "19910103", "7", "삼성전자(주)"),
        _item(2818, "19970701", "7", "삼성전자(주)천안공장"),
        _item(671, "19900101", "7", "삼성전자(주)광주"),
        _item(2389, "19760101", "3", "삼성전자(주)본사스텝"),
        _item(26824, "19840403", "7", "삼성전자(주)기흥공장"),
        _item(111, "19971001", "7", "삼성전자(주)광주(콤프제조)"),
        _item(80, "19880101", "7", "삼성전자(주)구미"),
        _item(90, "19920101", "4", "삼성전자(주)온양"),
        _item(100, "19930101", "7", "삼성전자(주)화성"),
    ]
    assert len(items) == 13
    recs = parse_items(_xml(*items))
    picked = select_latest(recs)
    assert picked is not None
    assert picked["external_reference_count"] == 128093
    assert picked["saeop_fg"] == "1"
    assert picked["is_blanket"] is False
    assert picked["source"] == "근로복지공단"


def test_zero_count_records_excluded():
    xml = _xml(_item(0, "20250101", "1"), _item(12, "20200101", "3"))
    recs = parse_items(xml)
    assert len(recs) == 1
    assert recs[0]["sangsiInwonCnt"] == 12


def test_missing_service_key_returns_none(monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    assert get_worker_reference("1248100998") is None


def test_recheck_blanket_message():
    out = compare(40, _ref(50, blanket=True))
    assert out["status"] == STATUS_RECHECK_REQUIRED
    assert "일괄적용 사업장 기준일 수 있어 참고용" in (out["message"] or "")


# ── paid INDUSTRIAL attach + no overwrite ─────────────────────────────────
def test_paid_industrial_attaches_validation_without_overwriting_worker(monkeypatch):
    seen = {}

    def fake_ref(*a, **k):
        return _ref(50)

    monkeypatch.setattr("services.ind_worker_validator.get_worker_reference", fake_ref)

    def run_step1(sb, step1):
        seen["workers"] = step1.worker_count
        seen["inp_workers"] = (step1.input or {}).get("worker_count")
        return {"status": "success", "data": {"obligations": []}}

    orig = (SVC.resolve_auth_log, SVC._assert_linkable, SVC._save_diagnosis_purchase,
            SVC._bind_linked_user_id, SVC._ensure_disclaimer_for_paid_entry)
    SVC.resolve_auth_log = lambda sb, tok: {
        "id": "A1", "ci_hash": "CI", "free_count": 0, "free_limit": 3, "linked_user_id": None,
    }
    SVC._assert_linkable = lambda a, c: None
    SVC._save_diagnosis_purchase = lambda *a, **k: None
    SVC._bind_linked_user_id = lambda *a, **k: None
    SVC._ensure_disclaimer_for_paid_entry = lambda sb, ar: "DISC1"
    try:
        out = SVC.run_diagnosis(
            supabase=_PaidSB(), body=_PaidBody(), run_step1_func=run_step1,
            auto_tier_func=lambda *a, **k: "INDUSTRY_STANDARD",
            build_partial_func=lambda x: {}, now_func=lambda: "2026-09-04T00:00:00",
            paid_tier_prices={"INDUSTRY_STANDARD": 149000}, free_tier_codes=set(),
            engine_version="v1",
            current_user={"id": "U1", "company_id": "C1", "ci_hash": "CI",
                          "identity_verified": True, "identity_ci": "CI"},
        )
    finally:
        (SVC.resolve_auth_log, SVC._assert_linkable, SVC._save_diagnosis_purchase,
         SVC._bind_linked_user_id, SVC._ensure_disclaimer_for_paid_entry) = orig
    assert seen["workers"] == 40
    wv = out["worker_validation"]
    assert wv["user_worker_count"] == 40
    assert wv["external_reference_count"] == 50
    assert wv["status"] == STATUS_RECHECK_REQUIRED


def test_building_paid_has_no_worker_validation(monkeypatch):
    class B(_PaidBody):
        sector = "BUILDING"
        form_data = {"floor_count": 2}
        worker_count = 3

    def run_step1(sb, step1):
        return {"status": "success", "data": {"obligations": []}}

    orig = (SVC.resolve_auth_log, SVC._assert_linkable, SVC._save_diagnosis_purchase,
            SVC._bind_linked_user_id, SVC._ensure_disclaimer_for_paid_entry)
    SVC.resolve_auth_log = lambda sb, tok: {
        "id": "A1", "ci_hash": "CI", "free_count": 0, "free_limit": 3, "linked_user_id": None,
    }
    SVC._assert_linkable = lambda a, c: None
    SVC._save_diagnosis_purchase = lambda *a, **k: None
    SVC._bind_linked_user_id = lambda *a, **k: None
    SVC._ensure_disclaimer_for_paid_entry = lambda sb, ar: "DISC1"
    try:
        out = SVC.run_diagnosis(
            supabase=_PaidSB(), body=B(), run_step1_func=run_step1,
            auto_tier_func=lambda *a, **k: "BUILDING_V2",
            build_partial_func=lambda x: {}, now_func=lambda: "2026-09-04T00:00:00",
            paid_tier_prices={"BUILDING_V2": 99000}, free_tier_codes=set(),
            engine_version="v1",
            current_user={"id": "U1", "company_id": "C1", "ci_hash": "CI",
                          "identity_verified": True, "identity_ci": "CI"},
        )
    finally:
        (SVC.resolve_auth_log, SVC._assert_linkable, SVC._save_diagnosis_purchase,
         SVC._bind_linked_user_id, SVC._ensure_disclaimer_for_paid_entry) = orig
    assert "worker_validation" not in out


def _samsung_items_distinct_addrs():
    return [
        _item(0, "19720101", "7", "삼성전자(주)", ADDR_SUWON),
        _item(128093, "19950701", "1", "삼성전자(주)", ADDR_SUWON),
        _item(1155, "19860101", "4", "삼성전자(주)", ADDR_SUWON),
        _item(120563, "20110101", "3", "삼성전자(주)", ADDR_SUWON),
        _item(4954, "19910103", "7", "삼성전자(주)", ADDR_SUWON),
        _item(2818, "19970701", "7", "삼성전자(주)천안공장", ADDR_CHEONAN),
        _item(671, "19900101", "7", "삼성전자(주)광주", ADDR_GWANGJU),
        _item(2389, "19760101", "3", "삼성전자(주)본사스텝", ADDR_SUWON),
        _item(26824, "19840403", "7", "삼성전자(주)기흥공장", ADDR_GIHEUNG),
        _item(111, "19971001", "7", "삼성전자(주)광주(콤프제조)", ADDR_AMKOR),
        _item(80, "19880101", "7", "삼성전자(주)구미", ADDR_GUMI),
        _item(90, "19920101", "4", "삼성전자(주)온양", ADDR_ASAN),
        _item(100, "19930101", "7", "삼성전자(주)화성", ADDR_HWASEONG),
    ]


def _http_xml(monkeypatch, xml):
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "dummy")

    class Resp:
        status_code = 200
        text = xml

    def boom(*a, **k):
        raise AssertionError("httpx.get must not be called")

    monkeypatch.setattr("clients.comwel_worker_client.httpx.get", lambda *a, **k: Resp())
    return boom


# ── address_match unit ─────────────────────────────────────────────────────
def test_address_match_clear_true():
    assert address_match(
        "충청남도 천안시 서북구 번영로 465",
        "충남 천안시 서북구 번영로 465 (성성동)",
    ) is True


def test_address_match_sido_abbrev_true():
    assert "서울" in normalize_address("서울특별시 강남구 테헤란로 152")
    assert "경기" in normalize_address("경기도 수원시 영통구 삼성로 129")
    assert address_match(ADDR_SEOUL, "서울 강남구 테헤란로 152") is True
    assert address_match(
        "경기도 수원시 영통구 삼성로 129",
        ADDR_SUWON,
    ) is True


def test_address_match_ambiguous_false():
    assert address_match("천안", ADDR_CHEONAN) is False
    assert address_match("서울", ADDR_SEOUL) is False
    assert address_match(ADDR_SUWON, ADDR_GIHEUNG) is False
    assert address_match(ADDR_SEOUL, ADDR_CHEONAN) is False


# ── M1–M5 workplace address match ──────────────────────────────────────────
def test_M1_same_biz_uses_cheonan_not_seoul():
    recs = parse_items(_xml(
        _item(99999, "19950701", "1", "서울공장", ADDR_SEOUL),
        _item(2818, "19970701", "7", "천안공장", ADDR_CHEONAN),
    ))
    picked = pick_reference(recs, ADDR_CHEONAN)
    assert picked is not None
    assert picked["external_reference_count"] == 2818
    assert picked["matched_address"] == ADDR_CHEONAN
    assert picked["saeop_fg"] != "1"


def test_M1_get_worker_reference_http_path(monkeypatch):
    xml = _xml(
        _item(99999, "19950701", "1", "서울공장", ADDR_SEOUL),
        _item(2818, "19970701", "7", "천안공장", ADDR_CHEONAN),
    )
    _http_xml(monkeypatch, xml)
    picked = get_worker_reference("1248100998", expected_address=ADDR_CHEONAN)
    assert picked["external_reference_count"] == 2818
    assert picked["matched_address"] == ADDR_CHEONAN


def test_M2_no_address_match_no_data_diagnosis_continues():
    recs = parse_items(_xml(
        _item(99999, "19950701", "1", "서울공장", ADDR_SEOUL),
        _item(2818, "19970701", "7", "천안공장", ADDR_CHEONAN),
    ))
    picked = pick_reference(recs, ADDR_BUSAN)
    assert picked is None
    out = compare(40, picked)
    assert out["status"] == STATUS_NO_DATA
    assert out["user_worker_count"] == 40

    class Body(_PaidBody):
        form_data = {"worker_count": 40, "address": ADDR_BUSAN}

    def fake_none(*a, **k):
        return None

    out2 = build_worker_validation(
        _PaidSB(), Body(), {"id": "U1", "company_id": "C1"}, 40, fetch_ref=fake_none,
    )
    assert out2["status"] == STATUS_NO_DATA
    assert out2["user_worker_count"] == 40


def test_M3_samsung_specific_plant_not_always_128093():
    recs = parse_items(_xml(*_samsung_items_distinct_addrs()))
    assert len([r for r in recs if r["sangsiInwonCnt"] > 0]) == 12
    cheonan = pick_reference(recs, ADDR_CHEONAN)
    assert cheonan["external_reference_count"] == 2818
    assert cheonan["external_reference_count"] != 128093
    giheung = pick_reference(recs, ADDR_GIHEUNG)
    assert giheung["external_reference_count"] == 26824
    assert giheung["external_reference_count"] != 128093
    suwon = pick_reference(recs, ADDR_SUWON)
    assert suwon["external_reference_count"] == 128093
    assert suwon["matched_address"] == ADDR_SUWON


def test_M4_biz_match_address_mismatch_is_no_data_not_recheck(monkeypatch):
    xml = _xml(
        _item(50, "19950701", "1", "서울공장", ADDR_SEOUL),
    )
    _http_xml(monkeypatch, xml)
    picked = get_worker_reference("1248100998", expected_address=ADDR_CHEONAN)
    assert picked is None
    out = compare(40, picked)
    assert out["status"] == STATUS_NO_DATA
    assert out["status"] != STATUS_RECHECK_REQUIRED


def test_M5_worker_count_original_preserved():
    user = 40
    out = compare(user, _ref(50))
    assert out["user_worker_count"] == 40
    assert out["external_reference_count"] == 50

    def fake_ref(*a, **k):
        return _ref(50)

    built = build_worker_validation(
        _PaidSB(), _PaidBody(), {"id": "U1", "company_id": "C1"}, user, fetch_ref=fake_ref,
    )
    assert built["user_worker_count"] == 40
    assert built["user_worker_count"] != built["external_reference_count"]


def test_empty_expected_address_returns_none_without_http(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "dummy")
    called = []

    def spy(*a, **k):
        called.append(1)
        raise AssertionError("must not HTTP without expected_address")

    monkeypatch.setattr("clients.comwel_worker_client.httpx.get", spy)
    assert get_worker_reference("1248100998") is None
    assert get_worker_reference("1248100998", expected_address="  ") is None
    assert called == []


def test_missing_address_on_body_is_no_data():
    class NoAddr(_PaidBody):
        form_data = {"worker_count": 40}
        region = None

    called = []

    def spy(*a, **k):
        called.append(1)
        return _ref(50)

    out = build_worker_validation(
        _PaidSB(), NoAddr(), {"id": "U1", "company_id": "C1"}, 40, fetch_ref=spy,
    )
    assert out["status"] == STATUS_NO_DATA
    assert called == []
    assert out["user_worker_count"] == 40
