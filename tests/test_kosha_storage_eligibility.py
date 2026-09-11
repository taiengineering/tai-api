"""WP-1C-5B eligibility + attachment resolution."""
from services.kosha_safety_materials.storage.eligibility import (
    EligibilityError,
    is_eligible_asset,
    is_eligible_detail,
    live_kogl_ok,
    pending_without_version,
)
from services.kosha_safety_materials.storage.resolve import (
    ResolutionError,
    match_downloadable_file,
    match_logical_attachment,
)
from services.kosha_safety_materials.storage.storage_keys import source_asset_key


def _detail(kogl="1", ct="PDF", mid="m1", status="OK"):
    return {
        "material_id": mid, "kogl_type": kogl, "content_type": ct,
        "enrichment_status": status,
    }


def _asset(mid="m1", atype="PDF", checksum="x"):
    return {"material_id": mid, "asset_type": atype, "checksum": checksum, "file_name": "a.pdf"}


def test_eligibility_gates():
    mem = {"m1"}
    assert is_eligible_detail(_detail(), mem)
    assert not is_eligible_detail(_detail(kogl="2"), mem)
    assert not is_eligible_detail(_detail(kogl="4"), mem)
    assert not is_eligible_detail(_detail(kogl="UNKNOWN"), mem)
    assert not is_eligible_detail(_detail(ct="VIDEO"), mem)
    assert not is_eligible_detail(_detail(mid="hist"), mem)
    assert is_eligible_asset(_asset(), _detail(), mem)
    assert not is_eligible_asset(_asset(atype="VIDEO"), _detail(), mem)
    assert live_kogl_ok("1", "1") is None
    assert live_kogl_ok("3", "3") is None
    assert live_kogl_ok("1", "2") == "LICENSE_CHANGED_REVIEW_REQUIRED"
    assert live_kogl_ok("1", "3") == "LICENSE_CHANGED_REVIEW_REQUIRED"


def test_pending_sort_positive_size_before_zero_and_keeps_zero():
    elig = [
        {"source_asset_key": "zero", "kogl_type": "1", "asset_type": "PDF", "file_size": 0, "material_id": "m0", "asset_id": 2029},
        {"source_asset_key": "null", "kogl_type": "1", "asset_type": "PDF", "file_size": None, "material_id": "mN", "asset_id": 3},
        {"source_asset_key": "big", "kogl_type": "1", "asset_type": "PDF", "file_size": 100, "material_id": "m2", "asset_id": 2},
        {"source_asset_key": "small", "kogl_type": "1", "asset_type": "PDF", "file_size": 10, "material_id": "m1", "asset_id": 1},
        {"source_asset_key": "img", "kogl_type": "1", "asset_type": "IMAGE", "file_size": 5, "material_id": "mI", "asset_id": 4},
    ]
    pending = pending_without_version(elig, set())
    assert [p["source_asset_key"] for p in pending] == ["small", "big", "zero", "null", "img"]
    assert "zero" in {p["source_asset_key"] for p in pending}


def test_pending_excludes_by_asset_id_even_if_checksum_differs():
    elig = [
        {"source_asset_key": "checksum-a", "kogl_type": "1", "asset_type": "PDF", "file_size": 9, "material_id": "m1", "asset_id": 10},
        {"source_asset_key": "checksum-b", "kogl_type": "1", "asset_type": "PDF", "file_size": 3, "material_id": "m1", "asset_id": 11},
    ]
    pending = pending_without_version(elig, {10})
    assert [p["asset_id"] for p in pending] == [11]


def test_pending_null_asset_id_fail_closed():
    try:
        pending_without_version(
            [{"source_asset_key": "x", "kogl_type": "1", "asset_type": "PDF", "file_size": 1, "material_id": "m1", "asset_id": None}],
            set(),
        )
        assert False
    except EligibilityError as e:
        assert e.code == "ASSET_ID_REQUIRED"


def test_pending_excludes_versioned_and_historical():
    elig = [
        {"source_asset_key": "a", "kogl_type": "1", "asset_type": "PDF", "file_size": 9, "material_id": "m1", "asset_id": 2},
        {"source_asset_key": "b", "kogl_type": "1", "asset_type": "PDF", "file_size": 3, "material_id": "m1", "asset_id": 1},
    ]
    pending = pending_without_version(elig, {2})
    assert [p["source_asset_key"] for p in pending] == ["b"]


def test_logical_match_exact_and_blocks():
    sak = source_asset_key("m1", "NO", 1, "a.pdf")
    js = {"payload": {"list": [
        {"contsAtcflNo": "NO", "contsAtcflSeq": 1, "orgnlAtchFileNm": "a.pdf"},
    ]}}
    hit = match_logical_attachment(
        material_id="m1", expected_checksum=sak, expected_filename="a.pdf", atch_json=js,
        requested_med_seq="10", response_med_seq="10",
    )
    assert hit["checksum"] == sak
    try:
        match_logical_attachment(
            material_id="m1", expected_checksum=sak, expected_filename="a.pdf", atch_json=js,
            requested_med_seq="10", response_med_seq="99",
        )
        assert False
    except ResolutionError as e:
        assert e.code == "SOURCE_ASSET_RESOLUTION_BLOCKED"
    js0 = {"payload": {"list": []}}
    try:
        match_logical_attachment(material_id="m1", expected_checksum=sak, expected_filename="a.pdf", atch_json=js0)
        assert False
    except ResolutionError as e:
        assert e.code == "SOURCE_ASSET_ZERO_MATCH"
    js2 = {"payload": {"list": [
        {"contsAtcflNo": "NO", "contsAtcflSeq": 1, "orgnlAtchFileNm": "a.pdf"},
        {"contsAtcflNo": "NO", "contsAtcflSeq": 1, "orgnlAtchFileNm": "a.pdf"},
    ]}}
    try:
        match_logical_attachment(material_id="m1", expected_checksum=sak, expected_filename="a.pdf", atch_json=js2)
        assert False
    except ResolutionError as e:
        assert e.code == "SOURCE_ASSET_MULTI_MATCH"
    try:
        match_logical_attachment(
            material_id="m1", expected_checksum=sak, expected_filename="other.pdf", atch_json=js,
        )
        assert False
    except ResolutionError as e:
        assert e.code == "SOURCE_ASSET_FILENAME_MISMATCH"


def test_downloadable_file_exact_and_blocks():
    files = [{"atcflNo": "NO", "atcflSeq": 1, "orgnlAtchFileNm": "a.pdf"}]
    hit = match_downloadable_file(files, file_name="a.pdf", atcfl_no="NO")
    assert hit["atcfl_seq"] == 1
    try:
        match_downloadable_file([], file_name="a.pdf", atcfl_no="NO")
        assert False
    except ResolutionError as e:
        assert e.code == "SOURCE_ASSET_ZERO_MATCH"
    try:
        match_downloadable_file(files + files, file_name="a.pdf", atcfl_no="NO")
        assert False
    except ResolutionError as e:
        assert e.code == "SOURCE_ASSET_MULTI_MATCH"
    try:
        match_downloadable_file(files, file_name="b.pdf", atcfl_no="NO")
        assert False
    except ResolutionError as e:
        assert e.code == "SOURCE_ASSET_FILENAME_MISMATCH"


def test_4523_style_filename_mismatch_is_hold_reason_not_fuzzy():
    files = [
        {"atcflNo": "FL00014173601", "atcflSeq": 1, "orgnlAtchFileNm": "[2017-교육미디어-405]-리프트 점검_표지.ai"},
        {"atcflNo": "FL00014173601", "atcflSeq": 2, "orgnlAtchFileNm": "[2017-교육미디어-405] 리프트 점검.pdf"},
    ]
    try:
        match_downloadable_file(
            files, file_name="[2017-교육미디어-405]-리프트 점검_표지.pdf", atcfl_no="FL00014173601",
        )
        assert False
    except ResolutionError as e:
        assert e.code == "SOURCE_ASSET_FILENAME_MISMATCH"
        names = [x["file_name"] for x in e.observed_files]
        assert "[2017-교육미디어-405]-리프트 점검_표지.ai" in names
        assert "[2017-교육미디어-405] 리프트 점검.pdf" in names


def test_pending_excludes_open_holds_but_not_as_versioned():
    elig = [
        {"source_asset_key": "a", "kogl_type": "1", "asset_type": "PDF", "file_size": 9, "material_id": "m1", "asset_id": 4523},
        {"source_asset_key": "b", "kogl_type": "1", "asset_type": "PDF", "file_size": 3, "material_id": "m1", "asset_id": 1},
    ]
    pending = pending_without_version(elig, set(), {4523})
    assert [p["asset_id"] for p in pending] == [1]
