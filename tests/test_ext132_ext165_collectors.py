"""WO-001B-R1 — EXT-132/EXT-165 수집기 전체 테스트 스위트.

=====================================================================
EXT-132 소방청 위험물안전관리 (소스 ID: EXT132_HAZARDOUS_MATERIAL)
=====================================================================
B01  contract 상수 검증
B02  parse: 정상 XML → PageResult
B03  parse: 빈 items XML → items=[]
B04  parse: totalCount 포함 XML
B05  parse: malformed XML → Ext132ParseError
B06  parse: chemicalno 없는 item → chemicalno=""
B07  sync: dry_run → 1페이지 후 종료
B08  sync: budget exhausted → PARTIAL
B09  sync: HTTP 오류 → FAILED
B10  sync: parse 오류 → FAILED
B11  sync: safety cap → PARTIAL
B12  sync: empty page terminates
B13  sync: totalCount termination
B14  store: compute_content_hash 결정적
B15  store: promote_snapshot STAGING guard
B16  adapter: preflight 환경변수 없음 → PreflightError
B17  adapter: preflight 환경변수 있음 → pass
B18  adapter: run success → RunResult SUCCESS
B19  adapter: run FAILED collect → RunResult FAILED + snapshot FAILED
B20  adapter: run PARTIAL collect → RunResult FAILED, snapshot preserved (no fail_snapshot)
B21  registry: EXT132_HAZARDOUS_MATERIAL 등록됨
B22  registry: adapter_key=ext132_hazardous_material
B23  registry: auto_refresh_candidate=False
B24  registry: sync_mode=FULL_SNAPSHOT

=====================================================================
EXT-165 화학물질안전원 화학사고 (소스 ID: EXT165_CHEMICAL_ACCIDENT)
=====================================================================
C01  contract 상수 검증
C02  parse: 정상 XML → PageResult
C03  parse: 빈 items XML → items=[]
C04  parse: totalCount 포함 XML
C05  parse: malformed XML → Ext165ParseError
C06  parse: datano fallback (대소문자 변형)
C07  sync: dry_run → 1페이지 후 종료
C08  sync: budget exhausted → PARTIAL
C09  sync: yyyy 파라미터 전달 확인
C10  sync: HTTP 오류 → FAILED
C11  sync: totalCount termination
C12  store: compute_content_hash 결정적
C13  adapter: preflight 환경변수 없음 → PreflightError
C14  adapter: run success → RunResult SUCCESS
C15  adapter: run FAILED collect → RunResult FAILED
C16  adapter: yyyy 메타데이터 → collect_all 에 전달됨
C17  registry: EXT165_CHEMICAL_ACCIDENT 등록됨
C18  registry: auto_refresh_candidate=False

=====================================================================
공통/인프라
=====================================================================
D01  generic budget: consume_or_raise 정상
D02  generic budget: exhausted → RequestBudgetExceeded
D03  generic budget: remaining 계산
D04  generic budget: RequestBudgetExceeded 메시지
D05  register_builtin_adapters: ext132 등록됨 (idempotent)
D06  register_builtin_adapters: ext165 등록됨 (idempotent)
D07  runner: run_source EXT132 — adapter lookup success
D08  runner: run_source EXT165 — adapter lookup success
D09  regression: 기존 KECO adapter 등록 영향 없음
D10  regression: 기존 CSI adapter 등록 영향 없음
D11  regression: 기존 HOLIDAY adapter 등록 영향 없음
D12  migration draft: ext132 파일 존재
D13  migration draft: ext165 파일 존재

=====================================================================
PATCH-003 P0 blockers
=====================================================================
H01  SQL ext132 save_page_checkpoint has SNAPSHOT_NOT_STAGING guard
H02  SQL complete_snapshot has PROMOTE_FAILED raise exception (both sources)
H03  ext132 sync premature empty page → PARTIAL(PREMATURE_EMPTY_PAGE)
H04  ext165 sync premature empty page → PARTIAL(PREMATURE_EMPTY_PAGE)
H05  initial_items_count=100 + empty page + total=100 → COMPLETED
H06  ext132 adapter BUDGET_EXHAUSTED → FAILED, no fail_snapshot, snapshot_preserved=True
H07  ext165 adapter BUDGET_EXHAUSTED → FAILED, no fail_snapshot, snapshot_preserved=True
H08  ext132 fail_snapshot STAGING guard present in call chain
H09  ext165 fail_snapshot STAGING guard present in call chain
H10  ext132 adapter INCOMPLETE_COLLECTION → FAILED + fail_snapshot
H11  save_page_checkpoint SNAPSHOT_NOT_STAGING → PageFencedError
H12  SQL ext132 checkpoint_api_total validation
H13  SQL ext165 checkpoint_api_total validation
H14  ext132 adapter FENCED → FAILED, no fail_snapshot, snapshot_preserved=True
H15  content hash consistent: in-memory vs DB-derived
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import ANY, MagicMock, call, patch
from uuid import uuid4

import pytest

from services.public_data_sync.adapters import AdapterRegistry
from services.public_data_sync.contracts import RunContext, RunStatus, SourceMode, TriggerKind
from services.public_data_sync.errors import PreflightError


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(source_id: str, **kwargs: Any) -> RunContext:
    return RunContext(
        run_id=str(uuid4()),
        source_id=source_id,
        trigger=TriggerKind.MANUAL,
        started_at=datetime.now(timezone.utc),
        **kwargs,
    )


def _xml_page(items: list[dict], total_count: int | None = None, page_no: int = 1, num_of_rows: int = 10) -> bytes:
    item_blocks = ""
    for d in items:
        fields = "".join(f"<{k}>{v}</{k}>" for k, v in d.items())
        item_blocks += f"<item>{fields}</item>"
    total_tag = f"<totalCount>{total_count}</totalCount>" if total_count is not None else ""
    return (
        f"<?xml version='1.0' encoding='UTF-8'?>"
        f"<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>"
        f"<body><pageNo>{page_no}</pageNo><numOfRows>{num_of_rows}</numOfRows>"
        f"{total_tag}<items>{item_blocks}</items></body></response>"
    ).encode()


def _empty_page(page_no: int = 2) -> bytes:
    return _xml_page([], page_no=page_no)


# ─────────────────────────────────────────────────────────────────────────────
# B01-B06 — EXT-132 contract & parse
# ─────────────────────────────────────────────────────────────────────────────

def test_b01_ext132_contract_source_id():
    from services.ext132_hazardous_material.contract import SOURCE_ID
    assert SOURCE_ID == "EXT132_HAZARDOUS_MATERIAL"


def test_b01b_ext132_contract_adapter_key():
    from services.ext132_hazardous_material.contract import ADAPTER_KEY
    assert ADAPTER_KEY == "ext132_hazardous_material"


def test_b01c_ext132_contract_base_url():
    from services.ext132_hazardous_material.contract import BASE_URL
    assert "apis.data.go.kr" in BASE_URL
    assert "materialInfoSvc" in BASE_URL


def test_b02_ext132_parse_normal_xml():
    from services.ext132_hazardous_material.parse import parse_page
    xml = _xml_page([
        {"chemicalno": "A001", "chemicalname": "에탄올"},
        {"chemicalno": "A002", "chemicalname": "메탄올"},
    ])
    page = parse_page(xml)
    assert len(page.items) == 2
    assert page.items[0].chemicalno == "A001"
    assert page.items[1].chemicalno == "A002"
    assert page.result_code == "00"


def test_b03_ext132_parse_empty_items():
    from services.ext132_hazardous_material.parse import parse_page
    xml = _empty_page()
    page = parse_page(xml)
    assert page.items == []


def test_b04_ext132_parse_total_count():
    from services.ext132_hazardous_material.parse import parse_page
    xml = _xml_page([{"chemicalno": "X1"}], total_count=999)
    page = parse_page(xml)
    assert page.total_count == 999


def test_b05_ext132_parse_malformed_xml():
    from services.ext132_hazardous_material.parse import Ext132ParseError, parse_page
    with pytest.raises(Ext132ParseError):
        parse_page(b"<not valid xml<<<")


def test_b06_ext132_parse_missing_chemicalno():
    from services.ext132_hazardous_material.parse import parse_page
    xml = _xml_page([{"name": "some_chemical"}])   # no chemicalno field
    page = parse_page(xml)
    assert len(page.items) == 1
    assert page.items[0].chemicalno == ""


# ─────────────────────────────────────────────────────────────────────────────
# B07-B13 — EXT-132 sync
# ─────────────────────────────────────────────────────────────────────────────

def test_b07_ext132_dry_run_fetches_one_page():
    from services.ext132_hazardous_material.parse import parse_page
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all

    page1 = _xml_page([{"chemicalno": f"A{i:03d}"} for i in range(10)], total_count=100)

    with patch("services.ext132_hazardous_material.client.fetch_page", return_value=page1) as mock_fetch:
        result = collect_all(dry_run=True, page_delay_seconds=0)

    assert mock_fetch.call_count == 1
    assert result.status == SyncStatus.COMPLETED
    assert result.fetched == 10
    assert result.pages_fetched == 1


def test_b08_ext132_budget_exhausted_returns_partial():
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all

    always_10 = _xml_page([{"chemicalno": "A001"}] * 10, total_count=10000)

    with patch("services.ext132_hazardous_material.client.fetch_page", return_value=always_10):
        result = collect_all(request_budget=1, page_delay_seconds=0)

    assert result.status == SyncStatus.PARTIAL
    assert result.error_code == "BUDGET_EXHAUSTED"
    assert result.budget_used == 1


def test_b09_ext132_http_error_returns_failed():
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all

    with patch("services.ext132_hazardous_material.client.fetch_page", side_effect=ConnectionError("timeout")):
        result = collect_all(page_delay_seconds=0)

    assert result.status == SyncStatus.FAILED
    assert result.error_code == "HTTP_ERROR"


def test_b10_ext132_parse_error_returns_failed():
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all

    with patch("services.ext132_hazardous_material.client.fetch_page", return_value=b"<bad xml<<<"):
        result = collect_all(page_delay_seconds=0)

    assert result.status == SyncStatus.FAILED
    assert result.error_code == "PARSE_ERROR"


def test_b11_ext132_safety_cap_returns_partial():
    from services.ext132_hazardous_material import sync as sync_mod
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all

    always_1 = _xml_page([{"chemicalno": "X"}] * 1, total_count=999999)
    original_cap = sync_mod.MAX_PAGES_SAFETY_CAP
    sync_mod.MAX_PAGES_SAFETY_CAP = 3

    try:
        with patch("services.ext132_hazardous_material.client.fetch_page", return_value=always_1):
            result = collect_all(request_budget=999, page_delay_seconds=0)
    finally:
        sync_mod.MAX_PAGES_SAFETY_CAP = original_cap

    assert result.status == SyncStatus.PARTIAL
    assert result.error_code == "SAFETY_CAP"


def test_b12_ext132_empty_page_terminates():
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all

    page1 = _xml_page([{"chemicalno": "A001"}] * 5)
    page2 = _empty_page(page_no=2)
    pages = [page1, page2]
    idx = {"n": 0}

    def _fetch(page_no, **kw):
        val = pages[idx["n"]]
        idx["n"] += 1
        return val

    with patch("services.ext132_hazardous_material.client.fetch_page", side_effect=_fetch):
        result = collect_all(page_delay_seconds=0)

    assert result.status == SyncStatus.COMPLETED
    assert result.fetched == 5
    assert result.pages_fetched == 2


def test_b13_ext132_total_count_terminates():
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all

    # totalCount=3 → 3 items → should stop after 1 page
    page1 = _xml_page([{"chemicalno": f"A{i}"} for i in range(3)], total_count=3)

    with patch("services.ext132_hazardous_material.client.fetch_page", return_value=page1) as mock_fetch:
        result = collect_all(page_delay_seconds=0)

    assert mock_fetch.call_count == 1
    assert result.status == SyncStatus.COMPLETED
    assert result.fetched == 3


# ─────────────────────────────────────────────────────────────────────────────
# B14-B15 — EXT-132 store
# ─────────────────────────────────────────────────────────────────────────────

def test_b14_ext132_content_hash_deterministic():
    from services.ext132_hazardous_material.parse import Ext132Item
    from services.ext132_hazardous_material.store import compute_content_hash

    items_a = [Ext132Item("A001"), Ext132Item("A002")]
    items_b = [Ext132Item("A002"), Ext132Item("A001")]  # reversed order
    assert compute_content_hash(items_a) == compute_content_hash(items_b)


def test_b15_ext132_promote_snapshot_staging_guard():
    """promote_snapshot filters on status=STAGING — cannot promote non-STAGING rows."""
    from services.ext132_hazardous_material.store import promote_snapshot

    mock_sb = MagicMock()
    mock_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

    result = promote_snapshot("snap-id", total_fetched=5, content_hash="abc", sb=mock_sb)
    assert result is False

    # Verify the STAGING guard was included in the query chain
    update_chain = mock_sb.table.return_value.update.return_value.eq.return_value.eq
    update_chain.assert_called_once_with("status", "STAGING")


# ─────────────────────────────────────────────────────────────────────────────
# B16-B20 — EXT-132 adapter
# ─────────────────────────────────────────────────────────────────────────────

def test_b16_ext132_adapter_preflight_missing_key(monkeypatch):
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    adapter = Ext132HazardousMaterialAdapter()
    with pytest.raises(PreflightError):
        adapter.preflight(_ctx("EXT132_HAZARDOUS_MATERIAL"))


def test_b17_ext132_adapter_preflight_key_present(monkeypatch):
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "test-key-value")
    adapter = Ext132HazardousMaterialAdapter()
    adapter.preflight(_ctx("EXT132_HAZARDOUS_MATERIAL"))   # must not raise


def test_b18_ext132_adapter_run_success():
    from services.ext132_hazardous_material.sync import SyncResult, SyncStatus
    from services.ext132_hazardous_material.parse import Ext132Item
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter

    fake_items = [Ext132Item("A001"), Ext132Item("A002")]
    fake_sync = SyncResult(
        status=SyncStatus.COMPLETED,
        fetched=2,
        items=fake_items,
        pages_fetched=1,
        budget_used=1,
    )

    # R3-02: collect_all side_effect must invoke on_page_complete so total_in_db is updated
    def fake_collect(**kw):
        on_page_complete = kw.get("on_page_complete")
        if on_page_complete:
            on_page_complete(1, fake_items, 2, 2)
        return fake_sync

    with (
        patch("services.ext132_hazardous_material.store.create_staging_snapshot", return_value="snap-1"),
        patch("services.ext132_hazardous_material.store.save_page_checkpoint", return_value=2),
        patch("services.ext132_hazardous_material.sync.collect_all", side_effect=fake_collect),
        patch("services.ext132_hazardous_material.store.atomic_complete_snapshot", return_value=True),
    ):
        result = Ext132HazardousMaterialAdapter().run(_ctx("EXT132_HAZARDOUS_MATERIAL"))

    assert result.status == RunStatus.SUCCESS
    assert result.fetched == 2
    assert result.change_detected is True
    assert result.content_hash is not None


def test_b19_ext132_adapter_run_failed_collect():
    from services.ext132_hazardous_material.sync import SyncResult, SyncStatus
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter

    fake_sync = SyncResult(
        status=SyncStatus.FAILED,
        fetched=0,
        items=[],
        error_code="HTTP_ERROR",
        error_message="timeout",
    )

    fail_snapshot_mock = MagicMock()
    with (
        patch("services.ext132_hazardous_material.store.create_staging_snapshot", return_value="snap-1"),
        patch("services.ext132_hazardous_material.sync.collect_all", return_value=fake_sync),
        patch("services.ext132_hazardous_material.store.fail_snapshot", fail_snapshot_mock),
    ):
        result = Ext132HazardousMaterialAdapter().run(_ctx("EXT132_HAZARDOUS_MATERIAL"))

    assert result.status == RunStatus.FAILED
    assert result.error_code == "HTTP_ERROR"
    fail_snapshot_mock.assert_called_once_with("snap-1", run_id=ANY, error_message="HTTP_ERROR")


def test_b20_ext132_adapter_run_partial():
    """PATCH-003: PARTIAL from collect → RunResult FAILED, fail_snapshot NOT called (snapshot preserved for resume)."""
    from services.ext132_hazardous_material.sync import SyncResult, SyncStatus
    from services.ext132_hazardous_material.parse import Ext132Item
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter

    fake_items = [Ext132Item("A001")]
    fake_sync = SyncResult(
        status=SyncStatus.PARTIAL,
        fetched=1,
        items=fake_items,
        error_code="BUDGET_EXHAUSTED",
    )

    def fake_collect(**kw):
        on_page_complete = kw.get("on_page_complete")
        if on_page_complete:
            on_page_complete(1, fake_items, 1, None)
        return fake_sync

    fail_snapshot_mock = MagicMock()
    atomic_mock = MagicMock()
    with (
        patch("services.ext132_hazardous_material.store.create_staging_snapshot", return_value="snap-1"),
        patch("services.ext132_hazardous_material.store.save_page_checkpoint", return_value=1),
        patch("services.ext132_hazardous_material.sync.collect_all", side_effect=fake_collect),
        patch("services.ext132_hazardous_material.store.fail_snapshot", fail_snapshot_mock),
        patch("services.ext132_hazardous_material.store.atomic_complete_snapshot", atomic_mock),
    ):
        result = Ext132HazardousMaterialAdapter().run(_ctx("EXT132_HAZARDOUS_MATERIAL"))

    assert result.status == RunStatus.FAILED
    assert result.error_code == "BUDGET_EXHAUSTED"
    assert (result.details or {}).get("snapshot_preserved") is True
    fail_snapshot_mock.assert_not_called()
    atomic_mock.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# B21-B24 — EXT-132 registry
# ─────────────────────────────────────────────────────────────────────────────

def test_b21_ext132_registry_entry_exists():
    from services.public_data_sync.registry import registry
    spec = registry.get("EXT132_HAZARDOUS_MATERIAL")
    assert spec.source_id == "EXT132_HAZARDOUS_MATERIAL"


def test_b22_ext132_registry_adapter_key():
    from services.public_data_sync.registry import registry
    spec = registry.get("EXT132_HAZARDOUS_MATERIAL")
    assert spec.adapter_key == "ext132_hazardous_material"


def test_b23_ext132_registry_auto_refresh_false():
    from services.public_data_sync.registry import registry
    spec = registry.get("EXT132_HAZARDOUS_MATERIAL")
    assert spec.auto_refresh_candidate is False


def test_b24_ext132_registry_sync_mode_full_snapshot():
    from services.public_data_sync.registry import registry
    spec = registry.get("EXT132_HAZARDOUS_MATERIAL")
    assert spec.sync_mode == SourceMode.FULL_SNAPSHOT


# ─────────────────────────────────────────────────────────────────────────────
# C01-C06 — EXT-165 contract & parse
# ─────────────────────────────────────────────────────────────────────────────

def test_c01_ext165_contract_source_id():
    from services.ext165_chemical_accident.contract import SOURCE_ID
    assert SOURCE_ID == "EXT165_CHEMICAL_ACCIDENT"


def test_c01b_ext165_contract_base_url():
    from services.ext165_chemical_accident.contract import BASE_URL
    assert "apis.data.go.kr" in BASE_URL
    assert "iciscsc" in BASE_URL


def test_c02_ext165_parse_normal_xml():
    from services.ext165_chemical_accident.parse import parse_page
    xml = _xml_page([
        {"dataNo": "2024-001", "accidentType": "누출"},
        {"dataNo": "2024-002", "accidentType": "화재"},
    ])
    page = parse_page(xml)
    assert len(page.items) == 2
    assert page.items[0].datano == "2024-001"
    assert page.items[1].datano == "2024-002"


def test_c03_ext165_parse_empty_items():
    from services.ext165_chemical_accident.parse import parse_page
    page = parse_page(_empty_page())
    assert page.items == []


def test_c04_ext165_parse_total_count():
    from services.ext165_chemical_accident.parse import parse_page
    xml = _xml_page([{"dataNo": "D1"}], total_count=42)
    page = parse_page(xml)
    assert page.total_count == 42


def test_c05_ext165_parse_malformed_xml():
    from services.ext165_chemical_accident.parse import Ext165ParseError, parse_page
    with pytest.raises(Ext165ParseError):
        parse_page(b"<<not xml")


def test_c06_ext165_parse_datano_fallback_lowercase():
    """parse_page handles datano (lowercase) as well as dataNo (camelCase)."""
    from services.ext165_chemical_accident.parse import parse_page
    # Simulate response with lowercase datano
    xml = (
        b"<?xml version='1.0' encoding='UTF-8'?>"
        b"<response><body><pageNo>1</pageNo><numOfRows>10</numOfRows>"
        b"<items><item><datano>LOWER-001</datano></item></items></body></response>"
    )
    page = parse_page(xml)
    assert len(page.items) == 1
    assert page.items[0].datano == "LOWER-001"


# ─────────────────────────────────────────────────────────────────────────────
# C07-C11 — EXT-165 sync
# ─────────────────────────────────────────────────────────────────────────────

def test_c07_ext165_dry_run_fetches_one_page():
    from services.ext165_chemical_accident.sync import SyncStatus, collect_all

    page1 = _xml_page([{"dataNo": f"D{i:03d}"} for i in range(5)], total_count=200)
    with patch("services.ext165_chemical_accident.client.fetch_page", return_value=page1) as mock_fetch:
        result = collect_all(dry_run=True, page_delay_seconds=0)

    assert mock_fetch.call_count == 1
    assert result.status == SyncStatus.COMPLETED
    assert result.fetched == 5


def test_c08_ext165_budget_exhausted_returns_partial():
    from services.ext165_chemical_accident.sync import SyncStatus, collect_all

    always_5 = _xml_page([{"dataNo": "D1"}] * 5, total_count=9999)
    with patch("services.ext165_chemical_accident.client.fetch_page", return_value=always_5):
        result = collect_all(request_budget=1, page_delay_seconds=0)

    assert result.status == SyncStatus.PARTIAL
    assert result.error_code == "BUDGET_EXHAUSTED"


def test_c09_ext165_yyyy_passed_to_fetch():
    """collect_all(yyyy='2024') must pass yyyy to fetch_page."""
    from services.ext165_chemical_accident.sync import collect_all

    page1 = _xml_page([{"dataNo": "D2024-001"}], total_count=1)
    with patch("services.ext165_chemical_accident.client.fetch_page", return_value=page1) as mock_fetch:
        collect_all(yyyy="2024", dry_run=True, page_delay_seconds=0)

    assert mock_fetch.call_count == 1
    _, call_kwargs = mock_fetch.call_args
    assert call_kwargs.get("yyyy") == "2024"


def test_c10_ext165_http_error_returns_failed():
    from services.ext165_chemical_accident.sync import SyncStatus, collect_all

    with patch("services.ext165_chemical_accident.client.fetch_page", side_effect=OSError("connection refused")):
        result = collect_all(page_delay_seconds=0)

    assert result.status == SyncStatus.FAILED
    assert result.error_code == "HTTP_ERROR"


def test_c11_ext165_total_count_terminates():
    from services.ext165_chemical_accident.sync import SyncStatus, collect_all

    page1 = _xml_page([{"dataNo": f"D{i}"} for i in range(2)], total_count=2)
    with patch("services.ext165_chemical_accident.client.fetch_page", return_value=page1) as mock_fetch:
        result = collect_all(page_delay_seconds=0)

    assert mock_fetch.call_count == 1
    assert result.fetched == 2
    assert result.status == SyncStatus.COMPLETED


# ─────────────────────────────────────────────────────────────────────────────
# C12 — EXT-165 store
# ─────────────────────────────────────────────────────────────────────────────

def test_c12_ext165_content_hash_deterministic():
    from services.ext165_chemical_accident.parse import Ext165Item
    from services.ext165_chemical_accident.store import compute_content_hash

    items_a = [Ext165Item("D001"), Ext165Item("D002")]
    items_b = [Ext165Item("D002"), Ext165Item("D001")]
    assert compute_content_hash(items_a) == compute_content_hash(items_b)


# ─────────────────────────────────────────────────────────────────────────────
# C13-C16 — EXT-165 adapter
# ─────────────────────────────────────────────────────────────────────────────

def test_c13_ext165_adapter_preflight_missing_key(monkeypatch):
    from services.public_data_sync.adapters.ext165_chemical_accident import Ext165ChemicalAccidentAdapter
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    adapter = Ext165ChemicalAccidentAdapter()
    with pytest.raises(PreflightError):
        adapter.preflight(_ctx("EXT165_CHEMICAL_ACCIDENT"))


def test_c14_ext165_adapter_run_success():
    from services.ext165_chemical_accident.sync import SyncResult, SyncStatus
    from services.ext165_chemical_accident.parse import Ext165Item
    from services.public_data_sync.adapters.ext165_chemical_accident import Ext165ChemicalAccidentAdapter

    fake_items = [Ext165Item("D001"), Ext165Item("D002"), Ext165Item("D003")]
    fake_sync = SyncResult(
        status=SyncStatus.COMPLETED,
        fetched=3,
        items=fake_items,
        pages_fetched=1,
        budget_used=1,
    )

    def fake_collect(**kw):
        on_page_complete = kw.get("on_page_complete")
        if on_page_complete:
            on_page_complete(1, fake_items, 3, 3)
        return fake_sync

    with (
        patch("services.ext165_chemical_accident.store.create_staging_snapshot", return_value="snap-165"),
        patch("services.ext165_chemical_accident.store.save_page_checkpoint", return_value=3),
        patch("services.ext165_chemical_accident.sync.collect_all", side_effect=fake_collect),
        patch("services.ext165_chemical_accident.store.atomic_complete_snapshot", return_value=True),
    ):
        result = Ext165ChemicalAccidentAdapter().run(_ctx("EXT165_CHEMICAL_ACCIDENT"))

    assert result.status == RunStatus.SUCCESS
    assert result.fetched == 3
    assert result.change_detected is True


def test_c15_ext165_adapter_run_failed():
    from services.ext165_chemical_accident.sync import SyncResult, SyncStatus
    from services.public_data_sync.adapters.ext165_chemical_accident import Ext165ChemicalAccidentAdapter

    fake_sync = SyncResult(
        status=SyncStatus.FAILED,
        fetched=0,
        items=[],
        error_code="PARSE_ERROR",
        error_message="bad xml",
    )

    fail_mock = MagicMock()
    with (
        patch("services.ext165_chemical_accident.store.create_staging_snapshot", return_value="snap-165"),
        patch("services.ext165_chemical_accident.sync.collect_all", return_value=fake_sync),
        patch("services.ext165_chemical_accident.store.fail_snapshot", fail_mock),
    ):
        result = Ext165ChemicalAccidentAdapter().run(_ctx("EXT165_CHEMICAL_ACCIDENT"))

    assert result.status == RunStatus.FAILED
    assert result.error_code == "PARSE_ERROR"
    fail_mock.assert_called_once()


def test_c16_ext165_adapter_yyyy_from_metadata():
    """RunContext.metadata['yyyy'] must be forwarded to collect_all(yyyy=...)."""
    from services.ext165_chemical_accident.sync import SyncResult, SyncStatus
    from services.ext165_chemical_accident.parse import Ext165Item
    from services.public_data_sync.adapters.ext165_chemical_accident import Ext165ChemicalAccidentAdapter

    fake_sync = SyncResult(
        status=SyncStatus.COMPLETED,
        fetched=1,
        items=[Ext165Item("D-2024-001")],
        pages_fetched=1,
        budget_used=1,
    )

    fake_items = [Ext165Item("D-2024-001")]
    ctx = _ctx("EXT165_CHEMICAL_ACCIDENT", metadata={"yyyy": "2024"})
    captured_kwargs: list[dict] = []

    def fake_collect(**kw):
        captured_kwargs.append(kw)
        on_page_complete = kw.get("on_page_complete")
        if on_page_complete:
            on_page_complete(1, fake_items, 1, 1)
        return fake_sync

    with (
        patch("services.ext165_chemical_accident.store.create_staging_snapshot", return_value="snap-165"),
        patch("services.ext165_chemical_accident.store.save_page_checkpoint", return_value=1),
        patch("services.ext165_chemical_accident.sync.collect_all", side_effect=fake_collect),
        patch("services.ext165_chemical_accident.store.atomic_complete_snapshot", return_value=True),
    ):
        Ext165ChemicalAccidentAdapter().run(ctx)

    assert captured_kwargs[0].get("yyyy") == "2024"


# ─────────────────────────────────────────────────────────────────────────────
# C17-C18 — EXT-165 registry
# ─────────────────────────────────────────────────────────────────────────────

def test_c17_ext165_registry_entry_exists():
    from services.public_data_sync.registry import registry
    spec = registry.get("EXT165_CHEMICAL_ACCIDENT")
    assert spec.source_id == "EXT165_CHEMICAL_ACCIDENT"


def test_c18_ext165_registry_auto_refresh_false():
    from services.public_data_sync.registry import registry
    spec = registry.get("EXT165_CHEMICAL_ACCIDENT")
    assert spec.auto_refresh_candidate is False


# ─────────────────────────────────────────────────────────────────────────────
# D01-D04 — Generic budget
# ─────────────────────────────────────────────────────────────────────────────

def test_d01_budget_consume_or_raise_normal():
    from services.public_data_sync.budget import RequestBudget
    b = RequestBudget(limit=5)
    b.consume_or_raise(3)
    assert b.used == 3
    assert b.remaining == 2


def test_d02_budget_exceed_raises():
    from services.public_data_sync.budget import RequestBudget, RequestBudgetExceeded
    b = RequestBudget(limit=2)
    b.consume_or_raise(2)
    with pytest.raises(RequestBudgetExceeded):
        b.consume_or_raise(1)


def test_d03_budget_remaining():
    from services.public_data_sync.budget import RequestBudget
    b = RequestBudget(limit=10, used=7)
    assert b.remaining == 3
    assert b.exhausted is False
    b.consume_or_raise(3)
    assert b.exhausted is True
    assert b.remaining == 0


def test_d04_budget_exception_message():
    from services.public_data_sync.budget import RequestBudget, RequestBudgetExceeded
    b = RequestBudget(limit=1)
    b.consume_or_raise(1)
    with pytest.raises(RequestBudgetExceeded) as exc_info:
        b.consume_or_raise(1)
    assert "used=1" in str(exc_info.value)
    assert "limit=1" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# D05-D06 — register_builtin_adapters
# ─────────────────────────────────────────────────────────────────────────────

def test_d05_register_builtin_adapters_ext132_registered():
    from services.public_data_sync.adapters import AdapterRegistry, register_builtin_adapters

    reg = AdapterRegistry()
    # Patch the module-level adapter_registry to use our fresh instance
    with patch("services.public_data_sync.adapters.adapter_registry", reg):
        register_builtin_adapters()

    assert "ext132_hazardous_material" in reg.registered_keys()


def test_d06_register_builtin_adapters_ext165_registered():
    from services.public_data_sync.adapters import AdapterRegistry, register_builtin_adapters

    reg = AdapterRegistry()
    with patch("services.public_data_sync.adapters.adapter_registry", reg):
        register_builtin_adapters()

    assert "ext165_chemical_accident" in reg.registered_keys()


# ─────────────────────────────────────────────────────────────────────────────
# D07-D08 — runner integration (adapter lookup without actual I/O)
# ─────────────────────────────────────────────────────────────────────────────

def test_d07_runner_run_source_ext132_finds_adapter():
    """run_source should resolve EXT132 adapter without raising AdapterNotRegisteredError."""
    from services.public_data_sync.runner import run_source
    from services.public_data_sync.contracts import TriggerKind, RunStatus

    fake_result_data = {
        "run_id": "test-run",
        "source_id": "EXT132_HAZARDOUS_MATERIAL",
        "status": RunStatus.SUCCESS,
    }
    from services.public_data_sync.contracts import RunResult
    fake_result = RunResult(
        run_id="test-run",
        source_id="EXT132_HAZARDOUS_MATERIAL",
        status=RunStatus.SUCCESS,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )

    with (
        patch("services.public_data_sync.adapters.ext132_hazardous_material.Ext132HazardousMaterialAdapter.preflight"),
        patch("services.public_data_sync.adapters.ext132_hazardous_material.Ext132HazardousMaterialAdapter.run", return_value=fake_result),
    ):
        result = run_source("EXT132_HAZARDOUS_MATERIAL", run_id="test-run", trigger=TriggerKind.MANUAL)

    assert result.source_id == "EXT132_HAZARDOUS_MATERIAL"
    assert result.status == RunStatus.SUCCESS


def test_d08_runner_run_source_ext165_finds_adapter():
    from services.public_data_sync.runner import run_source
    from services.public_data_sync.contracts import TriggerKind, RunStatus, RunResult

    fake_result = RunResult(
        run_id="test-run-165",
        source_id="EXT165_CHEMICAL_ACCIDENT",
        status=RunStatus.SUCCESS,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )

    with (
        patch("services.public_data_sync.adapters.ext165_chemical_accident.Ext165ChemicalAccidentAdapter.preflight"),
        patch("services.public_data_sync.adapters.ext165_chemical_accident.Ext165ChemicalAccidentAdapter.run", return_value=fake_result),
    ):
        result = run_source("EXT165_CHEMICAL_ACCIDENT", run_id="test-run-165", trigger=TriggerKind.MANUAL)

    assert result.source_id == "EXT165_CHEMICAL_ACCIDENT"


# ─────────────────────────────────────────────────────────────────────────────
# D09-D11 — regression: existing adapters unaffected
# ─────────────────────────────────────────────────────────────────────────────

def test_d09_regression_keco_adapter_still_registered():
    from services.public_data_sync.adapters import AdapterRegistry, register_builtin_adapters

    reg = AdapterRegistry()
    with patch("services.public_data_sync.adapters.adapter_registry", reg):
        register_builtin_adapters()

    assert "keco_chemical" in reg.registered_keys()


def test_d10_regression_csi_adapter_still_registered():
    from services.public_data_sync.adapters import AdapterRegistry, register_builtin_adapters

    reg = AdapterRegistry()
    with patch("services.public_data_sync.adapters.adapter_registry", reg):
        register_builtin_adapters()

    assert "csi_accident" in reg.registered_keys()


def test_d11_regression_holiday_adapter_still_registered():
    from services.public_data_sync.adapters import AdapterRegistry, register_builtin_adapters

    reg = AdapterRegistry()
    with patch("services.public_data_sync.adapters.adapter_registry", reg):
        register_builtin_adapters()

    assert "holiday" in reg.registered_keys()


# ─────────────────────────────────────────────────────────────────────────────
# D12-D13 — migration draft files exist
# ─────────────────────────────────────────────────────────────────────────────

def test_d12_ext132_migration_draft_exists():
    import pathlib
    drafts = list(pathlib.Path("supabase/migrations").glob("*ext132*"))
    assert len(drafts) >= 1, "EXT-132 migration draft file not found"


def test_d13_ext165_migration_draft_exists():
    import pathlib
    drafts = list(pathlib.Path("supabase/migrations").glob("*ext165*"))
    assert len(drafts) >= 1, "EXT-165 migration draft file not found"


# ─────────────────────────────────────────────────────────────────────────────
# E01-E02 — GAP-A: dry_run adapter guard (no HTTP / no DB writes)
# ─────────────────────────────────────────────────────────────────────────────

def test_e01_gap_a_ext132_adapter_dry_run_returns_skipped():
    """GAP-A: dry_run=True must return SKIPPED without calling collect_all or any DB write."""
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter

    collect_mock = MagicMock()
    create_snap_mock = MagicMock()

    with (
        patch("services.ext132_hazardous_material.sync.collect_all", collect_mock),
        patch("services.ext132_hazardous_material.store.create_staging_snapshot", create_snap_mock),
    ):
        result = Ext132HazardousMaterialAdapter().run(_ctx("EXT132_HAZARDOUS_MATERIAL", dry_run=True))

    assert result.status == RunStatus.SKIPPED
    collect_mock.assert_not_called()
    create_snap_mock.assert_not_called()


def test_e02_gap_a_ext165_adapter_dry_run_returns_skipped():
    """GAP-A: dry_run=True must return SKIPPED without calling collect_all or any DB write."""
    from services.public_data_sync.adapters.ext165_chemical_accident import Ext165ChemicalAccidentAdapter

    collect_mock = MagicMock()
    create_snap_mock = MagicMock()

    with (
        patch("services.ext165_chemical_accident.sync.collect_all", collect_mock),
        patch("services.ext165_chemical_accident.store.create_staging_snapshot", create_snap_mock),
    ):
        result = Ext165ChemicalAccidentAdapter().run(_ctx("EXT165_CHEMICAL_ACCIDENT", dry_run=True))

    assert result.status == RunStatus.SKIPPED
    collect_mock.assert_not_called()
    create_snap_mock.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# E03-E09 — GAP-B: checkpoint / resume
# ─────────────────────────────────────────────────────────────────────────────

def test_e03_gap_b_collect_all_start_page_no_skips_earlier_pages():
    """GAP-B: start_page_no=3 must request page 3 first, not page 1 or 2."""
    from services.ext132_hazardous_material.sync import collect_all

    page3 = _xml_page([{"chemicalno": "A003"}], total_count=3)
    fetched_pages = []

    def _fetch(page_no, **kw):
        fetched_pages.append(page_no)
        return page3

    with patch("services.ext132_hazardous_material.client.fetch_page", side_effect=_fetch):
        collect_all(start_page_no=3, page_delay_seconds=0)

    assert 1 not in fetched_pages
    assert 2 not in fetched_pages
    assert 3 in fetched_pages


def test_e04_gap_b_collect_all_on_page_complete_called_per_page():
    """GAP-B/R3-02: on_page_complete callback receives (page_no, page_items, total_collected, total_count_from_api)."""
    from services.ext132_hazardous_material.sync import collect_all

    page1 = _xml_page([{"chemicalno": "A1"}, {"chemicalno": "A2"}], total_count=4)
    page2 = _xml_page([{"chemicalno": "A3"}, {"chemicalno": "A4"}], total_count=4)
    pages = iter([page1, page2])
    callback_calls: list[tuple] = []

    def _fetch(page_no, **kw):
        return next(pages)

    def _on_page(page_no, page_items, total_collected, total_count_from_api):
        callback_calls.append((page_no, [i.chemicalno for i in page_items], total_collected, total_count_from_api))

    with patch("services.ext132_hazardous_material.client.fetch_page", side_effect=_fetch):
        collect_all(on_page_complete=_on_page, page_delay_seconds=0)

    assert len(callback_calls) == 2
    # page_items contains THIS page's items only
    assert callback_calls[0] == (1, ["A1", "A2"], 2, 4)
    assert callback_calls[1] == (2, ["A3", "A4"], 4, 4)


def test_e05_gap_b_collect_all_aborts_when_total_count_changes():
    """GAP-B: expected_total_count mismatch on resume must return ABORTED_TOTAL_CHANGED."""
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all

    page_with_different_total = _xml_page([{"chemicalno": "A1"}], total_count=999)

    with patch("services.ext132_hazardous_material.client.fetch_page", return_value=page_with_different_total):
        result = collect_all(
            start_page_no=5,
            expected_total_count=100,  # expected differs from API's 999
            page_delay_seconds=0,
        )

    assert result.status == SyncStatus.ABORTED_TOTAL_CHANGED
    assert result.error_code == "TOTAL_COUNT_CHANGED"


def test_e06_gap_b_update_checkpoint_calls_db():
    """GAP-B: update_checkpoint must write last_page_no and checkpoint fields to DB."""
    from services.ext132_hazardous_material.store import update_checkpoint

    mock_sb = MagicMock()
    update_chain = mock_sb.table.return_value.update.return_value.eq.return_value
    update_chain.execute.return_value.data = [{"id": "snap-1"}]

    update_checkpoint("snap-1", last_page_no=5, items_so_far=42, total_count_from_api=200, sb=mock_sb)

    mock_sb.table.assert_called_once_with("ext132_hazardous_material_snapshots")
    update_payload = mock_sb.table.return_value.update.call_args[0][0]
    assert update_payload["last_page_no"] == 5
    assert update_payload["checkpoint_total_count"] == 42
    assert update_payload["checkpoint_api_total"] == 200


def test_e07_gap_b_find_resumable_staging_returns_row():
    """GAP-B: find_resumable_staging must query for STAGING rows ordered by created_at desc."""
    from services.ext132_hazardous_material.store import find_resumable_staging

    mock_sb = MagicMock()
    fake_row = {"id": "staging-snap", "run_id": "run-1", "last_page_no": 7}
    (mock_sb.table.return_value
     .select.return_value.eq.return_value.eq.return_value
     .order.return_value.limit.return_value.execute.return_value.data) = [fake_row]

    result = find_resumable_staging(source_id="EXT132_HAZARDOUS_MATERIAL", sb=mock_sb)

    assert result == fake_row
    mock_sb.table.assert_called_once_with("ext132_hazardous_material_snapshots")


def test_e08_gap_b_ext132_adapter_resume_reuses_snapshot():
    """GAP-B: resume_snapshot_id in ctx.metadata must skip create_staging_snapshot."""
    from services.ext132_hazardous_material.sync import SyncResult, SyncStatus
    from services.ext132_hazardous_material.parse import Ext132Item
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter

    fake_items = [Ext132Item("A001")]
    fake_sync = SyncResult(
        status=SyncStatus.COMPLETED,
        fetched=1,
        items=fake_items,
        pages_fetched=3,
        budget_used=3,
    )

    create_snap_mock = MagicMock()
    collect_mock = MagicMock(return_value=fake_sync)

    ctx = _ctx("EXT132_HAZARDOUS_MATERIAL", metadata={
        "resume_snapshot_id": "existing-snap-id",
        "resume_from_page": "4",
        "expected_total_count": 100,
    })

    with (
        patch("services.ext132_hazardous_material.store.create_staging_snapshot", create_snap_mock),
        patch("services.ext132_hazardous_material.sync.collect_all", collect_mock),
        patch("services.ext132_hazardous_material.store.atomic_complete_snapshot", return_value=True),
        patch("services.ext132_hazardous_material.store.compute_content_hash_from_db", return_value="hash-resume-132"),
    ):
        result = Ext132HazardousMaterialAdapter().run(ctx)

    create_snap_mock.assert_not_called()
    _, call_kwargs = collect_mock.call_args
    assert call_kwargs.get("start_page_no") == 4
    assert call_kwargs.get("expected_total_count") == 100
    assert result.status == RunStatus.SUCCESS


def test_e09_gap_b_ext165_adapter_resume_passes_params():
    """GAP-B: resume params forwarded to collect_all, snapshot not re-created."""
    from services.ext165_chemical_accident.sync import SyncResult, SyncStatus
    from services.ext165_chemical_accident.parse import Ext165Item
    from services.public_data_sync.adapters.ext165_chemical_accident import Ext165ChemicalAccidentAdapter

    fake_sync = SyncResult(
        status=SyncStatus.COMPLETED,
        fetched=1,
        items=[Ext165Item("D999")],
        pages_fetched=2,
        budget_used=2,
    )

    create_snap_mock = MagicMock()
    collect_mock = MagicMock(return_value=fake_sync)

    ctx = _ctx("EXT165_CHEMICAL_ACCIDENT", metadata={
        "resume_snapshot_id": "snap-165-existing",
        "resume_from_page": "6",
    })

    with (
        patch("services.ext165_chemical_accident.store.create_staging_snapshot", create_snap_mock),
        patch("services.ext165_chemical_accident.sync.collect_all", collect_mock),
        patch("services.ext165_chemical_accident.store.atomic_complete_snapshot", return_value=True),
        patch("services.ext165_chemical_accident.store.compute_content_hash_from_db", return_value="hash-resume-165"),
    ):
        Ext165ChemicalAccidentAdapter().run(ctx)

    create_snap_mock.assert_not_called()
    _, call_kwargs = collect_mock.call_args
    assert call_kwargs.get("start_page_no") == 6


# ─────────────────────────────────────────────────────────────────────────────
# E10-E14 — R3-01: CLI bootstrap uses existing MANUAL lock (FAIL-CLOSED)
# ─────────────────────────────────────────────────────────────────────────────

import importlib.util as _iutil
import pathlib as _pathlib

_REPO_ROOT = _pathlib.Path(__file__).parent.parent


def _load_bootstrap(tool_path: str):
    p = _REPO_ROOT / tool_path
    spec = _iutil.spec_from_file_location("_bootstrap_tmp", p)
    mod = _iutil.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_e10_r3_01_claim_run_success_uses_manual_trigger():
    """R3-01: _claim_run uses TriggerKind.MANUAL and returns (store, run_id) on success."""
    from services.public_data_sync.contracts import TriggerKind
    bootstrap = _load_bootstrap("tools/ext132/bootstrap.py")

    mock_store = MagicMock()
    mock_claim = MagicMock()
    mock_claim.claimed = True
    mock_claim.lease_until = "2099-01-01T00:00:00Z"
    captured_trigger: list = []

    def _check_claim(run_id, spec, trigger, now):
        captured_trigger.append(trigger)
        return mock_claim

    mock_store.claim_run.side_effect = _check_claim
    mock_spec = MagicMock()

    with (
        patch("services.public_data_sync.runtime_store.PublicDataRuntimeStore", return_value=mock_store),
        patch("services.public_data_sync.registry.registry.get", return_value=mock_spec),
    ):
        result_store, result_info = bootstrap._claim_run("test-run-id")

    assert result_store is mock_store
    assert result_info == "test-run-id"
    assert len(captured_trigger) == 1
    assert captured_trigger[0] == TriggerKind.MANUAL


def test_e11_r3_01_claim_run_unknown_source_returns_none():
    """R3-01: UNKNOWN_SOURCE_RUNTIME must return None, reason tuple (FAIL-CLOSED)."""
    bootstrap = _load_bootstrap("tools/ext132/bootstrap.py")

    mock_store = MagicMock()
    mock_claim = MagicMock()
    mock_claim.claimed = False
    mock_claim.reason = "UNKNOWN_SOURCE_RUNTIME"
    mock_store.claim_run.return_value = mock_claim
    mock_spec = MagicMock()

    with (
        patch("services.public_data_sync.runtime_store.PublicDataRuntimeStore", return_value=mock_store),
        patch("services.public_data_sync.registry.registry.get", return_value=mock_spec),
    ):
        result_store, reason = bootstrap._claim_run("test-run-id")

    assert result_store is None
    assert reason == "UNKNOWN_SOURCE_RUNTIME"


def test_e12_r3_01_claim_run_source_busy_returns_none():
    """R3-01: SOURCE_BUSY must return None (FAIL-CLOSED — no graceful degradation)."""
    bootstrap = _load_bootstrap("tools/ext132/bootstrap.py")

    mock_store = MagicMock()
    mock_claim = MagicMock()
    mock_claim.claimed = False
    mock_claim.reason = "SOURCE_BUSY"
    mock_store.claim_run.return_value = mock_claim
    mock_spec = MagicMock()

    with (
        patch("services.public_data_sync.runtime_store.PublicDataRuntimeStore", return_value=mock_store),
        patch("services.public_data_sync.registry.registry.get", return_value=mock_spec),
    ):
        result_store, reason = bootstrap._claim_run("test-run-id")

    assert result_store is None
    assert reason == "SOURCE_BUSY"


def test_e13_r3_01_claim_run_rpc_exception_returns_none():
    """R3-01: Exception during claim_run returns None (FAIL-CLOSED)."""
    bootstrap = _load_bootstrap("tools/ext132/bootstrap.py")

    mock_store = MagicMock()
    mock_store.claim_run.side_effect = RuntimeError("DB connection failed")
    mock_spec = MagicMock()

    with (
        patch("services.public_data_sync.runtime_store.PublicDataRuntimeStore", return_value=mock_store),
        patch("services.public_data_sync.registry.registry.get", return_value=mock_spec),
    ):
        result_store, reason = bootstrap._claim_run("test-run-id")

    assert result_store is None
    assert "DB connection failed" in reason


def test_e14_r3_01_ext165_claim_run_fail_closed():
    """R3-01: EXT-165 bootstrap _claim_run must also be FAIL-CLOSED."""
    bootstrap = _load_bootstrap("tools/ext165/bootstrap.py")

    mock_store = MagicMock()
    mock_claim = MagicMock()
    mock_claim.claimed = False
    mock_claim.reason = "UNKNOWN_SOURCE_RUNTIME"
    mock_store.claim_run.return_value = mock_claim
    mock_spec = MagicMock()

    with (
        patch("services.public_data_sync.runtime_store.PublicDataRuntimeStore", return_value=mock_store),
        patch("services.public_data_sync.registry.registry.get", return_value=mock_spec),
    ):
        result_store, reason = bootstrap._claim_run("test-run-id")

    assert result_store is None
    assert reason == "UNKNOWN_SOURCE_RUNTIME"


# ─────────────────────────────────────────────────────────────────────────────
# E15-E19 — GAP-D: atomic_complete_snapshot RPC
# ─────────────────────────────────────────────────────────────────────────────

def test_e15_gap_d_atomic_complete_snapshot_calls_rpc():
    """GAP-D: atomic_complete_snapshot must call fn_ext132_complete_snapshot RPC."""
    from services.ext132_hazardous_material.store import atomic_complete_snapshot

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value.data = True

    result = atomic_complete_snapshot(
        "snap-1",
        source_id="EXT132_HAZARDOUS_MATERIAL",
        total_items=42,
        content_hash="abc123",
        run_id="test-run-id",
        sb=mock_sb,
    )

    mock_sb.rpc.assert_called_once_with("fn_ext132_complete_snapshot", {
        "p_snapshot_id": "snap-1",
        "p_source_id": "EXT132_HAZARDOUS_MATERIAL",
        "p_total_items": 42,
        "p_content_hash": "abc123",
        "p_run_id": "test-run-id",
    })
    assert result is True


def test_e16_gap_d_atomic_complete_snapshot_returns_true_on_truthy():
    """GAP-D: atomic_complete_snapshot returns True when RPC returns truthy."""
    from services.ext132_hazardous_material.store import atomic_complete_snapshot

    for truthy_val in [True, 1, [True], {"result": True}]:
        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = truthy_val
        result = atomic_complete_snapshot("snap-1", source_id="X", total_items=1, content_hash="h", run_id="run-x", sb=mock_sb)
        assert result is True, f"Expected True for data={truthy_val!r}"


def test_e17_gap_d_atomic_complete_snapshot_raises_on_rpc_exception():
    """GAP-D: RPC failure must raise RuntimeError (not swallow the error)."""
    from services.ext132_hazardous_material.store import atomic_complete_snapshot

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.side_effect = Exception("connection timeout")

    with pytest.raises(RuntimeError, match="fn_ext132_complete_snapshot"):
        atomic_complete_snapshot("snap-1", source_id="X", total_items=1, content_hash="h", run_id="run-x", sb=mock_sb)


def test_e18_gap_d_ext165_atomic_complete_snapshot_calls_correct_rpc():
    """GAP-D: EXT-165 must call fn_ext165_complete_snapshot (not fn_ext132_...)."""
    from services.ext165_chemical_accident.store import atomic_complete_snapshot

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value.data = True

    atomic_complete_snapshot(
        "snap-165",
        source_id="EXT165_CHEMICAL_ACCIDENT",
        total_items=10,
        content_hash="xyz",
        run_id="run-165",
        sb=mock_sb,
    )

    rpc_name = mock_sb.rpc.call_args[0][0]
    assert rpc_name == "fn_ext165_complete_snapshot"


def test_e19_gap_d_migration_drafts_contain_checkpoint_and_rpc_fields():
    """GAP-D/GAP-B: migration drafts must contain checkpoint columns and RPC definitions."""
    import pathlib

    for pattern, expected_fragments in [
        ("*ext132*", ["last_page_no", "checkpoint_total_count", "fn_ext132_complete_snapshot", "p_run_id"]),
        ("*ext165*", ["last_page_no", "checkpoint_total_count", "fn_ext165_complete_snapshot", "p_run_id"]),
    ]:
        drafts = list(pathlib.Path("supabase/migrations").glob(pattern))
        assert drafts, f"No migration draft for {pattern}"
        content = drafts[0].read_text()
        for fragment in expected_fragments:
            assert fragment in content, f"Expected '{fragment}' in {drafts[0].name}"


# ─────────────────────────────────────────────────────────────────────────────
# F01-F13 — PATCH-001: dry-run/probe split, save_page_checkpoint, fencing, is_current
# ─────────────────────────────────────────────────────────────────────────────

def test_f01_patch01_ext132_dry_run_no_http_no_db(capsys):
    """PATCH-01: ext132 dry-run parses fixture XML without HTTP or DB calls."""
    bootstrap = _load_bootstrap("tools/ext132/bootstrap.py")
    with patch("services.ext132_hazardous_material.sync.collect_all") as mock_collect:
        rc = bootstrap.cmd_dry_run()
    mock_collect.assert_not_called()
    assert rc == 0
    out = capsys.readouterr().out
    assert "fixture_items" in out
    assert "FIXTURE-001" in out


def test_f02_patch01_ext132_probe_calls_collect_dry_run():
    """PATCH-01: ext132 probe calls collect_all(dry_run=True) — real API sample path."""
    from services.ext132_hazardous_material.sync import SyncResult, SyncStatus
    bootstrap = _load_bootstrap("tools/ext132/bootstrap.py")
    fake_result = SyncResult(status=SyncStatus.COMPLETED, fetched=3, items=[], pages_fetched=1, budget_used=1)
    with patch("services.ext132_hazardous_material.sync.collect_all", return_value=fake_result) as mock_collect:
        rc = bootstrap.cmd_probe()
    mock_collect.assert_called_once()
    assert mock_collect.call_args[1].get("dry_run") is True
    assert rc == 0


def test_f03_patch01_ext165_dry_run_no_http_no_db(capsys):
    """PATCH-01: ext165 dry-run parses fixture XML without HTTP or DB calls."""
    bootstrap = _load_bootstrap("tools/ext165/bootstrap.py")
    with patch("services.ext165_chemical_accident.sync.collect_all") as mock_collect:
        rc = bootstrap.cmd_dry_run()
    mock_collect.assert_not_called()
    assert rc == 0
    out = capsys.readouterr().out
    assert "fixture_items" in out
    assert "FIXTURE-001" in out


def test_f04_patch01_ext165_probe_calls_collect_dry_run():
    """PATCH-01: ext165 probe calls collect_all(dry_run=True) — real API sample path."""
    from services.ext165_chemical_accident.sync import SyncResult, SyncStatus
    bootstrap = _load_bootstrap("tools/ext165/bootstrap.py")
    fake_result = SyncResult(status=SyncStatus.COMPLETED, fetched=2, items=[], pages_fetched=1, budget_used=1)
    with patch("services.ext165_chemical_accident.sync.collect_all", return_value=fake_result) as mock_collect:
        rc = bootstrap.cmd_probe()
    mock_collect.assert_called_once()
    assert mock_collect.call_args[1].get("dry_run") is True
    assert rc == 0


def test_f05_patch02_ext132_save_page_checkpoint_calls_rpc():
    """PATCH-02/03: save_page_checkpoint calls fn_ext132_save_page_checkpoint with run_id."""
    from services.ext132_hazardous_material.store import save_page_checkpoint
    from services.ext132_hazardous_material.parse import Ext132Item

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value.data = 3

    items = [Ext132Item("C001"), Ext132Item("C002"), Ext132Item("C003")]
    result = save_page_checkpoint("snap-x", items, page_no=2, api_total=100, run_id="run-abc", sb=mock_sb)

    mock_sb.rpc.assert_called_once_with("fn_ext132_save_page_checkpoint", {
        "p_snapshot_id": "snap-x",
        "p_items": [{"chemicalno": "C001", "raw": {}}, {"chemicalno": "C002", "raw": {}}, {"chemicalno": "C003", "raw": {}}],
        "p_page_no": 2,
        "p_api_total": 100,
        "p_run_id": "run-abc",
    })
    assert result == 3


def test_f06_patch02_ext165_save_page_checkpoint_calls_rpc():
    """PATCH-02/03: save_page_checkpoint calls fn_ext165_save_page_checkpoint with run_id."""
    from services.ext165_chemical_accident.store import save_page_checkpoint
    from services.ext165_chemical_accident.parse import Ext165Item

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value.data = 2

    items = [Ext165Item("D001"), Ext165Item("D002")]
    result = save_page_checkpoint("snap-165", items, page_no=1, api_total=50, run_id="run-xyz", sb=mock_sb)

    mock_sb.rpc.assert_called_once_with("fn_ext165_save_page_checkpoint", {
        "p_snapshot_id": "snap-165",
        "p_items": [{"datano": "D001", "raw": {}}, {"datano": "D002", "raw": {}}],
        "p_page_no": 1,
        "p_api_total": 50,
        "p_run_id": "run-xyz",
    })
    assert result == 2


def test_f07_patch02_save_page_checkpoint_raises_on_rpc_failure():
    """PATCH-02: save_page_checkpoint raises RuntimeError for non-fencing RPC failures."""
    from services.ext132_hazardous_material.store import save_page_checkpoint
    from services.ext132_hazardous_material.parse import Ext132Item

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.side_effect = Exception("DB unavailable")

    with pytest.raises(RuntimeError, match="fn_ext132_save_page_checkpoint"):
        save_page_checkpoint("snap-x", [Ext132Item("A")], page_no=1, api_total=None, run_id="run-1", sb=mock_sb)


def test_f07b_patch03_save_page_checkpoint_raises_page_fenced_on_run_fenced():
    """PATCH-03: save_page_checkpoint raises PageFencedError when RPC signals RUN_FENCED."""
    from services.ext132_hazardous_material.store import save_page_checkpoint
    from services.ext132_hazardous_material.parse import Ext132Item
    from services.public_data_sync.errors import PageFencedError

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.side_effect = Exception("RUN_FENCED: run_id=abc is not current owner")

    with pytest.raises(PageFencedError):
        save_page_checkpoint("snap-x", [Ext132Item("A")], page_no=1, api_total=None, run_id="run-abc", sb=mock_sb)


def test_f08_patch02_migration_drafts_contain_save_page_checkpoint():
    """PATCH-02: migration drafts must define fn_ext132/165_save_page_checkpoint RPC."""
    import pathlib

    for pattern, fn_name in [
        ("*ext132*", "fn_ext132_save_page_checkpoint"),
        ("*ext165*", "fn_ext165_save_page_checkpoint"),
    ]:
        drafts = list(pathlib.Path("supabase/migrations").glob(pattern))
        assert drafts, f"No migration draft for {pattern}"
        content = drafts[0].read_text()
        assert fn_name in content, f"Expected '{fn_name}' in {drafts[0].name}"


def test_f09_patch03_ext132_sync_page_fenced_error_returns_fenced():
    """PATCH-03: PageFencedError from on_page_complete stops collection, returns FENCED."""
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all
    from services.public_data_sync.errors import PageFencedError

    page1 = _xml_page([{"chemicalno": f"A{i}"} for i in range(3)], total_count=9)

    def _fencing_callback(page_no, page_items, total_collected, total_count_from_api):
        raise PageFencedError("lease stolen")

    with patch("services.ext132_hazardous_material.client.fetch_page", return_value=page1):
        result = collect_all(on_page_complete=_fencing_callback, page_delay_seconds=0)

    assert result.status == SyncStatus.FAILED
    assert result.error_code == "FENCED"


def test_f10_patch03_ext165_sync_page_fenced_error_returns_fenced():
    """PATCH-03: ext165 PageFencedError from on_page_complete stops collection."""
    from services.ext165_chemical_accident.sync import SyncStatus, collect_all
    from services.public_data_sync.errors import PageFencedError

    page1 = _xml_page([{"dataNo": f"D{i}"} for i in range(2)], total_count=4)

    def _fencing_callback(page_no, page_items, total_collected, total_count_from_api):
        raise PageFencedError("lease expired")

    with patch("services.ext165_chemical_accident.client.fetch_page", return_value=page1):
        result = collect_all(on_page_complete=_fencing_callback, page_delay_seconds=0)

    assert result.status == SyncStatus.FAILED
    assert result.error_code == "FENCED"


def test_f11_patch04_migration_drafts_contain_is_current():
    """PATCH-04: migration drafts must define is_current column for canonical snapshot pointer."""
    import pathlib

    for pattern in ("*ext132*", "*ext165*"):
        drafts = list(pathlib.Path("supabase/migrations").glob(pattern))
        assert drafts, f"No migration draft for {pattern}"
        content = drafts[0].read_text()
        assert "is_current" in content, f"Expected 'is_current' in {drafts[0].name}"


def test_f12_patch04_ext132_get_latest_completed_snapshot_uses_is_current():
    """PATCH-04: get_latest_completed_snapshot must filter by is_current=True."""
    from services.ext132_hazardous_material.store import get_latest_completed_snapshot

    mock_sb = MagicMock()
    mock_chain = mock_sb.table.return_value.select.return_value
    mock_chain.eq.return_value = mock_chain
    mock_chain.order.return_value = mock_chain
    mock_chain.limit.return_value = mock_chain
    mock_chain.execute.return_value.data = [{"id": "snap-1", "status": "COMPLETED", "is_current": True}]

    get_latest_completed_snapshot(sb=mock_sb)

    eq_calls = [str(c) for c in mock_chain.eq.call_args_list]
    assert any("is_current" in c and "True" in c for c in eq_calls), \
        f"Expected eq('is_current', True) in calls: {eq_calls}"


def test_f13_patch04_ext165_get_latest_completed_snapshot_uses_is_current():
    """PATCH-04: ext165 get_latest_completed_snapshot must filter by is_current=True."""
    from services.ext165_chemical_accident.store import get_latest_completed_snapshot

    mock_sb = MagicMock()
    mock_chain = mock_sb.table.return_value.select.return_value
    mock_chain.eq.return_value = mock_chain
    mock_chain.order.return_value = mock_chain
    mock_chain.limit.return_value = mock_chain
    mock_chain.execute.return_value.data = [{"id": "snap-165", "status": "COMPLETED", "is_current": True}]

    get_latest_completed_snapshot(sb=mock_sb)

    eq_calls = [str(c) for c in mock_chain.eq.call_args_list]
    assert any("is_current" in c and "True" in c for c in eq_calls), \
        f"Expected eq('is_current', True) in calls: {eq_calls}"


def test_f14_patch03_resume_ownership_adapter_passes_ctx_run_id():
    """PATCH-03/Resume: _on_page_complete must pass ctx.run_id to save_page_checkpoint (not old run_id)."""
    from services.ext132_hazardous_material.sync import SyncResult, SyncStatus
    from services.ext132_hazardous_material.parse import Ext132Item
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter

    fake_items = [Ext132Item("R001")]
    fake_sync = SyncResult(status=SyncStatus.COMPLETED, fetched=1, items=fake_items, pages_fetched=1, budget_used=1)

    captured_run_ids: list[str] = []

    def spy_save(snapshot_id, page_items, page_no, api_total, *, run_id, sb=None):
        captured_run_ids.append(run_id)
        return 1

    def fake_collect(**kw):
        on_page_complete = kw.get("on_page_complete")
        if on_page_complete:
            on_page_complete(1, fake_items, 1, 1)
        return fake_sync

    resume_ctx = _ctx("EXT132_HAZARDOUS_MATERIAL", metadata={
        "resume_snapshot_id": "old-snap-id",
        "resume_from_page": "3",
    })

    with (
        patch("services.ext132_hazardous_material.store.create_staging_snapshot"),
        patch("services.ext132_hazardous_material.store.save_page_checkpoint", side_effect=spy_save),
        patch("services.ext132_hazardous_material.sync.collect_all", side_effect=fake_collect),
        patch("services.ext132_hazardous_material.store.atomic_complete_snapshot", return_value=True),
        patch("services.ext132_hazardous_material.store.compute_content_hash_from_db", return_value="h"),
    ):
        Ext132HazardousMaterialAdapter().run(resume_ctx)

    assert len(captured_run_ids) == 1
    assert captured_run_ids[0] == resume_ctx.run_id, \
        f"Expected ctx.run_id={resume_ctx.run_id!r}, got {captured_run_ids[0]!r}"


def test_f15_patch04_migration_drafts_contain_is_current_unique_index():
    """PATCH-04: migration drafts must define uidx_*_snapshots_one_current partial unique index."""
    import pathlib

    for pattern, idx_name in [
        ("*ext132*", "uidx_ext132_snapshots_one_current"),
        ("*ext165*", "uidx_ext165_snapshots_one_current"),
    ]:
        drafts = list(pathlib.Path("supabase/migrations").glob(pattern))
        assert drafts, f"No migration draft for {pattern}"
        content = drafts[0].read_text()
        assert idx_name in content, f"Expected '{idx_name}' in {drafts[0].name}"
        assert "where is_current = true" in content, \
            f"Expected partial index condition 'where is_current = true' in {drafts[0].name}"


# ─────────────────────────────────────────────────────────────────────────────
# G01-G13 — PATCH-002: HTTP contract, resultCode, PARTIAL block, PageSaveError,
#            SQL promotion order, content hash, collect_scope
# ─────────────────────────────────────────────────────────────────────────────

def test_g01_ext132_client_http_200_returns_bytes(monkeypatch):
    """PATCH-002-01: kr_get() returns (status_code, text) tuple; client unpacks to bytes."""
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "test-key")
    xml_text = "<?xml version='1.0'?><response/>"
    with patch("services.kr_public_api.kr_get", return_value=(200, xml_text)):
        from services.ext132_hazardous_material.client import fetch_page
        result = fetch_page(1)
    assert result == xml_text.encode("utf-8")


def test_g02_ext132_client_http_401_raises_environment_error(monkeypatch):
    """PATCH-002-01: HTTP 401 from tuple contract → EnvironmentError (auth failure)."""
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "test-key")
    with patch("services.kr_public_api.kr_get", return_value=(401, "")):
        from services.ext132_hazardous_material.client import fetch_page
        with pytest.raises(EnvironmentError, match="401"):
            fetch_page(1)


def test_g03_ext132_client_http_500_raises_ioerror(monkeypatch):
    """PATCH-002-01: HTTP 5xx from tuple contract → IOError."""
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "test-key")
    with patch("services.kr_public_api.kr_get", return_value=(500, "")):
        from services.ext132_hazardous_material.client import fetch_page
        with pytest.raises(IOError):
            fetch_page(1)


def test_g04_ext165_client_http_200_returns_bytes(monkeypatch):
    """PATCH-002-01: ext165 kr_get() tuple unpacked to bytes."""
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "test-key")
    xml_text = "<?xml version='1.0'?><response/>"
    with patch("services.kr_public_api.kr_get", return_value=(200, xml_text)):
        from services.ext165_chemical_accident.client import fetch_page
        result = fetch_page(1)
    assert result == xml_text.encode("utf-8")


def _xml_page_error(result_code: str) -> bytes:
    """XML page with a non-'00' resultCode for PATCH-002-05 tests."""
    return (
        f"<?xml version='1.0' encoding='UTF-8'?>"
        f"<response><header><resultCode>{result_code}</resultCode>"
        f"<resultMsg>ERROR</resultMsg></header>"
        f"<body><pageNo>1</pageNo><numOfRows>10</numOfRows><items></items></body></response>"
    ).encode()


def test_g05_ext132_sync_result_code_nonzero_returns_failed():
    """PATCH-002-05: resultCode '99' → SyncStatus.FAILED with error_code=API_ERROR_CODE."""
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all

    with patch("services.ext132_hazardous_material.client.fetch_page", return_value=_xml_page_error("99")):
        result = collect_all(page_delay_seconds=0)

    assert result.status == SyncStatus.FAILED
    assert result.error_code == "API_ERROR_CODE"
    assert "resultCode=99" in (result.error_message or "")


def test_g06_ext165_sync_result_code_nonzero_returns_failed():
    """PATCH-002-05: ext165 resultCode '01' → SyncStatus.FAILED with error_code=API_ERROR_CODE."""
    from services.ext165_chemical_accident.sync import SyncStatus, collect_all

    with patch("services.ext165_chemical_accident.client.fetch_page", return_value=_xml_page_error("01")):
        result = collect_all(page_delay_seconds=0)

    assert result.status == SyncStatus.FAILED
    assert result.error_code == "API_ERROR_CODE"
    assert "resultCode=01" in (result.error_message or "")


def test_g07_ext132_adapter_partial_safety_cap_returns_failed():
    """PATCH-003: SAFETY_CAP PARTIAL → FAILED, fail_snapshot NOT called (snapshot preserved for resume)."""
    from services.ext132_hazardous_material.sync import SyncResult, SyncStatus
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter

    fake_sync = SyncResult(
        status=SyncStatus.PARTIAL,
        fetched=3,
        items=[],
        error_code="SAFETY_CAP",
    )

    fail_mock = MagicMock()
    atomic_mock = MagicMock()
    with (
        patch("services.ext132_hazardous_material.store.create_staging_snapshot", return_value="snap-cap"),
        patch("services.ext132_hazardous_material.sync.collect_all", return_value=fake_sync),
        patch("services.ext132_hazardous_material.store.fail_snapshot", fail_mock),
        patch("services.ext132_hazardous_material.store.atomic_complete_snapshot", atomic_mock),
    ):
        result = Ext132HazardousMaterialAdapter().run(_ctx("EXT132_HAZARDOUS_MATERIAL"))

    assert result.status == RunStatus.FAILED
    assert result.error_code == "SAFETY_CAP"
    assert (result.details or {}).get("snapshot_preserved") is True
    fail_mock.assert_not_called()
    atomic_mock.assert_not_called()


def test_g08_ext165_adapter_partial_returns_failed():
    """PATCH-003: ext165 PARTIAL → FAILED, fail_snapshot NOT called (snapshot preserved for resume)."""
    from services.ext165_chemical_accident.sync import SyncResult, SyncStatus
    from services.public_data_sync.adapters.ext165_chemical_accident import Ext165ChemicalAccidentAdapter

    fake_sync = SyncResult(
        status=SyncStatus.PARTIAL,
        fetched=5,
        items=[],
        error_code="BUDGET_EXHAUSTED",
    )

    fail_mock = MagicMock()
    atomic_mock = MagicMock()
    with (
        patch("services.ext165_chemical_accident.store.create_staging_snapshot", return_value="snap-165-p"),
        patch("services.ext165_chemical_accident.sync.collect_all", return_value=fake_sync),
        patch("services.ext165_chemical_accident.store.fail_snapshot", fail_mock),
        patch("services.ext165_chemical_accident.store.atomic_complete_snapshot", atomic_mock),
    ):
        result = Ext165ChemicalAccidentAdapter().run(_ctx("EXT165_CHEMICAL_ACCIDENT"))

    assert result.status == RunStatus.FAILED
    assert result.error_code == "BUDGET_EXHAUSTED"
    assert (result.details or {}).get("snapshot_preserved") is True
    fail_mock.assert_not_called()
    atomic_mock.assert_not_called()


def test_g09_ext132_sync_page_save_error_returns_failed():
    """PATCH-002-03: PageSaveError from on_page_complete → SyncStatus.FAILED(SAVE_ERROR)."""
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all
    from services.public_data_sync.errors import PageSaveError

    page1 = _xml_page([{"chemicalno": f"A{i}"} for i in range(3)], total_count=3)

    def _save_error_callback(page_no, page_items, total_collected, total_count_from_api):
        raise PageSaveError("DB write failed for page 1")

    with patch("services.ext132_hazardous_material.client.fetch_page", return_value=page1):
        result = collect_all(on_page_complete=_save_error_callback, page_delay_seconds=0)

    assert result.status == SyncStatus.FAILED
    assert result.error_code == "SAVE_ERROR"
    assert "DB write failed" in (result.error_message or "")


def test_g10_ext165_sync_page_save_error_returns_failed():
    """PATCH-002-03: ext165 PageSaveError → SyncStatus.FAILED(SAVE_ERROR)."""
    from services.ext165_chemical_accident.sync import SyncStatus, collect_all
    from services.public_data_sync.errors import PageSaveError

    page1 = _xml_page([{"dataNo": f"D{i}"} for i in range(2)], total_count=2)

    def _save_error_callback(page_no, page_items, total_collected, total_count_from_api):
        raise PageSaveError("RPC timeout on page 1")

    with patch("services.ext165_chemical_accident.client.fetch_page", return_value=page1):
        result = collect_all(on_page_complete=_save_error_callback, page_delay_seconds=0)

    assert result.status == SyncStatus.FAILED
    assert result.error_code == "SAVE_ERROR"


def test_g11_sql_promotion_order_clear_before_set():
    """PATCH-002-02: migration drafts must clear old is_current=false BEFORE setting new is_current=true."""
    import pathlib

    for pattern, fn_name in [
        ("*ext132*", "fn_ext132_complete_snapshot"),
        ("*ext165*", "fn_ext165_complete_snapshot"),
    ]:
        drafts = list(pathlib.Path("supabase/migrations").glob(pattern))
        assert drafts, f"No migration draft for {pattern}"
        content = drafts[0].read_text()
        fn_start = content.find(f"create or replace function {fn_name}")
        assert fn_start >= 0, f"Function {fn_name} not found in {drafts[0].name}"
        fn_body = content[fn_start:]
        # Find position of the clear step (set is_current = false) and the set step
        pos_clear = fn_body.find("set is_current = false")
        pos_set = fn_body.find("is_current    = true") if "is_current    = true" in fn_body \
            else fn_body.find("is_current    = (v_collect_scope is null)")
        assert pos_clear >= 0, f"Expected 'set is_current = false' in {fn_name} body"
        assert pos_set >= 0, f"Expected is_current set step in {fn_name} body"
        assert pos_clear < pos_set, (
            f"{fn_name}: is_current=false must appear BEFORE is_current=true/scope-set "
            f"(clear={pos_clear}, set={pos_set})"
        )


def test_g12_content_hash_includes_raw_content():
    """PATCH-002-07: same ID, different raw content → different hash (hash covers raw, not just ID)."""
    from services.ext132_hazardous_material.parse import Ext132Item
    from services.ext132_hazardous_material.store import compute_content_hash

    item_v1 = Ext132Item("A001", raw={"quantity": 100, "location": "warehouse-A"})
    item_v2 = Ext132Item("A001", raw={"quantity": 200, "location": "warehouse-B"})

    hash_v1 = compute_content_hash([item_v1])
    hash_v2 = compute_content_hash([item_v2])

    assert hash_v1 != hash_v2, "Same ID, different raw content must produce different hashes"


def test_g13_ext165_sql_collect_scope_and_scoped_promotion():
    """PATCH-002-06: ext165 migration draft has collect_scope column + scoped promotion logic."""
    import pathlib

    drafts = list(pathlib.Path("supabase/migrations").glob("*ext165*"))
    assert drafts, "No EXT-165 migration draft found"
    content = drafts[0].read_text()

    # collect_scope column must exist in table DDL
    assert "collect_scope" in content, "Expected 'collect_scope' column in ext165 migration draft"

    # fn_ext165_complete_snapshot must declare and use v_collect_scope
    fn_start = content.find("create or replace function fn_ext165_complete_snapshot")
    assert fn_start >= 0
    fn_body = content[fn_start:]
    assert "v_collect_scope" in fn_body, "Expected 'v_collect_scope' variable in fn_ext165_complete_snapshot"

    # Scoped promotion logic: is_current = (v_collect_scope is null)
    assert "v_collect_scope is null" in fn_body, (
        "Expected 'v_collect_scope is null' logic so year-scoped snapshots "
        "are not promoted as global is_current"
    )


# ─────────────────────────────────────────────────────────────────────────────
# H01-H15 — PATCH-003 P0 blockers
# ─────────────────────────────────────────────────────────────────────────────

def test_h01_sql_ext132_save_page_checkpoint_has_staging_guard():
    """PATCH-003-04: fn_ext132_save_page_checkpoint must raise SNAPSHOT_NOT_STAGING when snapshot not STAGING."""
    import pathlib
    drafts = list(pathlib.Path("supabase/migrations").glob("*ext132*"))
    assert drafts, "No ext132 migration draft found"
    content = drafts[0].read_text()
    fn_start = content.find("create or replace function fn_ext132_save_page_checkpoint")
    assert fn_start >= 0, "fn_ext132_save_page_checkpoint not found"
    fn_body = content[fn_start:]
    assert "SNAPSHOT_NOT_STAGING" in fn_body, "Expected SNAPSHOT_NOT_STAGING raise in fn_ext132_save_page_checkpoint"
    assert "for update" in fn_body.lower(), "Expected snapshot FOR UPDATE lock in fn_ext132_save_page_checkpoint"


def test_h02_sql_complete_snapshot_has_promote_failed_raise():
    """PATCH-003: fn_*_complete_snapshot must RAISE EXCEPTION 'PROMOTE_FAILED' to rollback on promotion failure."""
    import pathlib
    for pattern, fn_name in [
        ("*ext132*", "fn_ext132_complete_snapshot"),
        ("*ext165*", "fn_ext165_complete_snapshot"),
    ]:
        drafts = list(pathlib.Path("supabase/migrations").glob(pattern))
        assert drafts, f"No migration draft for {pattern}"
        content = drafts[0].read_text()
        fn_start = content.find(f"create or replace function {fn_name}")
        assert fn_start >= 0, f"{fn_name} not found in migration draft"
        fn_body = content[fn_start:]
        assert "PROMOTE_FAILED" in fn_body, f"Expected PROMOTE_FAILED raise exception in {fn_name}"
        assert "raise exception" in fn_body.lower(), f"Expected 'raise exception' in {fn_name}"


def test_h03_ext132_sync_premature_empty_page():
    """PATCH-003-02: ext132 empty page when total_count not yet reached → PARTIAL(PREMATURE_EMPTY_PAGE)."""
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all

    page1 = _xml_page([{"chemicalno": f"A{i}"} for i in range(3)], total_count=10)
    page2 = _xml_page([], total_count=10, page_no=2)
    pages = [page1, page2]
    idx = {"n": 0}

    def _fetch(page_no, **kw):
        val = pages[min(idx["n"], len(pages) - 1)]
        idx["n"] += 1
        return val

    with patch("services.ext132_hazardous_material.client.fetch_page", side_effect=_fetch):
        result = collect_all(page_delay_seconds=0)

    assert result.status == SyncStatus.PARTIAL
    assert result.error_code == "PREMATURE_EMPTY_PAGE"
    assert result.fetched == 3


def test_h04_ext165_sync_premature_empty_page():
    """PATCH-003-02: ext165 empty page when total_count not yet reached → PARTIAL(PREMATURE_EMPTY_PAGE)."""
    from services.ext165_chemical_accident.sync import SyncStatus, collect_all

    page1 = _xml_page([{"dataNo": f"D{i}"} for i in range(3)], total_count=10)
    page2 = _xml_page([], total_count=10, page_no=2)
    pages = [page1, page2]
    idx = {"n": 0}

    def _fetch(page_no, **kw):
        val = pages[min(idx["n"], len(pages) - 1)]
        idx["n"] += 1
        return val

    with patch("services.ext165_chemical_accident.client.fetch_page", side_effect=_fetch):
        result = collect_all(page_delay_seconds=0)

    assert result.status == SyncStatus.PARTIAL
    assert result.error_code == "PREMATURE_EMPTY_PAGE"
    assert result.fetched == 3


def test_h05_ext132_initial_items_count_prevents_premature_empty_page():
    """PATCH-003-02: initial_items_count=100 meets total=100 even on empty page → COMPLETED, not PREMATURE_EMPTY_PAGE."""
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all

    # Empty first page, but initial_items_count already meets total_count
    page1 = _xml_page([], total_count=100, page_no=1)

    with patch("services.ext132_hazardous_material.client.fetch_page", return_value=page1):
        result = collect_all(page_delay_seconds=0, initial_items_count=100)

    assert result.status == SyncStatus.COMPLETED
    assert result.error_code is None


def test_h06_ext132_adapter_budget_exhausted_preserves_snapshot():
    """PATCH-003: ext132 adapter BUDGET_EXHAUSTED → FAILED, fail_snapshot NOT called, snapshot_preserved=True."""
    from services.ext132_hazardous_material.sync import SyncResult, SyncStatus
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter

    fake_sync = SyncResult(
        status=SyncStatus.PARTIAL,
        fetched=10,
        items=[],
        error_code="BUDGET_EXHAUSTED",
    )

    fail_mock = MagicMock()
    with (
        patch("services.ext132_hazardous_material.store.create_staging_snapshot", return_value="snap-h06"),
        patch("services.ext132_hazardous_material.sync.collect_all", return_value=fake_sync),
        patch("services.ext132_hazardous_material.store.fail_snapshot", fail_mock),
    ):
        result = Ext132HazardousMaterialAdapter().run(_ctx("EXT132_HAZARDOUS_MATERIAL"))

    assert result.status == RunStatus.FAILED
    assert result.error_code == "BUDGET_EXHAUSTED"
    assert (result.details or {}).get("snapshot_preserved") is True
    fail_mock.assert_not_called()


def test_h07_ext165_adapter_budget_exhausted_preserves_snapshot():
    """PATCH-003: ext165 adapter BUDGET_EXHAUSTED → FAILED, fail_snapshot NOT called, snapshot_preserved=True."""
    from services.ext165_chemical_accident.sync import SyncResult, SyncStatus
    from services.public_data_sync.adapters.ext165_chemical_accident import Ext165ChemicalAccidentAdapter

    fake_sync = SyncResult(
        status=SyncStatus.PARTIAL,
        fetched=10,
        items=[],
        error_code="BUDGET_EXHAUSTED",
    )

    fail_mock = MagicMock()
    with (
        patch("services.ext165_chemical_accident.store.create_staging_snapshot", return_value="snap-h07"),
        patch("services.ext165_chemical_accident.sync.collect_all", return_value=fake_sync),
        patch("services.ext165_chemical_accident.store.fail_snapshot", fail_mock),
    ):
        result = Ext165ChemicalAccidentAdapter().run(_ctx("EXT165_CHEMICAL_ACCIDENT"))

    assert result.status == RunStatus.FAILED
    assert result.error_code == "BUDGET_EXHAUSTED"
    assert (result.details or {}).get("snapshot_preserved") is True
    fail_mock.assert_not_called()


def test_h08_fail_snapshot_calls_rpc_with_run_id():
    """REPAIR-A: fail_snapshot must call fn_ext132_fail_snapshot RPC with p_run_id for ownership fencing."""
    from services.ext132_hazardous_material.store import fail_snapshot

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value = MagicMock()

    fail_snapshot("snap-id", run_id="run-abc", error_message="test error", sb=mock_sb)

    mock_sb.rpc.assert_called_once_with("fn_ext132_fail_snapshot", {
        "p_snapshot_id": "snap-id",
        "p_run_id": "run-abc",
        "p_error_message": "test error",
    })


def test_h09_ext165_fail_snapshot_calls_rpc_with_run_id():
    """REPAIR-A: ext165 fail_snapshot must call fn_ext165_fail_snapshot RPC with p_run_id."""
    from services.ext165_chemical_accident.store import fail_snapshot

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value = MagicMock()

    fail_snapshot("snap-165", run_id="run-xyz", error_message="oops", sb=mock_sb)

    mock_sb.rpc.assert_called_once_with("fn_ext165_fail_snapshot", {
        "p_snapshot_id": "snap-165",
        "p_run_id": "run-xyz",
        "p_error_message": "oops",
    })


def test_h10_ext132_adapter_incomplete_collection_fails_snapshot():
    """PATCH-003: total_in_db < api_total → INCOMPLETE_COLLECTION + fail_snapshot."""
    from services.ext132_hazardous_material.sync import SyncResult, SyncStatus
    from services.ext132_hazardous_material.parse import Ext132Item
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter

    fake_items = [Ext132Item("A001"), Ext132Item("A002")]
    fake_sync = SyncResult(
        status=SyncStatus.COMPLETED,
        fetched=2,
        items=fake_items,
        pages_fetched=1,
        budget_used=1,
    )

    def fake_collect(**kw):
        on_page_complete = kw.get("on_page_complete")
        if on_page_complete:
            on_page_complete(1, fake_items, 2, 100)  # api_total=100, but only 2 saved
        return fake_sync

    fail_mock = MagicMock()
    with (
        patch("services.ext132_hazardous_material.store.create_staging_snapshot", return_value="snap-h10"),
        patch("services.ext132_hazardous_material.store.save_page_checkpoint", return_value=2),
        patch("services.ext132_hazardous_material.sync.collect_all", side_effect=fake_collect),
        patch("services.ext132_hazardous_material.store.fail_snapshot", fail_mock),
        patch("services.ext132_hazardous_material.store.atomic_complete_snapshot"),
    ):
        result = Ext132HazardousMaterialAdapter().run(_ctx("EXT132_HAZARDOUS_MATERIAL"))

    assert result.status == RunStatus.FAILED
    assert result.error_code == "INCOMPLETE_COLLECTION"
    fail_mock.assert_called_once_with("snap-h10", run_id=ANY, error_message="INCOMPLETE_COLLECTION")


def test_h11_ext132_save_page_checkpoint_snapshot_not_staging_raises_fenced():
    """PATCH-003: save_page_checkpoint receiving SNAPSHOT_NOT_STAGING → PageFencedError."""
    from services.ext132_hazardous_material.store import save_page_checkpoint
    from services.public_data_sync.errors import PageFencedError

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.side_effect = Exception(
        "SNAPSHOT_NOT_STAGING: snapshot abc has status=COMPLETED, expected STAGING"
    )

    with pytest.raises(PageFencedError):
        save_page_checkpoint("snap-id", [], 1, None, run_id="run-id", sb=mock_sb)


def test_h12_sql_ext132_checkpoint_api_total_validation():
    """REPAIR-B: fn_ext132_complete_snapshot blocks promotion when checkpoint_api_total IS NULL (fail-closed)."""
    import pathlib
    drafts = list(pathlib.Path("supabase/migrations").glob("*ext132*"))
    assert drafts
    content = drafts[0].read_text()
    fn_start = content.find("create or replace function fn_ext132_complete_snapshot")
    assert fn_start >= 0
    fn_body = content[fn_start:]
    assert "v_checkpoint_api" in fn_body, "Expected v_checkpoint_api variable in fn_ext132_complete_snapshot"
    # REPAIR-B: NULL → block (fail-closed); previously only non-null was checked
    assert "v_checkpoint_api is null" in fn_body.lower(), \
        "Expected fail-closed NULL guard: if v_checkpoint_api is null then return false"


def test_h13_sql_ext165_checkpoint_api_total_validation():
    """REPAIR-B: fn_ext165_complete_snapshot blocks promotion when checkpoint_api_total IS NULL (fail-closed)."""
    import pathlib
    drafts = list(pathlib.Path("supabase/migrations").glob("*ext165*"))
    assert drafts
    content = drafts[0].read_text()
    fn_start = content.find("create or replace function fn_ext165_complete_snapshot")
    assert fn_start >= 0
    fn_body = content[fn_start:]
    assert "v_checkpoint_api" in fn_body, "Expected v_checkpoint_api variable in fn_ext165_complete_snapshot"
    assert "v_checkpoint_api is null" in fn_body.lower(), \
        "Expected fail-closed NULL guard: if v_checkpoint_api is null then return false"


def test_h14_ext132_adapter_fenced_preserves_snapshot():
    """PATCH-003: FENCED result → RunStatus.FAILED, fail_snapshot NOT called (snapshot preserved)."""
    from services.ext132_hazardous_material.sync import SyncResult, SyncStatus
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter

    fake_sync = SyncResult(
        status=SyncStatus.FAILED,
        fetched=5,
        items=[],
        error_code="FENCED",
        error_message="run_id not current owner",
    )

    fail_mock = MagicMock()
    with (
        patch("services.ext132_hazardous_material.store.create_staging_snapshot", return_value="snap-h14"),
        patch("services.ext132_hazardous_material.sync.collect_all", return_value=fake_sync),
        patch("services.ext132_hazardous_material.store.fail_snapshot", fail_mock),
    ):
        result = Ext132HazardousMaterialAdapter().run(_ctx("EXT132_HAZARDOUS_MATERIAL"))

    assert result.status == RunStatus.FAILED
    assert result.error_code == "FENCED"
    assert (result.details or {}).get("snapshot_preserved") is True
    fail_mock.assert_not_called()


def test_h15_ext132_content_hash_consistent_memory_vs_db():
    """PATCH-003: compute_content_hash and compute_content_hash_from_db produce identical results for same data."""
    from services.ext132_hazardous_material.parse import Ext132Item
    from services.ext132_hazardous_material.store import compute_content_hash, compute_content_hash_from_db

    items = [
        Ext132Item("A001", raw={"qty": 10, "loc": "WH-A"}),
        Ext132Item("A002", raw={"qty": 20, "loc": "WH-B"}),
    ]

    hash_memory = compute_content_hash(items)

    db_rows = [{"chemicalno": item.chemicalno, "raw": item.raw} for item in items]
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.range.return_value.execute.return_value.data = db_rows

    hash_db = compute_content_hash_from_db("snap-id", sb=mock_sb)

    assert hash_memory == hash_db, "In-memory and DB-derived content hashes must match for identical data"


# ─────────────────────────────────────────────────────────────────────────────
# I-group: REVIEW-REPAIR-001 REPAIR-A/B/D tests
# SQL_INTEGRATION=UNVERIFIED (no test DB available; REPAIR-D acknowledged)
# ─────────────────────────────────────────────────────────────────────────────

def test_i01_ext132_safe_fail_snapshot_passes_run_id():
    """REPAIR-A: _safe_fail_snapshot must forward run_id to fail_snapshot RPC."""
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter
    from services.ext132_hazardous_material.sync import SyncResult, SyncStatus

    fake_sync = SyncResult(
        status=SyncStatus.FAILED,
        fetched=0,
        items=[],
        error_code="HTTP_ERROR",
        error_message="timeout",
    )

    ctx = _ctx("EXT132_HAZARDOUS_MATERIAL")
    fail_mock = MagicMock()
    with (
        patch("services.ext132_hazardous_material.store.create_staging_snapshot", return_value="snap-i01"),
        patch("services.ext132_hazardous_material.sync.collect_all", return_value=fake_sync),
        patch("services.ext132_hazardous_material.store.fail_snapshot", fail_mock),
    ):
        Ext132HazardousMaterialAdapter().run(ctx)

    fail_mock.assert_called_once_with("snap-i01", run_id=ctx.run_id, error_message="HTTP_ERROR")


def test_i02_ext165_safe_fail_snapshot_passes_run_id():
    """REPAIR-A: ext165 _safe_fail_snapshot must forward run_id to fail_snapshot RPC."""
    from services.public_data_sync.adapters.ext165_chemical_accident import Ext165ChemicalAccidentAdapter
    from services.ext165_chemical_accident.sync import SyncResult, SyncStatus

    fake_sync = SyncResult(
        status=SyncStatus.FAILED,
        fetched=0,
        items=[],
        error_code="HTTP_ERROR",
        error_message="timeout",
    )

    ctx = _ctx("EXT165_CHEMICAL_ACCIDENT")
    fail_mock = MagicMock()
    with (
        patch("services.ext165_chemical_accident.store.create_staging_snapshot", return_value="snap-i02"),
        patch("services.ext165_chemical_accident.sync.collect_all", return_value=fake_sync),
        patch("services.ext165_chemical_accident.store.fail_snapshot", fail_mock),
    ):
        Ext165ChemicalAccidentAdapter().run(ctx)

    fail_mock.assert_called_once_with("snap-i02", run_id=ctx.run_id, error_message="HTTP_ERROR")


def test_i03_safe_fail_snapshot_skips_when_run_id_none():
    """REPAIR-A: _safe_fail_snapshot(run_id=None) must not call fail_snapshot — prevents orphan REST write."""
    from services.public_data_sync.adapters.ext132_hazardous_material import Ext132HazardousMaterialAdapter

    fail_mock = MagicMock()
    with patch("services.ext132_hazardous_material.store.fail_snapshot", fail_mock):
        Ext132HazardousMaterialAdapter._safe_fail_snapshot("snap-id", "reason", run_id=None)

    fail_mock.assert_not_called()


def test_i04_ext132_sync_callback_error_is_fatal():
    """REPAIR-B: unknown callback exception → CALLBACK_ERROR (not silently swallowed)."""
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all
    from services.ext132_hazardous_material.parse import Ext132Item, PageResult

    def bad_callback(page_no, page_items, total_collected, total_count_from_api):
        raise RuntimeError("unexpected db failure")

    fake_page = PageResult(total_count=10, page_no=1, num_of_rows=10, items=[Ext132Item("A")])
    with patch("services.ext132_hazardous_material.client.fetch_page", return_value=b""):
        with patch("services.ext132_hazardous_material.sync.parse_page", return_value=fake_page):
            result = collect_all(request_budget=5, on_page_complete=bad_callback)

    assert result.status == SyncStatus.FAILED
    assert result.error_code == "CALLBACK_ERROR"


def test_i05_ext165_sync_callback_error_is_fatal():
    """REPAIR-B: ext165 unknown callback exception → CALLBACK_ERROR."""
    from services.ext165_chemical_accident.sync import SyncStatus, collect_all
    from services.ext165_chemical_accident.parse import Ext165Item, PageResult

    def bad_callback(page_no, page_items, total_collected, total_count_from_api):
        raise ValueError("bad value")

    fake_page = PageResult(total_count=10, page_no=1, num_of_rows=10, items=[Ext165Item("E1")])
    with patch("services.ext165_chemical_accident.client.fetch_page", return_value=b""):
        with patch("services.ext165_chemical_accident.sync.parse_page", return_value=fake_page):
            result = collect_all(request_budget=5, on_page_complete=bad_callback)

    assert result.status == SyncStatus.FAILED
    assert result.error_code == "CALLBACK_ERROR"


def test_i06_ext132_sync_mid_collection_total_count_change():
    """REPAIR-B: totalCount changing between pages mid-collection → ABORTED_TOTAL_CHANGED."""
    from services.ext132_hazardous_material.sync import SyncStatus, collect_all
    from services.ext132_hazardous_material.parse import Ext132Item, PageResult

    page1 = PageResult(total_count=100, page_no=1, num_of_rows=10, items=[Ext132Item("A")])
    page2 = PageResult(total_count=99, page_no=2, num_of_rows=10, items=[Ext132Item("B")])  # changed!
    pages = [page1, page2]
    parse_call = [0]

    def fake_parse(raw):
        idx = parse_call[0]
        parse_call[0] += 1
        return pages[idx] if idx < len(pages) else PageResult(total_count=99, page_no=3, num_of_rows=10, items=[])

    with patch("services.ext132_hazardous_material.client.fetch_page", return_value=b""):
        with patch("services.ext132_hazardous_material.sync.parse_page", side_effect=fake_parse):
            result = collect_all(request_budget=10)

    assert result.status == SyncStatus.ABORTED_TOTAL_CHANGED
    assert result.error_code == "TOTAL_COUNT_CHANGED"


def test_i07_ext165_sync_mid_collection_total_count_change():
    """REPAIR-B: ext165 totalCount changing mid-collection → ABORTED_TOTAL_CHANGED."""
    from services.ext165_chemical_accident.sync import SyncStatus, collect_all
    from services.ext165_chemical_accident.parse import Ext165Item, PageResult

    page1 = PageResult(total_count=50, page_no=1, num_of_rows=10, items=[Ext165Item("E1")])
    page2 = PageResult(total_count=51, page_no=2, num_of_rows=10, items=[Ext165Item("E2")])  # changed!
    pages = [page1, page2]
    parse_call = [0]

    def fake_parse(raw):
        idx = parse_call[0]
        parse_call[0] += 1
        return pages[idx] if idx < len(pages) else PageResult(total_count=51, page_no=3, num_of_rows=10, items=[])

    with patch("services.ext165_chemical_accident.client.fetch_page", return_value=b""):
        with patch("services.ext165_chemical_accident.sync.parse_page", side_effect=fake_parse):
            result = collect_all(request_budget=10)

    assert result.status == SyncStatus.ABORTED_TOTAL_CHANGED
    assert result.error_code == "TOTAL_COUNT_CHANGED"


def test_i08_sql_ext132_fail_snapshot_rpc_defined():
    """REPAIR-A: fn_ext132_fail_snapshot RPC must be defined in SQL draft with ownership fencing."""
    import pathlib
    drafts = list(pathlib.Path("supabase/migrations").glob("*ext132*"))
    assert drafts
    content = drafts[0].read_text()
    assert "fn_ext132_fail_snapshot" in content, "Expected fn_ext132_fail_snapshot RPC in migration draft"
    fn_start = content.find("create or replace function fn_ext132_fail_snapshot")
    assert fn_start >= 0
    fn_body = content[fn_start:fn_start + 2000]
    assert "for update" in fn_body.lower(), "Expected FOR UPDATE lock in fn_ext132_fail_snapshot"
    assert "p_run_id" in fn_body, "Expected p_run_id ownership parameter"
    assert "p_error_message" in fn_body, "Expected p_error_message parameter"
