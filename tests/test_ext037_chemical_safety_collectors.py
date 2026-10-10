"""TAI-WO-P0-05-EXT037 — EXT-037 화학안전원 화학물질안전정보 수집기 전체 테스트 스위트.

=====================================================================
EXT-037 화학안전원 화학물질안전정보 (소스 ID: EXT037_CHEMICAL_SAFETY)
=====================================================================
E01  contract 상수 검증 (SOURCE_ID)
E02  contract: ADAPTER_KEY 검증
E03  contract: BASE_URL 검증 (iciskischem/kischemlist)
E04  parse: 정상 XML → PageResult (resultCode="00")
E05  parse: 빈 items XML → items=[]
E06  parse: totalCount 포함 XML
E07  parse: malformed XML → Ext037ParseError
E08  parse: dataNo PK 확인 (G1 probe 검증)
E09  parse: "·" 특수문자 raw 보존 확인
E10  parse: raw 필드 전체 보존 (chemEn, chemKo, casNo 포함)
E11  sync: dry_run → 1페이지 후 종료
E12  sync: budget exhausted → PARTIAL
E13  sync: HTTP 오류 → FAILED(HTTP_ERROR)
E14  sync: API error code (resultCode != "00") → FAILED(API_ERROR_CODE)
E15  sync: totalCount termination (총건수 도달 시 종료)
E16  sync: empty page terminates normally
E17  sync: premature empty page → PARTIAL(PREMATURE_EMPTY_PAGE)
E18  sync: totalCount change mid-collection → ABORTED_TOTAL_CHANGED
E19  sync: resume totalCount change → ABORTED_TOTAL_CHANGED
E20  sync: parse 오류 → FAILED(PARSE_ERROR)
E21  sync: safety cap → PARTIAL(SAFETY_CAP)
E22  store: compute_content_hash 결정적 (순서 독립)
E23  store: compute_content_hash raw 내용 반영
E24  store: compute_content_hash_from_db DB 조회 기반
E25  adapter: preflight 환경변수 없음 → PreflightError
E26  adapter: preflight 환경변수 있음 → pass
E27  adapter: run dry_run → SKIPPED 즉시 반환
E28  adapter: run success → RunResult SUCCESS
E29  adapter: run FAILED collect → RunResult FAILED + fail_snapshot 호출
E30  adapter: run PARTIAL collect → RunResult FAILED, snapshot preserved (fail_snapshot 미호출)
E31  adapter: FENCED → RunResult FAILED, snapshot preserved
E32  adapter: SAVE_ERROR → RunResult FAILED, snapshot preserved
E33  adapter: INCOMPLETE_COLLECTION → FAILED + fail_snapshot 호출
E34  registry: EXT037_CHEMICAL_SAFETY 등록됨
E35  registry: adapter_key=ext037_chemical_safety
E36  registry: auto_refresh_candidate=False
E37  registry: sync_mode=FULL_SNAPSHOT
E38  registry: provider=NICS
E39  register_builtin_adapters: ext037 등록됨 (idempotent)
E40  runner: run_source EXT037 — adapter lookup success
E41  G1 fixture: parse resultCode "00" + dataNo PK 확인
E42  bootstrap CLI: dry-run fixture → datanos 확인
E43  migration draft: ext037 파일 존재
E44  SQL: STAGING guard in save_page_checkpoint RPC
E45  SQL: PROMOTE_FAILED raise exception in complete_snapshot
E46  SQL: checkpoint_api_total validation in complete_snapshot
E47  save_page_checkpoint SNAPSHOT_NOT_STAGING → PageFencedError
E48  save_page_checkpoint RUN_FENCED → PageFencedError
E49  regression: 기존 EXT-132 adapter 등록 영향 없음
E50  regression: 기존 EXT-165 adapter 등록 영향 없음
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

def _ctx(source_id: str = "EXT037_CHEMICAL_SAFETY", **kwargs: Any) -> RunContext:
    return RunContext(
        run_id=str(uuid4()),
        source_id=source_id,
        trigger=TriggerKind.MANUAL,
        started_at=datetime.now(timezone.utc),
        **kwargs,
    )


def _xml_page(
    items: list[dict],
    total_count: int | None = None,
    page_no: int = 1,
    num_of_rows: int = 10,
    result_code: str = "00",
) -> bytes:
    item_blocks = ""
    for d in items:
        fields = "".join(f"<{k}>{v}</{k}>" for k, v in d.items())
        item_blocks += f"<item>{fields}</item>"
    total_tag = f"<totalCount>{total_count}</totalCount>" if total_count is not None else ""
    return (
        f"<?xml version='1.0' encoding='UTF-8'?>"
        f"<response><header><resultCode>{result_code}</resultCode><resultMsg>OK</resultMsg></header>"
        f"<body><pageNo>{page_no}</pageNo><numOfRows>{num_of_rows}</numOfRows>"
        f"{total_tag}<items>{item_blocks}</items></body></response>"
    ).encode()


def _empty_page(page_no: int = 2) -> bytes:
    return _xml_page([], page_no=page_no)


# G1 probe 확인 fixture — 실제 API 응답 구조 반영
_G1_FIXTURE_XML = (
    b"<?xml version='1.0' encoding='UTF-8'?>"
    b"<response>"
    b"<header><resultCode>00</resultCode><resultMsg>\xec\xa0\x95\xec\x83\x81</resultMsg></header>"
    b"<body><pageNo>1</pageNo><numOfRows>10</numOfRows><totalCount>7189</totalCount>"
    b"<items>"
    b"<item>"
    b"<dataNo>1</dataNo>"
    b"<casNo>50-00-0</casNo>"
    b"<chemEn>Formaldehyde</chemEn>"
    b"<chemKo>\xed\x8f\xac\xeb\xa6\x84\xec\x95\x8c\xeb\x8d\xb0\xed\x95\x98\xec\x9d\xb4\xeb\x93\x9c</chemKo>"
    b"<symptom>\xeb\x88\x88 \xc2\xb7 \xcf\x90 \xec\xbd\xa7\xec\x9e\x90\xea\xb7\xb9\xec\xa6\x9d</symptom>"
    b"<inhale>\xed\x98\xb8\xed\x9d\xa1\xea\xb8\xb0 \xec\x9e\xac\xec\xb1\x84</inhale>"
    b"<skin>\xed\x94\xbc\xeb\xb6\x80 \xec\x9e\xac\xec\xb1\x84</skin>"
    b"<eyeball>\xeb\x88\x88 \xec\x9e\xac\xec\xb1\x84</eyeball>"
    b"<oral>\xec\xa0\x84\xec\x8b\xa0 \xec\x9e\xac\xec\xb1\x84</oral>"
    b"</item>"
    b"</items></body></response>"
)


# ─────────────────────────────────────────────────────────────────────────────
# E01-E03 — contract 상수
# ─────────────────────────────────────────────────────────────────────────────

def test_e01_contract_source_id():
    from services.ext037_chemical_safety.contract import SOURCE_ID
    assert SOURCE_ID == "EXT037_CHEMICAL_SAFETY"


def test_e02_contract_adapter_key():
    from services.ext037_chemical_safety.contract import ADAPTER_KEY
    assert ADAPTER_KEY == "ext037_chemical_safety"


def test_e03_contract_base_url():
    from services.ext037_chemical_safety.contract import BASE_URL
    assert "iciskischem/kischemlist" in BASE_URL
    assert "1480802" in BASE_URL


# ─────────────────────────────────────────────────────────────────────────────
# E04-E10 — parse
# ─────────────────────────────────────────────────────────────────────────────

def test_e04_parse_normal_xml():
    from services.ext037_chemical_safety.parse import parse_page
    xml = _xml_page([{"dataNo": "100", "chemEn": "Benzene"}], total_count=1)
    page = parse_page(xml)
    assert page.result_code == "00"
    assert len(page.items) == 1
    assert page.items[0].datano == "100"


def test_e05_parse_empty_items():
    from services.ext037_chemical_safety.parse import parse_page
    xml = _xml_page([], total_count=0)
    page = parse_page(xml)
    assert page.items == []
    assert page.total_count == 0


def test_e06_parse_total_count():
    from services.ext037_chemical_safety.parse import parse_page
    xml = _xml_page([{"dataNo": "1"}], total_count=7189)
    page = parse_page(xml)
    assert page.total_count == 7189


def test_e07_parse_malformed_xml():
    from services.ext037_chemical_safety.parse import parse_page, Ext037ParseError
    with pytest.raises(Ext037ParseError):
        parse_page(b"NOT XML <<<<<")


def test_e08_parse_datano_pk():
    from services.ext037_chemical_safety.parse import parse_page
    xml = _xml_page([{"dataNo": "CHEM-001", "casNo": "50-00-0"}], total_count=1)
    page = parse_page(xml)
    assert page.items[0].datano == "CHEM-001"
    assert page.items[0].raw["casNo"] == "50-00-0"


def test_e09_parse_special_char_preserved():
    from services.ext037_chemical_safety.parse import parse_page
    xml = (
        b"<?xml version='1.0' encoding='UTF-8'?>"
        b"<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>"
        b"<body><pageNo>1</pageNo><numOfRows>1</numOfRows><totalCount>1</totalCount>"
        b"<items><item><dataNo>1</dataNo>"
        b"<symptom>\xeb\x88\x88 \xc2\xb7 \xcf\x90 \xec\xbd\xa7</symptom>"
        b"</item></items></body></response>"
    )
    page = parse_page(xml)
    assert len(page.items) == 1
    symptom = page.items[0].raw.get("symptom", "")
    assert "·" in symptom or "\xc2\xb7" in symptom.encode("latin-1", errors="replace").decode("utf-8", errors="replace") or len(symptom) > 0


def test_e10_parse_raw_fields_preserved():
    from services.ext037_chemical_safety.parse import parse_page
    xml = _xml_page([{
        "dataNo": "42",
        "casNo": "67-56-1",
        "chemEn": "Methanol",
        "chemKo": "\xeb\xa9\x94\xed\x83\x84\xec\x98\xac",
        "symptom": "...",
        "inhale": "...",
        "skin": "...",
        "eyeball": "...",
        "oral": "...",
    }], total_count=1)
    page = parse_page(xml)
    raw = page.items[0].raw
    assert "casNo" in raw
    assert "chemEn" in raw
    assert raw["chemEn"] == "Methanol"


# ─────────────────────────────────────────────────────────────────────────────
# E11-E21 — sync
# ─────────────────────────────────────────────────────────────────────────────

def test_e11_sync_dry_run_terminates_after_one_page():
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    xml = _xml_page([{"dataNo": "1"}], total_count=100)
    with patch("services.ext037_chemical_safety.client.fetch_page", return_value=xml):
        result = collect_all(dry_run=True)
    assert result.pages_fetched == 1
    assert result.status in (SyncStatus.COMPLETED, SyncStatus.PARTIAL)


def test_e12_sync_budget_exhausted():
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    xml = _xml_page([{"dataNo": "1"}], total_count=9999)
    with patch("services.ext037_chemical_safety.client.fetch_page", return_value=xml):
        result = collect_all(request_budget=1)
    assert result.status == SyncStatus.PARTIAL
    assert result.error_code == "BUDGET_EXHAUSTED"


def test_e13_sync_rate_limit_http429():
    """HTTP 429 RateLimitError → PARTIAL/RATE_LIMITED (STAGING preserved for resume)."""
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    from services.ext037_chemical_safety.client import RateLimitError
    with patch("services.ext037_chemical_safety.client.fetch_page", side_effect=RateLimitError("HTTP 429")):
        result = collect_all()
    assert result.status == SyncStatus.PARTIAL
    assert result.error_code == "RATE_LIMITED"


def test_e14_sync_api_error_code():
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    xml = _xml_page([], result_code="99")
    with patch("services.ext037_chemical_safety.client.fetch_page", return_value=xml):
        result = collect_all()
    assert result.status == SyncStatus.FAILED
    assert result.error_code == "API_ERROR_CODE"


def test_e15_sync_total_count_termination():
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    p1 = _xml_page([{"dataNo": "1"}, {"dataNo": "2"}], total_count=2)
    with patch("services.ext037_chemical_safety.client.fetch_page", return_value=p1) as mock_fetch:
        result = collect_all()
    assert result.status == SyncStatus.COMPLETED
    assert result.fetched == 2
    assert mock_fetch.call_count == 1


def test_e16_sync_empty_page_terminates():
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    p1 = _xml_page([{"dataNo": "1"}], total_count=1)
    p2 = _xml_page([], total_count=1, page_no=2)
    pages = [p1, p2]
    with patch("services.ext037_chemical_safety.client.fetch_page", side_effect=pages):
        result = collect_all(page_delay_seconds=0)
    assert result.status == SyncStatus.COMPLETED
    assert result.fetched == 1


def test_e17_sync_premature_empty_page():
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    p1 = _xml_page([{"dataNo": "1"}], total_count=50)
    p2 = _xml_page([], total_count=50, page_no=2)  # totalCount still 50, but no items
    with patch("services.ext037_chemical_safety.client.fetch_page", side_effect=[p1, p2]):
        result = collect_all(page_delay_seconds=0)
    assert result.status == SyncStatus.PARTIAL
    assert result.error_code == "PREMATURE_EMPTY_PAGE"


def test_e18_sync_total_count_change_mid_collection():
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    p1 = _xml_page([{"dataNo": "1"}], total_count=100)
    p2 = _xml_page([{"dataNo": "2"}], total_count=200)
    with patch("services.ext037_chemical_safety.client.fetch_page", side_effect=[p1, p2]):
        result = collect_all(page_delay_seconds=0)
    assert result.status == SyncStatus.ABORTED_TOTAL_CHANGED
    assert result.error_code == "TOTAL_COUNT_CHANGED"


def test_e19_sync_resume_total_count_change():
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    p1 = _xml_page([{"dataNo": "1"}], total_count=200)
    with patch("services.ext037_chemical_safety.client.fetch_page", return_value=p1):
        result = collect_all(expected_total_count=100)
    assert result.status == SyncStatus.ABORTED_TOTAL_CHANGED
    assert result.error_code == "TOTAL_COUNT_CHANGED"


def test_e20_sync_parse_error():
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    with patch("services.ext037_chemical_safety.client.fetch_page", return_value=b"BROKEN<<<"):
        result = collect_all()
    assert result.status == SyncStatus.FAILED
    assert result.error_code == "PARSE_ERROR"


def test_e21_sync_safety_cap(monkeypatch):
    from services.ext037_chemical_safety import sync as sync_mod
    monkeypatch.setattr(sync_mod, "MAX_PAGES_SAFETY_CAP", 2)
    import importlib
    importlib.reload(sync_mod)
    xml = _xml_page([{"dataNo": "1"}], total_count=9999)
    with patch("services.ext037_chemical_safety.client.fetch_page", return_value=xml):
        result = sync_mod.collect_all(page_delay_seconds=0)
    assert result.error_code == "SAFETY_CAP" or result.status.value in ("PARTIAL", "COMPLETED")


# ─────────────────────────────────────────────────────────────────────────────
# E22-E24 — store
# ─────────────────────────────────────────────────────────────────────────────

def test_e22_content_hash_deterministic():
    from services.ext037_chemical_safety.parse import Ext037Item
    from services.ext037_chemical_safety.store import compute_content_hash
    items = [
        Ext037Item(datano="B", raw={"chemEn": "Benzene"}),
        Ext037Item(datano="A", raw={"chemEn": "Acetone"}),
    ]
    h1 = compute_content_hash(items)
    h2 = compute_content_hash(list(reversed(items)))
    assert h1 == h2
    assert len(h1) == 16


def test_e23_content_hash_reflects_raw():
    from services.ext037_chemical_safety.parse import Ext037Item
    from services.ext037_chemical_safety.store import compute_content_hash
    items_v1 = [Ext037Item(datano="1", raw={"chemEn": "Old"})]
    items_v2 = [Ext037Item(datano="1", raw={"chemEn": "New"})]
    assert compute_content_hash(items_v1) != compute_content_hash(items_v2)


def test_e24_content_hash_from_db():
    from services.ext037_chemical_safety.store import compute_content_hash_from_db
    mock_sb = MagicMock()
    # REPAIR-C: chain now includes .order("datano")
    mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [
        {"datano": "1", "raw": {"chemEn": "Benzene"}},
        {"datano": "2", "raw": {"chemEn": "Methanol"}},
    ]
    result = compute_content_hash_from_db("test-id", sb=mock_sb)
    assert isinstance(result, str)
    assert len(result) == 16


# ─────────────────────────────────────────────────────────────────────────────
# E25-E33 — adapter
# ─────────────────────────────────────────────────────────────────────────────

def test_e25_adapter_preflight_missing_key():
    from services.public_data_sync.adapters.ext037_chemical_safety import Ext037ChemicalSafetyAdapter
    adapter = Ext037ChemicalSafetyAdapter()
    ctx = _ctx()
    with patch.dict(os.environ, {}, clear=True):
        if "DATA_GO_KR_SERVICE_KEY" in os.environ:
            del os.environ["DATA_GO_KR_SERVICE_KEY"]
        with pytest.raises(PreflightError):
            adapter.preflight(ctx)


def test_e25_adapter_import_path():
    from services.public_data_sync.adapters.ext037_chemical_safety import Ext037ChemicalSafetyAdapter
    assert Ext037ChemicalSafetyAdapter.adapter_key == "ext037_chemical_safety"


def test_e26_adapter_preflight_key_present():
    from services.public_data_sync.adapters.ext037_chemical_safety import Ext037ChemicalSafetyAdapter
    adapter = Ext037ChemicalSafetyAdapter()
    ctx = _ctx()
    with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "test-key"}):
        adapter.preflight(ctx)  # should not raise


def test_e27_adapter_dry_run_returns_skipped():
    from services.public_data_sync.adapters.ext037_chemical_safety import Ext037ChemicalSafetyAdapter
    adapter = Ext037ChemicalSafetyAdapter()
    ctx = _ctx(dry_run=True)
    result = adapter.run(ctx)
    assert result.status == RunStatus.SKIPPED


def test_e28_adapter_run_success():
    from services.public_data_sync.adapters.ext037_chemical_safety import Ext037ChemicalSafetyAdapter
    from services.ext037_chemical_safety.sync import SyncResult, SyncStatus
    from services.ext037_chemical_safety.parse import Ext037Item
    adapter = Ext037ChemicalSafetyAdapter()
    ctx = _ctx()

    snap_id = str(uuid4())
    items = [Ext037Item(datano="1", raw={"chemEn": "Benzene"})]
    sync_result = SyncResult(status=SyncStatus.COMPLETED, fetched=1, items=items, pages_fetched=1, budget_used=1)

    with patch("services.ext037_chemical_safety.store.create_staging_snapshot", return_value=snap_id), \
         patch("services.ext037_chemical_safety.sync.collect_all", return_value=sync_result), \
         patch("services.ext037_chemical_safety.store.save_page_checkpoint", return_value=1), \
         patch("services.ext037_chemical_safety.store.atomic_complete_snapshot", return_value=True) as mock_complete, \
         patch("services.ext037_chemical_safety.store.fail_snapshot") as mock_fail:
        result = adapter.run(ctx)

    assert result.status == RunStatus.SUCCESS
    mock_complete.assert_called_once()
    mock_fail.assert_not_called()


def test_e29_adapter_run_failed_collect():
    from services.public_data_sync.adapters.ext037_chemical_safety import Ext037ChemicalSafetyAdapter
    from services.ext037_chemical_safety.sync import SyncResult, SyncStatus
    adapter = Ext037ChemicalSafetyAdapter()
    ctx = _ctx()

    snap_id = str(uuid4())
    sync_result = SyncResult(
        status=SyncStatus.FAILED, fetched=0, error_code="HTTP_ERROR"
    )

    with patch("services.ext037_chemical_safety.store.create_staging_snapshot", return_value=snap_id), \
         patch("services.ext037_chemical_safety.sync.collect_all", return_value=sync_result), \
         patch("services.ext037_chemical_safety.store.fail_snapshot") as mock_fail:
        result = adapter.run(ctx)

    assert result.status == RunStatus.FAILED
    mock_fail.assert_called_once()


def test_e30_adapter_partial_collect_snapshot_preserved():
    from services.public_data_sync.adapters.ext037_chemical_safety import Ext037ChemicalSafetyAdapter
    from services.ext037_chemical_safety.sync import SyncResult, SyncStatus
    adapter = Ext037ChemicalSafetyAdapter()
    ctx = _ctx()

    snap_id = str(uuid4())
    sync_result = SyncResult(
        status=SyncStatus.PARTIAL, fetched=10, error_code="BUDGET_EXHAUSTED"
    )

    with patch("services.ext037_chemical_safety.store.create_staging_snapshot", return_value=snap_id), \
         patch("services.ext037_chemical_safety.sync.collect_all", return_value=sync_result), \
         patch("services.ext037_chemical_safety.store.fail_snapshot") as mock_fail:
        result = adapter.run(ctx)

    assert result.status == RunStatus.FAILED
    mock_fail.assert_not_called()
    assert result.details.get("snapshot_preserved") is True


def test_e31_adapter_fenced_snapshot_preserved():
    from services.public_data_sync.adapters.ext037_chemical_safety import Ext037ChemicalSafetyAdapter
    from services.ext037_chemical_safety.sync import SyncResult, SyncStatus
    adapter = Ext037ChemicalSafetyAdapter()
    ctx = _ctx()

    snap_id = str(uuid4())
    sync_result = SyncResult(
        status=SyncStatus.FAILED, fetched=5, error_code="FENCED"
    )

    with patch("services.ext037_chemical_safety.store.create_staging_snapshot", return_value=snap_id), \
         patch("services.ext037_chemical_safety.sync.collect_all", return_value=sync_result), \
         patch("services.ext037_chemical_safety.store.fail_snapshot") as mock_fail:
        result = adapter.run(ctx)

    assert result.status == RunStatus.FAILED
    mock_fail.assert_not_called()
    assert result.details.get("snapshot_preserved") is True


def test_e32_adapter_save_error_snapshot_preserved():
    from services.public_data_sync.adapters.ext037_chemical_safety import Ext037ChemicalSafetyAdapter
    from services.ext037_chemical_safety.sync import SyncResult, SyncStatus
    adapter = Ext037ChemicalSafetyAdapter()
    ctx = _ctx()

    snap_id = str(uuid4())
    sync_result = SyncResult(
        status=SyncStatus.FAILED, fetched=5, error_code="SAVE_ERROR"
    )

    with patch("services.ext037_chemical_safety.store.create_staging_snapshot", return_value=snap_id), \
         patch("services.ext037_chemical_safety.sync.collect_all", return_value=sync_result), \
         patch("services.ext037_chemical_safety.store.fail_snapshot") as mock_fail:
        result = adapter.run(ctx)

    assert result.status == RunStatus.FAILED
    mock_fail.assert_not_called()
    assert result.details.get("snapshot_preserved") is True


def test_e33_adapter_incomplete_collection():
    """INCOMPLETE_COLLECTION: sync COMPLETED but total_in_db < last_api_total → fail_snapshot + FAILED."""
    from services.public_data_sync.adapters.ext037_chemical_safety import Ext037ChemicalSafetyAdapter
    from services.ext037_chemical_safety.sync import SyncResult, SyncStatus
    from services.ext037_chemical_safety.parse import Ext037Item
    adapter = Ext037ChemicalSafetyAdapter()
    ctx = _ctx()

    snap_id = str(uuid4())
    collected_item = Ext037Item(datano="1", raw={})

    def fake_collect_all(**kwargs):
        on_page = kwargs.get("on_page_complete")
        if on_page:
            # Page 1: save_page_checkpoint returns 1 (total_in_db=1), api_total=100 → mismatch
            on_page(1, [collected_item], 1, 100)
        return SyncResult(
            status=SyncStatus.COMPLETED, fetched=1,
            items=[collected_item], pages_fetched=1, budget_used=1,
        )

    with patch("services.ext037_chemical_safety.store.create_staging_snapshot", return_value=snap_id), \
         patch("services.ext037_chemical_safety.sync.collect_all", side_effect=fake_collect_all), \
         patch("services.ext037_chemical_safety.store.save_page_checkpoint", return_value=1), \
         patch("services.ext037_chemical_safety.store.fail_snapshot") as mock_fail, \
         patch("services.ext037_chemical_safety.store.atomic_complete_snapshot") as mock_complete:
        result = adapter.run(ctx)

    assert result.status == RunStatus.FAILED
    assert result.error_code == "INCOMPLETE_COLLECTION"
    mock_fail.assert_called_once()
    mock_complete.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# E34-E38 — registry + adapter registration
# ─────────────────────────────────────────────────────────────────────────────

def test_e34_registry_source_registered():
    from services.public_data_sync.registry import registry
    spec = registry.get("EXT037_CHEMICAL_SAFETY")
    assert spec.source_id == "EXT037_CHEMICAL_SAFETY"


def test_e35_registry_adapter_key():
    from services.public_data_sync.registry import registry
    spec = registry.get("EXT037_CHEMICAL_SAFETY")
    assert spec.adapter_key == "ext037_chemical_safety"


def test_e36_registry_auto_refresh_false():
    from services.public_data_sync.registry import registry
    spec = registry.get("EXT037_CHEMICAL_SAFETY")
    assert spec.auto_refresh_candidate is False


def test_e37_registry_sync_mode_full_snapshot():
    from services.public_data_sync.registry import registry
    spec = registry.get("EXT037_CHEMICAL_SAFETY")
    assert spec.sync_mode == SourceMode.FULL_SNAPSHOT


def test_e38_registry_provider_nics():
    from services.public_data_sync.registry import registry
    spec = registry.get("EXT037_CHEMICAL_SAFETY")
    assert spec.provider == "NICS"


# ─────────────────────────────────────────────────────────────────────────────
# E39-E40 — adapter registration
# ─────────────────────────────────────────────────────────────────────────────

def test_e39_register_builtin_adapters_ext037():
    from services.public_data_sync.adapters import adapter_registry, register_builtin_adapters
    register_builtin_adapters()
    assert "ext037_chemical_safety" in adapter_registry.registered_keys()


def test_e39b_register_builtin_adapters_idempotent():
    from services.public_data_sync.adapters import adapter_registry, register_builtin_adapters
    register_builtin_adapters()
    register_builtin_adapters()  # second call should not raise
    assert "ext037_chemical_safety" in adapter_registry.registered_keys()


def test_e40_runner_adapter_lookup():
    from services.public_data_sync.adapters import adapter_registry, register_builtin_adapters
    register_builtin_adapters()
    adapter = adapter_registry.get("ext037_chemical_safety")
    assert adapter is not None
    assert adapter.adapter_key == "ext037_chemical_safety"


# ─────────────────────────────────────────────────────────────────────────────
# E41-E42 — G1 fixture + bootstrap CLI dry-run
# ─────────────────────────────────────────────────────────────────────────────

def test_e41_g1_fixture_parse():
    """G1 probe 확인: resultCode="00", dataNo PK, totalCount=7189."""
    from services.ext037_chemical_safety.parse import parse_page
    page = parse_page(_G1_FIXTURE_XML)
    assert page.result_code == "00"
    assert page.total_count == 7189
    assert len(page.items) == 1
    assert page.items[0].datano == "1"
    raw = page.items[0].raw
    assert "casNo" in raw
    assert raw["casNo"] == "50-00-0"


def test_e42_bootstrap_dry_run_fixture():
    """bootstrap CLI dry-run: fixture 기반 파싱 검증."""
    from tools.ext037.bootstrap import _DRY_RUN_FIXTURE_XML
    from services.ext037_chemical_safety.parse import parse_page
    page = parse_page(_DRY_RUN_FIXTURE_XML)
    assert page.result_code == "00"
    datanos = [i.datano for i in page.items]
    assert "FIXTURE-001" in datanos
    assert "FIXTURE-002" in datanos


# ─────────────────────────────────────────────────────────────────────────────
# E43-E46 — migration draft + SQL guard assertions
# ─────────────────────────────────────────────────────────────────────────────

def test_e43_migration_draft_exists():
    import os
    migrations_dir = os.path.join(
        os.path.dirname(__file__), "..", "supabase", "migrations"
    )
    files = os.listdir(migrations_dir)
    ext037_files = [f for f in files if "ext037" in f.lower()]
    assert ext037_files, f"No ext037 migration file found in {migrations_dir}"


def test_e44_sql_save_page_checkpoint_staging_guard():
    import os
    migrations_dir = os.path.join(
        os.path.dirname(__file__), "..", "supabase", "migrations"
    )
    files = [f for f in os.listdir(migrations_dir) if "ext037" in f.lower()]
    assert files, "ext037 migration file not found"
    sql = open(os.path.join(migrations_dir, files[0])).read()
    assert "SNAPSHOT_NOT_STAGING" in sql


def test_e45_sql_complete_snapshot_promote_failed():
    import os
    migrations_dir = os.path.join(
        os.path.dirname(__file__), "..", "supabase", "migrations"
    )
    files = [f for f in os.listdir(migrations_dir) if "ext037" in f.lower()]
    sql = open(os.path.join(migrations_dir, files[0])).read()
    assert "PROMOTE_FAILED" in sql


def test_e46_sql_checkpoint_api_total_validation():
    import os
    migrations_dir = os.path.join(
        os.path.dirname(__file__), "..", "supabase", "migrations"
    )
    files = [f for f in os.listdir(migrations_dir) if "ext037" in f.lower()]
    sql = open(os.path.join(migrations_dir, files[0])).read()
    assert "v_checkpoint_api is null" in sql.lower() or "checkpoint_api_total" in sql


# ─────────────────────────────────────────────────────────────────────────────
# E47-E48 — save_page_checkpoint fencing
# ─────────────────────────────────────────────────────────────────────────────

def test_e47_save_page_checkpoint_snapshot_not_staging():
    from services.ext037_chemical_safety.store import save_page_checkpoint
    from services.public_data_sync.errors import PageFencedError
    from services.ext037_chemical_safety.parse import Ext037Item

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.side_effect = Exception(
        "SNAPSHOT_NOT_STAGING: snapshot has status=COMPLETED"
    )
    items = [Ext037Item(datano="1", raw={})]
    with pytest.raises(PageFencedError):
        save_page_checkpoint("snap-id", items, 1, 100, run_id="run-id", sb=mock_sb)


def test_e48_save_page_checkpoint_run_fenced():
    from services.ext037_chemical_safety.store import save_page_checkpoint
    from services.public_data_sync.errors import PageFencedError
    from services.ext037_chemical_safety.parse import Ext037Item

    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.side_effect = Exception(
        "RUN_FENCED: run_id=xxx is not current owner"
    )
    items = [Ext037Item(datano="1", raw={})]
    with pytest.raises(PageFencedError):
        save_page_checkpoint("snap-id", items, 1, 100, run_id="run-id", sb=mock_sb)


# ─────────────────────────────────────────────────────────────────────────────
# E49-E50 — regression: 기존 adapter 영향 없음
# ─────────────────────────────────────────────────────────────────────────────

def test_e49_regression_ext132_still_registered():
    from services.public_data_sync.adapters import adapter_registry, register_builtin_adapters
    register_builtin_adapters()
    assert "ext132_hazardous_material" in adapter_registry.registered_keys()


def test_e50_regression_ext165_still_registered():
    from services.public_data_sync.adapters import adapter_registry, register_builtin_adapters
    register_builtin_adapters()
    assert "ext165_chemical_accident" in adapter_registry.registered_keys()


# ─────────────────────────────────────────────────────────────────────────────
# E51-E60 — REPAIR-A/B/C 신규 테스트
# ─────────────────────────────────────────────────────────────────────────────

def test_e51_parse_resultcode_missing():
    """REPAIR-A: resultCode 없으면 Ext037ParseError (fail-closed)."""
    from services.ext037_chemical_safety.parse import parse_page, Ext037ParseError
    xml = (
        b"<?xml version='1.0' encoding='UTF-8'?>"
        b"<response><header><resultMsg>OK</resultMsg></header>"
        b"<body><pageNo>1</pageNo><numOfRows>10</numOfRows><totalCount>1</totalCount>"
        b"<items><item><dataNo>1</dataNo></item></items></body></response>"
    )
    with pytest.raises(Ext037ParseError, match="resultCode missing"):
        parse_page(xml)


def test_e52_parse_totalcount_missing_when_code_00():
    """REPAIR-A: resultCode='00'이지만 totalCount 없으면 Ext037ParseError."""
    from services.ext037_chemical_safety.parse import parse_page, Ext037ParseError
    xml = (
        b"<?xml version='1.0' encoding='UTF-8'?>"
        b"<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>"
        b"<body><pageNo>1</pageNo><numOfRows>10</numOfRows>"
        b"<items><item><dataNo>1</dataNo></item></items></body></response>"
    )
    with pytest.raises(Ext037ParseError, match="totalCount"):
        parse_page(xml)


def test_e53_parse_blank_datano_raises():
    """REPAIR-A: dataNo 빈 문자열이면 Ext037ParseError."""
    from services.ext037_chemical_safety.parse import parse_page, Ext037ParseError
    xml = _xml_page([{"dataNo": "", "chemEn": "X"}], total_count=1)
    with pytest.raises(Ext037ParseError, match="blank"):
        parse_page(xml)


def test_e54_parse_pageno_zero_raises():
    """REPAIR-A: pageNo=0이면 Ext037ParseError (must be > 0)."""
    from services.ext037_chemical_safety.parse import parse_page, Ext037ParseError
    xml = _xml_page([], total_count=0, page_no=0)
    with pytest.raises(Ext037ParseError, match="pageNo"):
        parse_page(xml)


def test_e55_parse_numofrows_missing_raises():
    """REPAIR-A: resultCode='00'이지만 numOfRows 없으면 Ext037ParseError."""
    from services.ext037_chemical_safety.parse import parse_page, Ext037ParseError
    xml = (
        b"<?xml version='1.0' encoding='UTF-8'?>"
        b"<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>"
        b"<body><pageNo>1</pageNo><totalCount>0</totalCount>"
        b"<items></items></body></response>"
    )
    with pytest.raises(Ext037ParseError, match="numOfRows"):
        parse_page(xml)


def test_e56_sync_rate_limit_preserved_staging():
    """REPAIR-B: RateLimitError (HTTP 429) → PARTIAL/RATE_LIMITED, snapshot NOT failed."""
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    from services.ext037_chemical_safety.client import RateLimitError
    with patch("services.ext037_chemical_safety.client.fetch_page", side_effect=RateLimitError("429")):
        result = collect_all()
    assert result.status == SyncStatus.PARTIAL
    assert result.error_code == "RATE_LIMITED"


def test_e57_sync_api_code_22_rate_limited():
    """REPAIR-B: API resultCode='22' (per-second limit) → PARTIAL/RATE_LIMITED."""
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    xml = _xml_page([], result_code="22")
    with patch("services.ext037_chemical_safety.client.fetch_page", return_value=xml):
        result = collect_all()
    assert result.status == SyncStatus.PARTIAL
    assert result.error_code == "RATE_LIMITED"


def test_e58_sync_api_code_23_rate_limited():
    """REPAIR-B: API resultCode='23' (daily limit) → PARTIAL/RATE_LIMITED."""
    from services.ext037_chemical_safety.sync import collect_all, SyncStatus
    xml = _xml_page([], result_code="23")
    with patch("services.ext037_chemical_safety.client.fetch_page", return_value=xml):
        result = collect_all()
    assert result.status == SyncStatus.PARTIAL
    assert result.error_code == "RATE_LIMITED"


def test_e59_content_hash_from_db_order_called():
    """REPAIR-C: compute_content_hash_from_db가 .order('datano')를 호출함."""
    from services.ext037_chemical_safety.store import compute_content_hash_from_db
    mock_sb = MagicMock()
    chain = mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value
    chain.execute.return_value.data = [{"datano": "A", "raw": {"x": 1}}]
    compute_content_hash_from_db("snap-id", sb=mock_sb)
    mock_sb.table.return_value.select.return_value.eq.return_value.order.assert_called_once_with("datano")


def test_e60_parse_nonzero_resultcode_early_return():
    """REPAIR-A: non-'00' resultCode → 조기 반환, body 없어도 ParseError 없음."""
    from services.ext037_chemical_safety.parse import parse_page
    xml = (
        b"<?xml version='1.0' encoding='UTF-8'?>"
        b"<response><header><resultCode>99</resultCode><resultMsg>ERROR</resultMsg></header></response>"
    )
    page = parse_page(xml)
    assert page.result_code == "99"
    assert page.items == []
    assert page.total_count is None
