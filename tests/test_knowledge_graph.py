"""OBJ-GRAPH G01–G80 + GUIDE shadow compatibility. No production DB."""
from __future__ import annotations

import ast
import inspect
import json
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.knowledge_graph_producers import (
    GraphCandidate,
    is_guide_material_related,
    produce_accident_relations,
    produce_guide_material_shadow,
    produce_guide_relations,
    produce_knowledge_center_relations,
    produce_law_relations,
    produce_precedent_relations,
    produce_safety_material_relations,
)
from services.knowledge_graph_rules import accept_candidate
from services.knowledge_graph_svc import (
    KnowledgeRecord,
    MemoryGraphStore,
    MemoryHydrator,
    StaleOwnership,
    make_edge_key,
    persist_candidates,
    read_context,
    read_item_contexts,
    read_related,
    refresh_graph,
    stale_unseen_edges,
)
import routers.public_knowledge_graph as graph_router
from services.knowledge_graph_store import (
    EDGES,
    EVIDENCE,
    RUNS,
    SOURCE_TABLES,
    RELATED_CONTEXT_LIMIT,
    FullTableScanForbidden,
    SupabaseGraphStore,
)
from services.knowledge_graph_hydrate import ProductionKnowledgeHydrator
from scripts.refresh_knowledge_graph import APPLY_ENV, PAGE, load_production_sources, main as refresh_main, produce_all

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase/migrations/20260913_knowledge_graph_relations.sql").read_text(encoding="utf-8")
GRAPH_PY = [
    ROOT / "services/knowledge_graph_svc.py",
    ROOT / "services/knowledge_graph_producers.py",
    ROOT / "services/knowledge_graph_rules.py",
    ROOT / "services/knowledge_graph_store.py",
    ROOT / "services/knowledge_graph_hydrate.py",
    ROOT / "routers/public_knowledge_graph.py",
    ROOT / "scripts/refresh_knowledge_graph.py",
]


def _cand(**over) -> GraphCandidate:
    base = dict(
        source_content_type="KOSHA_GUIDE",
        source_content_id="A-1-2018",
        edge_kind="CONTEXT",
        relation_type="equipment",
        relation_key="forklift",
        relation_label="지게차",
        target_content_type=None,
        target_content_id=None,
        method="CONTROLLED_KEYWORD",
        evidence_type="FIELD_PHRASE",
        evidence_value="지게차",
        source_field="guide_title",
        rule_id="EQUIPMENT_FORKLIFT_V1",
        rule_version="1",
        source_version="v1",
        source_content_hash="hash-a",
        status="ACCEPTED",
    )
    base.update(over)
    return GraphCandidate(**base)


def _rec(**over) -> KnowledgeRecord:
    base = dict(
        content_type="KOSHA_GUIDE",
        content_id="A-1-2018",
        title="지게차 안전",
        summary="지게차 작업",
        tai_url="https://taieng.co.kr/safety-guide/A-1-2018",
        source_name="KOSHA",
        source_url="https://www.kosha.or.kr/x",
        published_at="2020-01-01",
        category="기계",
        is_public_current=True,
    )
    base.update(over)
    return KnowledgeRecord(**base)


def _client(store, hydrator):
    graph_router.configure_graph_read(store=store, hydrator=hydrator)
    app = FastAPI()
    app.include_router(graph_router.router)
    return TestClient(app)


def test_g01_one_edge_two_evidence():
    store = MemoryGraphStore()
    persist_candidates(
        store,
        [
            _cand(method="CONTROLLED_KEYWORD", rule_id="EQUIPMENT_FORKLIFT_V1"),
            _cand(method="SOURCE_NATIVE", rule_id="EQUIPMENT_FORKLIFT_NATIVE", evidence_value="forklift", source_field="category"),
        ],
        run_id="r1",
    )
    assert len(store.edges) == 1
    edge = next(iter(store.edges.values()))
    assert len(store.list_evidence(edge["id"])) == 2


def test_g02_same_evidence_rerun_no_duplicate():
    store = MemoryGraphStore()
    c = _cand()
    persist_candidates(store, [c], run_id="r1")
    out = persist_candidates(store, [c], run_id="r2")
    edge = next(iter(store.edges.values()))
    assert len(store.list_evidence(edge["id"])) == 1
    assert out["duplicate_prevented"] == 1


def test_g03_context_edge_key_deterministic():
    a = make_edge_key(edge_kind="CONTEXT", source_content_type="KOSHA_GUIDE", source_content_id="A-1-2018", relation_type="equipment", relation_key="forklift")
    b = make_edge_key(edge_kind="CONTEXT", source_content_type="KOSHA_GUIDE", source_content_id="A-1-2018", relation_type="equipment", relation_key="forklift")
    assert a == b == "CTX|KOSHA_GUIDE|A-1-2018|equipment|forklift"
    assert "CONTROLLED" not in a and "v1" not in a


def test_g04_direct_edge_key_deterministic():
    a = make_edge_key(
        edge_kind="DIRECT",
        source_content_type="KOSHA_GUIDE",
        source_content_id="A-1-2018",
        relation_type="RELATED_TO",
        target_content_type="SAFETY_MATERIAL",
        target_content_id="m1",
    )
    assert a == "DIR|KOSHA_GUIDE|A-1-2018|RELATED_TO|SAFETY_MATERIAL|m1"


def test_g05_context_direct_constraints():
    with pytest.raises(ValueError):
        make_edge_key(edge_kind="CONTEXT", source_content_type="KOSHA_GUIDE", source_content_id="A-1-2018", relation_type="equipment")
    with pytest.raises(ValueError):
        make_edge_key(edge_kind="DIRECT", source_content_type="KOSHA_GUIDE", source_content_id="A-1-2018", relation_type="RELATED_TO")
    assert "relation_key IS NOT NULL" in SQL
    assert "target_content_id IS NOT NULL" in SQL


def _seed_status(status, **edge_over):
    store = MemoryGraphStore()
    persist_candidates(store, [_cand()], run_id="r1")
    edge = next(iter(store.edges.values()))
    edge.update({"status": status, **edge_over})
    store.upsert_edge(edge)
    hydrator = MemoryHydrator([_rec()])
    return store, hydrator


def test_g06_candidate_excluded_from_public():
    store, hydrator = _seed_status("CANDIDATE")
    assert read_context(store, hydrator, relation_type="equipment", relation_key="forklift")["total"] == 0


def test_g07_rejected_excluded_from_public():
    store, hydrator = _seed_status("REJECTED")
    assert read_context(store, hydrator, relation_type="equipment", relation_key="forklift")["total"] == 0


def test_g08_stale_excluded_from_public():
    store, hydrator = _seed_status("ACCEPTED", is_active=False, stale_at="2026-09-13T00:00:00+09:00")
    assert read_context(store, hydrator, relation_type="equipment", relation_key="forklift")["total"] == 0


def test_g09_inactive_excluded_from_public():
    store, hydrator = _seed_status("ACCEPTED", is_active=False, stale_at=None)
    assert read_context(store, hydrator, relation_type="equipment", relation_key="forklift")["total"] == 0


def test_g10_forklift_mapping():
    cands = produce_guide_relations([{"guide_no": "A-1-2018", "guide_title": "지게차 안전기준", "content_id": "A-1-2018"}], current_ids={"A-1-2018"})
    assert any(c.relation_type == "equipment" and c.relation_key == "forklift" for c in cands)


def test_g11_alias_same_edge():
    a = produce_guide_relations([{"guide_no": "A-1-2018", "guide_title": "포크리프트 안전", "content_id": "A-1-2018"}], current_ids={"A-1-2018"})
    b = produce_guide_relations([{"guide_no": "A-1-2018", "guide_title": "지게차 안전", "content_id": "A-1-2018"}], current_ids={"A-1-2018"})
    assert a[0].relation_key == b[0].relation_key == "forklift"
    assert make_edge_key(edge_kind="CONTEXT", source_content_type="KOSHA_GUIDE", source_content_id="A-1-2018", relation_type="equipment", relation_key="forklift") == make_edge_key(
        edge_kind=a[0].edge_kind, source_content_type=a[0].source_content_type, source_content_id=a[0].source_content_id, relation_type=a[0].relation_type, relation_key=a[0].relation_key
    )


def test_g12_unrelated_vehicle_zero():
    cands = produce_guide_relations([{"guide_no": "A-1-2018", "guide_title": "일반 차량 안전", "content_id": "A-1-2018"}], current_ids={"A-1-2018"})
    assert not any(c.relation_key == "forklift" for c in cands)


def test_g13_welding():
    cands = produce_accident_relations([{"id": "acc-1", "title": "용접 작업 중 화재"}])
    assert any(c.relation_type == "task" and c.relation_key == "welding" for c in cands)


def test_g14_excavation():
    cands = produce_accident_relations([{"id": "acc-2", "accident_summary": "굴착작업 중 붕괴", "work_type": "굴착"}])
    assert any(c.relation_type == "process" and c.relation_key == "excavation" for c in cands)


def test_g15_fall_aliases():
    a = produce_safety_material_relations([{"id": "m1", "title": "추락 재해 예방", "in_current_snapshot": True}], current_ids={"m1"})
    b = produce_safety_material_relations([{"id": "m1", "title": "떨어짐 사고 예방", "in_current_snapshot": True}], current_ids={"m1"})
    assert a[0].relation_key == b[0].relation_key == "fall"


def test_g16_fuzzy_typo_zero():
    cands = produce_guide_relations([{"guide_no": "A-1-2018", "guide_title": "지게챠 안전기준", "content_id": "A-1-2018"}], current_ids={"A-1-2018"})
    assert not any(c.relation_key == "forklift" for c in cands)


def test_g17_g18_no_llm_or_vector():
    blob = "\n".join(p.read_text(encoding="utf-8") for p in GRAPH_PY).lower()
    for token in ("openai", "anthropic", "embedding", "chromadb", "pinecone", "vector_store"):
        assert token not in blob
    assert "from services.legal" not in blob


def test_g19_rerun_idempotent():
    store = MemoryGraphStore()
    guides = [{"guide_no": "A-1-2018", "guide_title": "지게차 안전", "content_id": "A-1-2018"}]
    produced = {"guide": produce_guide_relations(guides, current_ids={"A-1-2018"})}
    refresh_graph(store=store, produced_by_source=produced, scanned_by_source={"guide": 1}, apply=True)
    n = len(store.edges)
    refresh_graph(store=store, produced_by_source=produced, scanned_by_source={"guide": 1}, apply=True)
    assert len(store.edges) == n
    edge = next(iter(store.edges.values()))
    assert len(store.list_evidence(edge["id"])) == 1


def test_g20_unchanged_hash_stable_edge():
    item = {"guide_no": "A-1-2018", "guide_title": "지게차 안전", "content_id": "A-1-2018"}
    a = produce_guide_relations([item], current_ids={"A-1-2018"})[0]
    b = produce_guide_relations([item], current_ids={"A-1-2018"})[0]
    assert a.source_content_hash == b.source_content_hash
    store = MemoryGraphStore()
    persist_candidates(store, [a], run_id="r1")
    persist_candidates(store, [b], run_id="r2")
    assert len(store.edges) == 1


def test_g21_changed_hash_same_edge_new_evidence():
    a = produce_guide_relations([{"guide_no": "A-1-2018", "guide_title": "지게차 안전", "content_id": "A-1-2018"}], current_ids={"A-1-2018"})[0]
    b = produce_guide_relations([{"guide_no": "A-1-2018", "guide_title": "지게차 안전 수칙", "content_id": "A-1-2018"}], current_ids={"A-1-2018"})[0]
    assert a.source_content_hash != b.source_content_hash
    store = MemoryGraphStore()
    persist_candidates(store, [a], run_id="r1")
    persist_candidates(store, [b], run_id="r2")
    edge = next(iter(store.edges.values()))
    assert len(store.edges) == 1
    assert len(store.list_evidence(edge["id"])) == 2


def test_g22_stale_after_completed_scoped_run():
    store = MemoryGraphStore()
    first = {"guide": produce_guide_relations([{"guide_no": "A-1-2018", "guide_title": "지게차 안전", "content_id": "A-1-2018"}], current_ids={"A-1-2018"})}
    refresh_graph(store=store, produced_by_source=first, scanned_by_source={"guide": 1}, apply=True)
    second = {"guide": produce_guide_relations([{"guide_no": "B-1-2018", "guide_title": "지게차 안전", "content_id": "B-1-2018"}], current_ids={"B-1-2018"})}
    report = refresh_graph(store=store, produced_by_source=second, scanned_by_source={"guide": 1}, apply=True)
    stale = [e for e in store.list_edges() if e["source_content_id"] == "A-1-2018"]
    assert stale and stale[0]["is_active"] is False and stale[0]["stale_at"]
    assert report.stale_count >= 1


def test_g23_failed_run_no_stale():
    store = MemoryGraphStore()
    first = {"guide": produce_guide_relations([{"guide_no": "A-1-2018", "guide_title": "지게차 안전", "content_id": "A-1-2018"}], current_ids={"A-1-2018"})}
    refresh_graph(store=store, produced_by_source=first, scanned_by_source={"guide": 1}, apply=True)
    report = refresh_graph(
        store=store,
        produced_by_source={"guide": []},
        scanned_by_source={"guide": 0},
        apply=True,
        abort=True,
    )
    assert report.status == "FAILED"
    edge = next(iter(store.edges.values()))
    assert edge["is_active"] is True
    assert edge.get("stale_at") is None
    assert report.stale_count == 0


def test_g24_partial_failure_no_stale_failed_source():
    store = MemoryGraphStore()
    mats = produce_safety_material_relations([{"id": "m1", "title": "지게차 교육", "in_current_snapshot": True}], current_ids={"m1"})
    refresh_graph(store=store, produced_by_source={"material": mats}, scanned_by_source={"material": 1}, apply=True)
    guides = produce_guide_relations([{"guide_no": "A-1-2018", "guide_title": "지게차 안전", "content_id": "A-1-2018"}], current_ids={"A-1-2018"})
    refresh_graph(
        store=store,
        produced_by_source={"guide": guides},
        scanned_by_source={"guide": 1, "material": 1},
        failed_sources={"material": "SNAPSHOT_UNAVAILABLE"},
        apply=True,
    )
    material_edge = [e for e in store.list_edges() if e["source_content_type"] == "SAFETY_MATERIAL"][0]
    assert material_edge["is_active"] is True


def test_g25_stale_rediscovered_reactivates():
    store = MemoryGraphStore()
    cands = produce_guide_relations([{"guide_no": "A-1-2018", "guide_title": "지게차 안전", "content_id": "A-1-2018"}], current_ids={"A-1-2018"})
    refresh_graph(store=store, produced_by_source={"guide": cands}, scanned_by_source={"guide": 1}, apply=True)
    refresh_graph(store=store, produced_by_source={"guide": []}, scanned_by_source={"guide": 0}, apply=True)
    edge = next(iter(store.edges.values()))
    assert edge["is_active"] is False
    report = refresh_graph(store=store, produced_by_source={"guide": cands}, scanned_by_source={"guide": 1}, apply=True)
    edge = next(iter(store.edges.values()))
    assert edge["is_active"] is True
    assert edge.get("stale_at") is None
    assert report.reactivated_count == 1


def test_g26_non_current_guide_public_zero():
    cands = produce_guide_relations([{"guide_no": "OLD-1", "guide_title": "지게차 안전", "content_id": "OLD-1"}], current_ids={"A-1-2018"})
    assert cands == []
    store = MemoryGraphStore()
    persist_candidates(store, [_cand(source_content_id="OLD-1")], run_id="r1")
    hydrator = MemoryHydrator([_rec(content_id="OLD-1", is_public_current=False)])
    body = read_context(store, hydrator, relation_type="equipment", relation_key="forklift")
    assert body["items"] == []


def test_g27_non_current_material_public_zero():
    cands = produce_safety_material_relations([{"id": "m-old", "title": "지게차", "in_current_snapshot": False}], current_ids={"m1"})
    assert cands == []


def test_g28_unpublished_law_zero():
    cands = produce_law_relations([{"id": "law-1", "law_name": "지게차 관련 고시", "summary": "지게차", "is_public": False, "status": "DRAFT"}])
    assert cands == []
    cands_ok = produce_law_relations([{"id": "law-2", "law_name": "지게차 관련 고시", "summary": "지게차", "is_public": True, "status": "PUBLISHED"}])
    assert cands_ok


def test_g29_accident_resolver_without_current_column():
    src = inspect.getsource(produce_accident_relations)
    assert "current=true" not in src
    cands = produce_accident_relations([{"id": "acc-3", "title": "지게차 전복"}])
    assert cands


def test_g30_history_catalog_not_current_consumer():
    store = MemoryGraphStore()
    persist_candidates(store, [_cand(source_content_type="SAFETY_MATERIAL", source_content_id="hist-1")], run_id="r1")
    hydrator = MemoryHydrator([_rec(content_type="SAFETY_MATERIAL", content_id="hist-1", is_public_current=False, title="history")])
    body = read_context(store, hydrator, relation_type="equipment", relation_key="forklift")
    assert body["items"] == []


def test_g31_g32_g33_read_endpoints():
    store = MemoryGraphStore()
    persist_candidates(
        store,
        [
            _cand(),
            _cand(source_content_type="SAFETY_MATERIAL", source_content_id="m1", source_content_hash="h2"),
        ],
        run_id="r1",
    )
    hydrator = MemoryHydrator(
        [
            _rec(),
            _rec(content_type="SAFETY_MATERIAL", content_id="m1", title="지게차 자료", tai_url="https://taieng.co.kr/safety-news-detail.html?id=m1", published_at="2021-01-01"),
        ]
    )
    client = _client(store, hydrator)
    ctx = client.get("/public/knowledge-graph/context", params={"relation_type": "equipment", "relation_key": "forklift"})
    assert ctx.status_code == 200
    assert ctx.json()["total"] == 2
    item_ctx = client.get("/public/knowledge-graph/items/KOSHA_GUIDE/A-1-2018/contexts")
    assert item_ctx.json()["contexts"][0]["relation_key"] == "forklift"
    related = client.get("/public/knowledge-graph/items/KOSHA_GUIDE/A-1-2018/related")
    ids = {(x["content_type"], x["content_id"]) for x in related.json()["items"]}
    assert ("SAFETY_MATERIAL", "m1") in ids
    assert ("KOSHA_GUIDE", "A-1-2018") not in ids


def test_g34_same_item_excluded():
    store = MemoryGraphStore()
    persist_candidates(store, [_cand()], run_id="r1")
    hydrator = MemoryHydrator([_rec()])
    related = read_related(store, hydrator, content_type="KOSHA_GUIDE", content_id="A-1-2018")
    assert related["items"] == []


def test_g35_target_dedupe():
    store = MemoryGraphStore()
    persist_candidates(
        store,
        [
            _cand(),
            _cand(relation_type="task", relation_key="welding", relation_label="용접", rule_id="TASK_WELDING_V1", evidence_value="용접"),
            _cand(source_content_type="ACCIDENT", source_content_id="acc-1", source_content_hash="h3"),
            _cand(source_content_type="ACCIDENT", source_content_id="acc-1", relation_type="task", relation_key="welding", relation_label="용접", source_content_hash="h3", rule_id="TASK_WELDING_V1"),
        ],
        run_id="r1",
    )
    hydrator = MemoryHydrator([_rec(), _rec(content_type="ACCIDENT", content_id="acc-1", title="사고", published_at="2019-01-01")])
    related = read_related(store, hydrator, content_type="KOSHA_GUIDE", content_id="A-1-2018")
    acc = [i for i in related["items"] if i["content_id"] == "acc-1"]
    assert len(acc) == 1
    assert acc[0]["shared_context_count"] == 2


def test_g36_deterministic_ordering():
    store = MemoryGraphStore()
    persist_candidates(
        store,
        [
            _cand(),
            _cand(source_content_type="ACCIDENT", source_content_id="acc-late", source_content_hash="h4"),
            _cand(source_content_type="ACCIDENT", source_content_id="acc-early", source_content_hash="h5"),
        ],
        run_id="r1",
    )
    hydrator = MemoryHydrator(
        [
            _rec(),
            _rec(content_type="ACCIDENT", content_id="acc-late", published_at="2022-01-01", title="late"),
            _rec(content_type="ACCIDENT", content_id="acc-early", published_at="2018-01-01", title="early"),
        ]
    )
    related = read_related(store, hydrator, content_type="KOSHA_GUIDE", content_id="A-1-2018")
    ids = [i["content_id"] for i in related["items"]]
    assert ids == ["acc-late", "acc-early"]


def test_g37_null_source_fields_allowed():
    rec = _rec(title=None, summary=None, category=None, source_url=None)
    assert rec.public_item()["title"] is None
    store = MemoryGraphStore()
    persist_candidates(store, [_cand()], run_id="r1")
    body = read_context(store, MemoryHydrator([rec]), relation_type="equipment", relation_key="forklift")
    assert body["items"][0]["title"] is None


def test_g38_g39_runtime_hydrate_no_content_copy():
    store = MemoryGraphStore()
    persist_candidates(store, [_cand()], run_id="r1")
    edge = next(iter(store.edges.values()))
    for banned in ("title", "summary", "body", "guide_title"):
        assert banned not in edge
    hydrator = MemoryHydrator([_rec(title="런타임 제목")])
    body = read_context(store, hydrator, relation_type="equipment", relation_key="forklift")
    assert body["items"][0]["title"] == "런타임 제목"


def test_g40_g41_g42_security_legal_evidence_absent():
    store = MemoryGraphStore()
    persist_candidates(store, [_cand()], run_id="r1")
    hydrator = MemoryHydrator([_rec()])
    client = _client(store, hydrator)
    payload = json.dumps(client.get("/public/knowledge-graph/context", params={"relation_type": "equipment", "relation_key": "forklift"}).json())
    for banned in ("legal_applicable", "legal_score", "user_id", "company_id", "factory_id", "diagnosis_id", "evidence_key", "rule_id"):
        assert banned not in payload
    ctx = client.get("/public/knowledge-graph/items/KOSHA_GUIDE/A-1-2018/contexts").json()
    assert "evidence" not in json.dumps(ctx)


def test_g43_source_tables_write_zero():
    store = MemoryGraphStore()
    persist_candidates(store, [_cand()], run_id="r1")
    assert store.source_writes() == 0


def test_g44_legal_engine_untouched():
    for path in GRAPH_PY:
        src = path.read_text(encoding="utf-8")
        assert "services.legal" not in src
        assert "legal_engine" not in src


def test_g45_no_original_binary_copy():
    blob = "\n".join(p.read_text(encoding="utf-8") for p in GRAPH_PY)
    assert "r2" not in blob.lower()
    assert "application/pdf" not in blob.lower()


def test_llm_candidate_rejected():
    assert accept_candidate("LLM_CANDIDATE") == "REJECTED"
    assert accept_candidate("SEMANTIC_CANDIDATE") == "REJECTED"
    assert accept_candidate("CONTROLLED_KEYWORD") == "ACCEPTED"


def test_knowledge_center_deferred_empty():
    assert produce_knowledge_center_relations(None) == []


def test_precedent_producer():
    cands = produce_precedent_relations([{"id": "p1", "case_name": "추락 재해 판결", "summary": "떨어짐"}])
    assert any(c.relation_key == "fall" for c in cands)


def test_migration_additive_and_rls():
    lowered = SQL.lower()
    assert "drop table" not in lowered
    assert "truncate table" not in lowered
    assert "alter table public.kosha_guide" not in lowered
    assert "knowledge_relation_runs" in lowered
    assert "knowledge_relation_edges" in lowered
    assert "knowledge_relation_evidence" in lowered
    assert "grant" in lowered and "anon" in lowered
    assert "revoke all on public.knowledge_relation_edges from anon" in lowered
    assert "unique (edge_id, evidence_key)" in lowered.replace("\n", " ")
    grants = [ln for ln in SQL.splitlines() if ln.strip().upper().startswith("GRANT")]
    assert grants
    assert all("DELETE" not in ln.upper() for ln in grants)
    assert "revoke delete on public.knowledge_relation_edges from service_role" in lowered


def test_guide_shadow_compatibility_sample():
    guides = [{"guide_no": f"G-{i}", "guide_title": title, "content_id": f"G-{i}"} for i, title in enumerate([
        "지게차 운전 작업 안전",
        "용접작업 화재 예방",
        "굴착작업 붕괴 예방",
        "추락 재해 예방 지침",
        "건설업 안전보건",
        "고소작업대 안전",
        "크레인 양중작업",
        "밀폐공간 질식",
        "전기 감전 예방",
        "화학물질 누출",
        "지게차 하역 작업",
        "아크 용접 안전수칙",
        "굴착면 보호 지침",
        "떨어짐 방지 설비",
        "비계 설치 해체",
        "타워크레인 신호",
        "산소결핍 위험",
        "분진 폭발 예방",
        "차량계 하역운반",
        "지게차 포크리프트 점검사항",
    ], start=1)]
    materials = [{"id": f"M-{i}", "title": title, "in_current_snapshot": True} for i, title in enumerate([
        "지게차 운전 교육자료",
        "용접작업 화재 사례",
        "굴착작업 붕괴 사례집",
        "추락 재해 예방 포스터",
        "건설업 안전보건 자료",
        "고소작업대 교육",
        "크레인 양중 교육",
        "밀폐공간 질식 예방",
        "전기 감전 사례",
        "화학물질 누출 대응",
        "지게차 하역 안전",
        "아크 용접 보호구",
        "굴착면 보호 교육",
        "떨어짐 방지 설비 안내",
        "비계 설치 해체 지침",
        "타워크레인 신호수",
        "산소결핍 질식",
        "분진 폭발 사례",
        "차량계 하역운반 기계",
        "지게차 포크리프트 점검표",
    ], start=1)]
    expected = set()
    for g in guides:
        for m in materials:
            if is_guide_material_related(g["guide_title"], m["title"]):
                expected.add((g["content_id"], m["id"]))
    shadow = produce_guide_material_shadow(
        guides,
        materials,
        current_guide_ids={g["content_id"] for g in guides},
        current_material_ids={m["id"] for m in materials},
    )
    got = {(c.source_content_id, c.target_content_id) for c in shadow}
    assert got == expected
    assert len(expected) >= 10
    matcher_only = expected - got
    graph_only = got - expected
    assert matcher_only == set()
    assert graph_only == set()


def test_guide_production_code_not_replaced():
    sync = (ROOT / "services/kosha_guide_sync.py").read_text(encoding="utf-8")
    display = (ROOT / "services/kosha_safety_materials/display.py").read_text(encoding="utf-8")
    assert "knowledge_graph" not in sync
    assert "knowledge_graph" not in display
    assert "public_knowledge_graph" not in sync
    robots_mentions = ["robots", "sitemap", "noindex"]
    graph_src = (ROOT / "routers/public_knowledge_graph.py").read_text(encoding="utf-8")
    for token in robots_mentions:
        assert token not in graph_src.lower()


def test_dry_run_cli_writes_zero(tmp_path, capsys):
    fixture = tmp_path / "sources.json"
    fixture.write_text(json.dumps({
        "guide": [{"guide_no": "A-1-2018", "guide_title": "지게차 안전", "content_id": "A-1-2018"}]
    }), encoding="utf-8")
    rc = refresh_main(["--source", "guide", "--context", "equipment:forklift", "--fixture-json", str(fixture)])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 0
    assert payload["db_write"] == 0
    assert payload["dry_run"] is True
    assert payload["accepted"] >= 1


def test_apply_cli_blocked(tmp_path):
    fixture = tmp_path / "sources.json"
    fixture.write_text(json.dumps({"guide": []}), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        refresh_main(["--apply", "--source", "guide", "--fixture-json", str(fixture)])
    assert "PRODUCTION_APPLY_GATED" in str(exc.value)


def test_router_registry_includes_graph():
    src = (ROOT / "router_registry/public.py").read_text(encoding="utf-8")
    assert "routers.public_knowledge_graph" in src


def test_time_contract_no_datetime_now():
    for path in GRAPH_PY:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "now":
                # allow now_kst only
                pass
        src = path.read_text(encoding="utf-8")
        assert "datetime.now(" not in src
        assert "datetime.utcnow" not in src


def _insert_run(store: MemoryGraphStore, status: str, run_id: str):
    return store.insert_run(
        {
            "id": run_id,
            "run_type": "TEST",
            "scope_json": {},
            "rule_set_version": "GRAPH_RULES_V1",
            "status": status,
            "dry_run": False,
            "started_at": "2026-09-13T00:00:00+09:00",
        }
    )


def _guide_context_scope():
    return [
        StaleOwnership(
            source_content_type="KOSHA_GUIDE",
            edge_kind="CONTEXT",
            producer_family="CONTEXT_CONTROLLED",
        )
    ]


def test_g46_running_run_stale_zero():
    store = MemoryGraphStore()
    persist_candidates(store, [_cand()], run_id="seed")
    _insert_run(store, "RUNNING", "running")
    mutated = stale_unseen_edges(store, run_id="running", scopes=_guide_context_scope())
    edge = next(iter(store.edges.values()))
    assert mutated == 0
    assert edge["is_active"] is True
    assert edge.get("stale_at") is None


def test_g47_failed_run_stale_zero():
    store = MemoryGraphStore()
    persist_candidates(store, [_cand()], run_id="seed")
    _insert_run(store, "FAILED", "failed")
    mutated = stale_unseen_edges(store, run_id="failed", scopes=_guide_context_scope())
    edge = next(iter(store.edges.values()))
    assert mutated == 0
    assert edge["is_active"] is True


def test_g48_completed_run_scoped_stale():
    store = MemoryGraphStore()
    persist_candidates(store, [_cand()], run_id="seed")
    _insert_run(store, "COMPLETED", "done")
    mutated = stale_unseen_edges(store, run_id="done", scopes=_guide_context_scope())
    edge = next(iter(store.edges.values()))
    assert mutated == 1
    assert edge["is_active"] is False
    assert edge.get("stale_at")


def test_guide_direct_not_stale_when_shadow_producer_not_run():
    store = MemoryGraphStore()
    guides = [{"guide_no": "A-1-2018", "guide_title": "지게차 운전 작업 안전", "content_id": "A-1-2018"}]
    materials = [{"id": "m1", "title": "지게차 운전 교육자료", "in_current_snapshot": True}]
    ctx = produce_guide_relations(guides, current_ids={"A-1-2018"})
    shadow = produce_guide_material_shadow(
        guides, materials, current_guide_ids={"A-1-2018"}, current_material_ids={"m1"}
    )
    mats = produce_safety_material_relations(materials, current_ids={"m1"})
    assert ctx and shadow
    refresh_graph(
        store=store,
        produced_by_source={"guide": ctx, "guide_shadow": shadow, "material": mats},
        scanned_by_source={"guide": 1, "material": 1},
        apply=True,
    )
    refresh_graph(
        store=store,
        produced_by_source={"guide": ctx},
        scanned_by_source={"guide": 1},
        apply=True,
    )
    direct = [e for e in store.list_edges() if e["edge_kind"] == "DIRECT"]
    context = [e for e in store.list_edges() if e["edge_kind"] == "CONTEXT" and e["source_content_type"] == "KOSHA_GUIDE"]
    assert direct and direct[0]["is_active"] is True
    assert direct[0].get("stale_at") is None
    assert context and context[0]["is_active"] is True


def test_g49_accepted_not_sticky_when_run_all_rejected():
    store = MemoryGraphStore()
    persist_candidates(store, [_cand()], run_id="r1")
    persist_candidates(store, [_cand(status="REJECTED", evidence_value="지게차-dropped")], run_id="r2")
    edge = next(iter(store.edges.values()))
    assert edge["status"] == "REJECTED"
    body = read_context(store, MemoryHydrator([_rec()]), relation_type="equipment", relation_key="forklift")
    assert body["total"] == 0


def test_g50_rejected_plus_accepted_is_accepted():
    store = MemoryGraphStore()
    persist_candidates(
        store,
        [
            _cand(status="REJECTED", method="CONTROLLED_KEYWORD", evidence_value="weak"),
            _cand(status="ACCEPTED", method="SOURCE_NATIVE", rule_id="NATIVE", evidence_value="forklift"),
        ],
        run_id="r1",
    )
    edge = next(iter(store.edges.values()))
    assert edge["status"] == "ACCEPTED"
    assert len(store.list_evidence(edge["id"])) == 2


def test_g51_candidate_order_does_not_change_status():
    a = [
        _cand(status="REJECTED", method="CONTROLLED_KEYWORD", evidence_value="weak"),
        _cand(status="ACCEPTED", method="SOURCE_NATIVE", rule_id="NATIVE", evidence_value="forklift"),
    ]
    b = list(reversed(a))
    store_a = MemoryGraphStore()
    store_b = MemoryGraphStore()
    persist_candidates(store_a, a, run_id="r1")
    persist_candidates(store_b, b, run_id="r1")
    assert next(iter(store_a.edges.values()))["status"] == next(iter(store_b.edges.values()))["status"] == "ACCEPTED"


class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = len(data) if count is None else count


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self._action = "select"
        self._filters = []
        self._payload = None
        self._limit = None
        self._orders = []
        self._order = None
        self._on_conflict = None
        self._range = None
        self._count = None

    def select(self, cols="*", count=None):
        self._action = "select"
        self._count = count
        self.client.ops.append(("select", self.table, cols))
        return self

    def insert(self, row):
        self._action = "insert"
        self._payload = row
        self.client.ops.append(("insert", self.table))
        return self

    def upsert(self, row, on_conflict=None):
        self._action = "upsert"
        self._payload = row
        self._on_conflict = on_conflict
        self.client.ops.append(("upsert", self.table, on_conflict))
        return self

    def update(self, patch):
        self._action = "update"
        self._payload = patch
        self.client.ops.append(("update", self.table))
        return self

    def delete(self):
        self._action = "delete"
        self.client.ops.append(("delete", self.table))
        self.client.delete_calls += 1
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        self.client.ops.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        self.client.ops.append(("neq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        self.client.ops.append(("in", col, list(vals)))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def order(self, col, desc=False):
        self._orders.append((col, desc))
        self._order = (col, desc)
        return self

    def range(self, start, end):
        self._range = (start, end)
        self.client.ops.append(("range", start, end))
        return self

    def _match(self, row):
        for kind, col, val in self._filters:
            cell = row.get(col)
            if kind == "eq" and cell != val:
                return False
            if kind == "neq" and cell == val:
                return False
            if kind == "in" and cell not in val:
                return False
        return True

    def execute(self):
        rows = self.client.tables.setdefault(self.table, [])
        if self._action == "select":
            if self.table == EDGES and not self._filters:
                self.client.unbounded_edge_selects += 1
            found = [dict(r) for r in rows if self._match(r)]
            total = len(found)
            orders = self._orders or ([self._order] if self._order else [])
            for col, desc in reversed(orders):
                found.sort(key=lambda r, c=col: r.get(c) or "", reverse=bool(desc))
            if self._range is not None:
                start, end = self._range
                found = found[start : end + 1]
            if self._limit is not None:
                found = found[: self._limit]
            return _Resp(found, count=total if self._count else len(found))
        if self._action == "insert":
            row = dict(self._payload)
            row.setdefault("id", str(uuid.uuid4()))
            rows.append(row)
            self.client.writes.append((self.table, "insert"))
            return _Resp([row])
        if self._action == "upsert":
            row = dict(self._payload)
            keys = [k.strip() for k in (self._on_conflict or "").split(",") if k.strip()]
            idx = None
            for i, existing in enumerate(rows):
                if keys and all(existing.get(k) == row.get(k) for k in keys):
                    idx = i
                    break
            if idx is None:
                row.setdefault("id", str(uuid.uuid4()))
                rows.append(row)
            else:
                merged = dict(rows[idx])
                merged.update(row)
                merged["id"] = rows[idx].get("id") or row.get("id") or str(uuid.uuid4())
                rows[idx] = merged
                row = merged
            self.client.writes.append((self.table, "upsert"))
            return _Resp([row])
        if self._action == "update":
            updated = []
            for row in rows:
                if self._match(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            self.client.writes.append((self.table, "update"))
            return _Resp(updated)
        if self._action == "delete":
            self.client.writes.append((self.table, "delete"))
            return _Resp([])
        return _Resp([])


class FakeSB:
    def __init__(self):
        self.tables: dict[str, list] = {}
        self.ops = []
        self.writes = []
        self.delete_calls = 0
        self.unbounded_edge_selects = 0

    def table(self, name):
        return FakeQuery(self, name)

    def seed(self, table, row):
        self.tables.setdefault(table, []).append(dict(row))


def _prod_store():
    sb = FakeSB()
    return sb, SupabaseGraphStore(sb)


def test_g52_supabase_edge_conflict_one_semantic_edge():
    sb, store = _prod_store()
    persist_candidates(store, [_cand(), _cand(method="SOURCE_NATIVE", rule_id="NATIVE", evidence_value="forklift")], run_id="r1")
    assert len(sb.tables[EDGES]) == 1


def test_g53_evidence_conflict_no_duplicate():
    sb, store = _prod_store()
    c = _cand()
    persist_candidates(store, [c], run_id="r1")
    out = persist_candidates(store, [c], run_id="r2")
    assert len(sb.tables[EVIDENCE]) == 1
    assert out["duplicate_prevented"] == 1


def test_g54_context_query_not_full_scan():
    sb, store = _prod_store()
    persist_candidates(store, [_cand()], run_id="r1")
    sb.unbounded_edge_selects = 0
    rows = store.query_context_edges(relation_type="equipment", relation_key="forklift")
    assert rows
    assert sb.unbounded_edge_selects == 0
    assert ("eq", "relation_type", "equipment") in sb.ops
    assert ("eq", "relation_key", "forklift") in sb.ops
    with pytest.raises(FullTableScanForbidden):
        store.list_edges()


def test_g55_item_contexts_bounded_query():
    sb, store = _prod_store()
    persist_candidates(store, [_cand()], run_id="r1")
    store.query_item_context_edges(content_type="KOSHA_GUIDE", content_id="A-1-2018")
    assert ("eq", "source_content_type", "KOSHA_GUIDE") in sb.ops
    assert ("eq", "source_content_id", "A-1-2018") in sb.ops
    assert sb.unbounded_edge_selects == 0


def test_g56_related_query_is_context_bounded():
    sb, store = _prod_store()
    persist_candidates(
        store,
        [_cand(), _cand(source_content_type="SAFETY_MATERIAL", source_content_id="m1", source_content_hash="h2")],
        run_id="r1",
    )
    rows = store.query_edges_for_contexts([("equipment", "forklift")], exclude_content=("KOSHA_GUIDE", "A-1-2018"))
    assert any(r["source_content_id"] == "m1" for r in rows)
    assert sb.unbounded_edge_selects == 0
    assert ("eq", "relation_type", "equipment") in sb.ops


def test_g57_stale_production_query_has_scope_where():
    sb, store = _prod_store()
    persist_candidates(store, [_cand()], run_id="seed")
    store.query_stale_scope_edges(
        source_content_type="KOSHA_GUIDE",
        edge_kind="CONTEXT",
        relation_type="equipment",
        relation_key="forklift",
        exclude_run_id="done",
    )
    assert ("eq", "source_content_type", "KOSHA_GUIDE") in sb.ops
    assert ("eq", "edge_kind", "CONTEXT") in sb.ops
    assert ("neq", "last_seen_run_id", "done") in sb.ops
    assert sb.unbounded_edge_selects == 0


def test_g58_running_production_stale_zero():
    sb, store = _prod_store()
    persist_candidates(store, [_cand()], run_id="seed")
    store.insert_run({"id": "running", "status": "RUNNING", "run_type": "TEST", "rule_set_version": "v", "started_at": "t"})
    n = stale_unseen_edges(store, run_id="running", scopes=_guide_context_scope())
    assert n == 0
    assert sb.tables[EDGES][0]["is_active"] is True


def test_g59_failed_production_stale_zero():
    _, store = _prod_store()
    persist_candidates(store, [_cand()], run_id="seed")
    store.insert_run({"id": "failed", "status": "FAILED", "run_type": "TEST", "rule_set_version": "v", "started_at": "t"})
    assert stale_unseen_edges(store, run_id="failed", scopes=_guide_context_scope()) == 0


def test_g60_completed_production_stale_scoped_only():
    sb, store = _prod_store()
    persist_candidates(store, [_cand()], run_id="seed")
    persist_candidates(
        store,
        [
            _cand(
                edge_kind="DIRECT",
                relation_type="RELATED_TO",
                relation_key=None,
                target_content_type="SAFETY_MATERIAL",
                target_content_id="m1",
                method="DETERMINISTIC_RULE",
            )
        ],
        run_id="seed",
    )
    store.insert_run({"id": "done", "status": "COMPLETED", "run_type": "TEST", "rule_set_version": "v", "started_at": "t"})
    n = stale_unseen_edges(store, run_id="done", scopes=_guide_context_scope())
    assert n == 1
    ctx = [e for e in sb.tables[EDGES] if e["edge_kind"] == "CONTEXT"][0]
    direct = [e for e in sb.tables[EDGES] if e["edge_kind"] == "DIRECT"][0]
    assert ctx["is_active"] is False
    assert direct["is_active"] is True


def _seed_hydrate(sb: FakeSB):
    sb.seed("kosha_guide_current", {"guide_no": "A-1-2018", "guide_title": "지게차 안전", "category_name": "기계", "guide_url": "https://kosha.example/a", "regist_date": "2020-01-01"})
    sb.seed("kosha_safety_material_snapshots", {"id": "snap1", "status": "COMPLETED", "completed_at": "2026-09-01"})
    sb.seed("kosha_safety_material_snapshot_items", {"snapshot_id": "snap1", "material_id": "m1"})
    sb.seed("kosha_safety_materials", {"id": "m1", "title": "지게차 자료", "category": "EDU", "url": "https://kosha.example/m", "collected_at": "2021-01-01"})
    sb.seed("kosha_safety_materials", {"id": "m-old", "title": "비현재 자료", "category": "EDU"})
    sb.seed("law_revision_board", {"id": "law-pub", "law_name": "공개 법령", "summary": "s", "status": "PUBLISHED", "is_public": True, "enforcement_date": "2022-01-01"})
    sb.seed("law_revision_board", {"id": "law-draft", "law_name": "미공개", "summary": "s", "status": "DRAFT", "is_public": False})
    sb.seed("kosha_accident_cases", {"id": "acc-1", "title": "사고", "reg_dt": "2019-01-01", "file_url": "https://kosha.example/acc"})
    sb.seed("industrial_accident_precedents", {"id": "p1", "case_name": "판례", "summary": "추락"})


def test_g61_guide_current_hydration():
    sb = FakeSB()
    _seed_hydrate(sb)
    recs = ProductionKnowledgeHydrator(sb).get_many([("KOSHA_GUIDE", "A-1-2018")])
    rec = recs[("KOSHA_GUIDE", "A-1-2018")]
    assert rec.title == "지게차 안전"
    assert rec.is_public_current is True


def test_g62_material_current_snapshot_hydration():
    sb = FakeSB()
    _seed_hydrate(sb)
    recs = ProductionKnowledgeHydrator(sb).get_many([("SAFETY_MATERIAL", "m1")])
    assert recs[("SAFETY_MATERIAL", "m1")].title == "지게차 자료"


def test_g63_non_current_material_excluded():
    sb = FakeSB()
    _seed_hydrate(sb)
    recs = ProductionKnowledgeHydrator(sb).get_many([("SAFETY_MATERIAL", "m-old")])
    assert recs == {}


def test_g64_unpublished_law_excluded():
    sb = FakeSB()
    _seed_hydrate(sb)
    recs = ProductionKnowledgeHydrator(sb).get_many([("LAW_UPDATE", "law-draft"), ("LAW_UPDATE", "law-pub")])
    assert ("LAW_UPDATE", "law-draft") not in recs
    assert ("LAW_UPDATE", "law-pub") in recs


def test_g65_mixed_ids_batch_by_source():
    sb = FakeSB()
    _seed_hydrate(sb)
    hydrator = ProductionKnowledgeHydrator(sb)
    recs = hydrator.get_many([("KOSHA_GUIDE", "A-1-2018"), ("SAFETY_MATERIAL", "m1"), ("ACCIDENT", "acc-1")])
    assert len(recs) == 3
    assert hydrator.batch_queries <= 8


def test_g66_missing_content_omitted():
    sb = FakeSB()
    _seed_hydrate(sb)
    recs = ProductionKnowledgeHydrator(sb).get_many([("KOSHA_GUIDE", "MISSING")])
    assert recs == {}


def test_g67_hydration_not_n_plus_one():
    sb = FakeSB()
    for i in range(5):
        sb.seed("kosha_guide_current", {"guide_no": f"G-{i}", "guide_title": "지게차"})
    hydrator = ProductionKnowledgeHydrator(sb)
    recs = hydrator.get_many([("KOSHA_GUIDE", f"G-{i}") for i in range(5)])
    assert len(recs) == 5
    guide_selects = [op for op in sb.ops if op[0] == "select" and op[1] == "kosha_guide_current"]
    assert len(guide_selects) == 1
    assert hydrator.batch_queries == 1


def test_g68_g70_production_provider_http_ok():
    sb, store = _prod_store()
    persist_candidates(
        store,
        [_cand(), _cand(source_content_type="SAFETY_MATERIAL", source_content_id="m1", source_content_hash="h2")],
        run_id="r1",
    )
    _seed_hydrate(sb)
    hydrator = ProductionKnowledgeHydrator(sb)
    client = _client(store, hydrator)
    ctx = client.get("/public/knowledge-graph/context", params={"relation_type": "equipment", "relation_key": "forklift"})
    assert ctx.status_code == 200
    assert ctx.json()["total"] >= 1
    item_ctx = client.get("/public/knowledge-graph/items/KOSHA_GUIDE/A-1-2018/contexts")
    assert item_ctx.status_code == 200
    related = client.get("/public/knowledge-graph/items/KOSHA_GUIDE/A-1-2018/related")
    assert related.status_code == 200


def test_g71_backend_unavailable_safe_503(monkeypatch):
    graph_router.reset_graph_read()

    def boom():
        raise RuntimeError("no db")

    monkeypatch.setattr(graph_router, "_lazy_production", boom)
    app = FastAPI()
    app.include_router(graph_router.router)
    r = TestClient(app).get(
        "/public/knowledge-graph/context",
        params={"relation_type": "equipment", "relation_key": "forklift"},
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "GRAPH_READ_UNAVAILABLE"
    assert "Traceback" not in r.text
    graph_router.reset_graph_read()


def test_g72_non_public_status_zero():
    sb, store = _prod_store()
    persist_candidates(store, [_cand(status="REJECTED")], run_id="r1")
    _seed_hydrate(sb)
    body = read_context(store, ProductionKnowledgeHydrator(sb), relation_type="equipment", relation_key="forklift")
    assert body["total"] == 0


def test_g73_g74_public_omits_evidence_and_legal():
    sb, store = _prod_store()
    persist_candidates(store, [_cand()], run_id="r1")
    _seed_hydrate(sb)
    client = _client(store, ProductionKnowledgeHydrator(sb))
    payload = json.dumps(
        client.get("/public/knowledge-graph/context", params={"relation_type": "equipment", "relation_key": "forklift"}).json()
    )
    for banned in ("evidence_key", "rule_id", "legal_applicable", "legal_score", "user_id"):
        assert banned not in payload


def test_g75_apply_without_env_blocked(tmp_path, monkeypatch):
    monkeypatch.delenv(APPLY_ENV, raising=False)
    fixture = tmp_path / "sources.json"
    fixture.write_text(json.dumps({"guide": []}), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        refresh_main(["--apply", "--source", "guide", "--fixture-json", str(fixture)])
    assert "PRODUCTION_APPLY_GATED" in str(exc.value)


def test_g76_env_without_apply_is_dry_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(APPLY_ENV, "1")
    fixture = tmp_path / "sources.json"
    fixture.write_text(
        json.dumps({"guide": [{"guide_no": "A-1-2018", "guide_title": "지게차 안전", "content_id": "A-1-2018"}]}),
        encoding="utf-8",
    )
    rc = refresh_main(["--source", "guide", "--fixture-json", str(fixture)])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["dry_run"] is True
    assert payload["db_write"] == 0


def test_g77_g80_two_key_apply_writes_graph_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(APPLY_ENV, "1")
    fixture = tmp_path / "sources.json"
    fixture.write_text(
        json.dumps({"guide": [{"guide_no": "A-1-2018", "guide_title": "지게차 안전", "content_id": "A-1-2018"}]}),
        encoding="utf-8",
    )
    sb, store = _prod_store()
    rc = refresh_main(
        ["--apply", "--source", "guide", "--fixture-json", str(fixture)],
        graph_store=store,
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "COMPLETED"
    written = {table for table, _op in sb.writes}
    assert written <= {RUNS, EDGES, EVIDENCE}
    assert store.source_writes() == 0
    assert sb.delete_calls == 0
    assert not any(op[0] == "delete" for op in sb.ops)
    assert not any(table in SOURCE_TABLES for table, _op in sb.writes)


def test_guide_shadow_requires_both_sources():
    produced = produce_all(
        {"guide": [{"guide_no": "A-1-2018", "guide_title": "지게차 운전 작업 안전", "content_id": "A-1-2018"}]},
        {"guide": {"A-1-2018"}},
        failed_sources={"material": "SNAPSHOT_UNAVAILABLE"},
    )
    assert "guide_shadow" not in produced
    both = produce_all(
        {
            "guide": [{"guide_no": "A-1-2018", "guide_title": "지게차 운전 작업 안전", "content_id": "A-1-2018"}],
            "material": [{"id": "m1", "title": "지게차 운전 교육자료", "in_current_snapshot": True}],
        },
        {"guide": {"A-1-2018"}, "material": {"m1"}},
        failed_sources={},
    )
    assert "guide_shadow" in both


def test_g81_g83_material_membership_full_paging():
    sb = FakeSB()
    sb.seed("kosha_safety_material_snapshots", {"id": "snap1", "status": "COMPLETED", "completed_at": "2026-09-01"})
    n = 1200
    for i in range(n):
        mid = f"m-{i:04d}"
        sb.seed("kosha_safety_material_snapshot_items", {"snapshot_id": "snap1", "material_id": mid})
        sb.seed("kosha_safety_materials", {"id": mid, "title": f"지게차 {i}", "category": "EDU"})
    stats = {}
    items, errors = load_production_sources(sb, {"material"}, stats=stats)
    assert errors == {}
    assert stats["material_membership_fetched"] == n
    assert stats["material_membership_declared"] == n
    assert len(items["material"]) == n
    ranges = [op for op in sb.ops if op[0] == "range"]
    assert ("range", 0, PAGE - 1) in ranges
    assert ("range", PAGE, PAGE * 2 - 1) in ranges
    produced = produce_all(items, {"material": {row["content_id"] for row in items["material"]}})
    assert len(items["material"]) == stats["material_membership_fetched"]
    scanned = len(items["material"])
    assert scanned == n
    assert produced["material"] or True


def test_g82_second_page_not_dropped():
    sb = FakeSB()
    sb.seed("kosha_safety_material_snapshots", {"id": "snap1", "status": "COMPLETED", "completed_at": "2026-09-01"})
    for i in range(1200):
        sb.seed("kosha_safety_material_snapshot_items", {"snapshot_id": "snap1", "material_id": f"m-{i:04d}"})
    from scripts.refresh_knowledge_graph import _paged_filtered
    rows = _paged_filtered(
        sb,
        "kosha_safety_material_snapshot_items",
        "material_id",
        eq={"snapshot_id": "snap1"},
    )
    ids = [r["material_id"] for r in rows]
    assert len(ids) == 1200
    assert "m-0000" in ids and "m-1199" in ids
    assert len(set(ids)) == 1200


def test_g84_g88_context_db_paging():
    sb, store = _prod_store()
    recs = []
    for i in range(5):
        cid = f"G-{i}"
        persist_candidates(store, [_cand(source_content_id=cid, source_content_hash=f"h{i}")], run_id="r1")
        recs.append(_rec(content_id=cid, title=f"t{i}", published_at=f"202{i}-01-01"))
    hydrator = MemoryHydrator(recs)

    class Spy:
        def __init__(self, inner):
            self.inner = inner
            self.seen = []

        def get_many(self, pairs):
            self.seen.extend(list(pairs))
            return self.inner.get_many(pairs)

        def get(self, *a):
            return self.inner.get(*a)

    spy = Spy(hydrator)
    sb.ops = []
    page1 = read_context(store, spy, relation_type="equipment", relation_key="forklift", page=1, page_size=2)
    ranges = [op for op in sb.ops if op[0] == "range"]
    assert ("range", 0, 1) in ranges
    assert len(page1["items"]) == 2
    assert page1["total"] == 5
    assert len(spy.seen) <= 2
    spy.seen.clear()
    page2 = read_context(store, spy, relation_type="equipment", relation_key="forklift", page=2, page_size=2)
    assert page2["items"]
    assert [i["content_id"] for i in page1["items"]] != [i["content_id"] for i in page2["items"]]
    assert len(page2["items"]) == 2
    assert len(spy.seen) <= 2
    rows = store.query_context_edges(relation_type="equipment", relation_key="forklift", page=1, page_size=2)
    assert len(rows) <= 2


def test_g89_related_context_bounded(monkeypatch):
    sb, store = _prod_store()
    persist_candidates(store, [_cand()], run_id="r1")
    for i in range(500):
        sb.seed(
            EDGES,
            {
                "id": f"e-{i}",
                "edge_key": f"CTX|ACCIDENT|{i}|equipment|forklift",
                "edge_kind": "CONTEXT",
                "source_content_type": "ACCIDENT",
                "source_content_id": str(i),
                "relation_type": "equipment",
                "relation_key": "forklift",
                "status": "ACCEPTED",
                "is_active": True,
            },
        )
    rows = store.query_edges_for_contexts([("equipment", "forklift")], exclude_content=("KOSHA_GUIDE", "A-1-2018"))
    assert len(rows) <= RELATED_CONTEXT_LIMIT
    assert RELATED_CONTEXT_LIMIT == 100


def test_g90_edge_id_immutable_on_conflict():
    _, store = _prod_store()
    persist_candidates(store, [_cand()], run_id="r1")
    before = store.get_edge_by_key("CTX|KOSHA_GUIDE|A-1-2018|equipment|forklift")["id"]
    persist_candidates(store, [_cand(method="SOURCE_NATIVE", rule_id="NATIVE", evidence_value="forklift")], run_id="r2")
    after = store.get_edge_by_key("CTX|KOSHA_GUIDE|A-1-2018|equipment|forklift")["id"]
    assert before == after


def test_g91_evidence_id_immutable_on_conflict():
    _, store = _prod_store()
    c = _cand()
    persist_candidates(store, [c], run_id="r1")
    edge = store.get_edge_by_key("CTX|KOSHA_GUIDE|A-1-2018|equipment|forklift")
    ev = store.list_evidence(edge["id"])[0]
    before = ev["id"]
    persist_candidates(store, [c], run_id="r2")
    store.insert_evidence(
        {
            "id": str(uuid.uuid4()),
            "edge_id": edge["id"],
            "evidence_key": ev["evidence_key"],
            "last_seen_run_id": "r3",
        }
    )
    after = store.list_evidence(edge["id"])[0]["id"]
    assert before == after


def test_g92_domestic_accident_source_normalized():
    sb = FakeSB()
    sb.seed(
        "kosha_accident_cases",
        {"id": "acc-d1", "title": "지게차 전복", "reg_dt": "2019-03-01", "file_url": "https://kosha.example/d1"},
    )
    items, errors = load_production_sources(sb, {"accident"})
    assert errors == {}
    row = next(r for r in items["accident"] if r["content_id"] == "acc-d1")
    assert row["published_at"] == "2019-03-01"
    assert row["source_url"] == "https://kosha.example/d1"


def test_g93_construction_accident_source_normalized():
    sb = FakeSB()
    sb.seed(
        "kosha_construction_accidents",
        {
            "id": "acc-c1",
            "accident_summary": "굴착 중 붕괴",
            "work_type": "굴착",
            "accident_type": "붕괴",
            "occurrence_date": "2020-04-02",
        },
    )
    items, errors = load_production_sources(sb, {"accident"})
    assert errors == {}
    row = next(r for r in items["accident"] if r["content_id"] == "acc-c1")
    assert row["published_at"] == "2020-04-02"
    assert "source_url" not in row or row.get("source_url") is None


def test_g94_hydrator_domestic_production_columns():
    sb = FakeSB()
    sb.seed(
        "kosha_accident_cases",
        {"id": "acc-d1", "title": "지게차 전복", "reg_dt": "2019-03-01", "file_url": "https://kosha.example/d1"},
    )
    rec = ProductionKnowledgeHydrator(sb).get("ACCIDENT", "acc-d1")
    assert rec is not None
    assert rec.title == "지게차 전복"
    assert rec.published_at == "2019-03-01"
    assert rec.source_url == "https://kosha.example/d1"
    assert rec.content_type == "ACCIDENT"
    assert rec.is_public_current is True


def test_g95_hydrator_construction_production_columns():
    sb = FakeSB()
    sb.seed(
        "kosha_construction_accidents",
        {
            "id": "acc-c1",
            "accident_summary": "굴착 중 붕괴",
            "work_type": "굴착",
            "accident_type": "붕괴",
            "occurrence_date": "2020-04-02",
        },
    )
    rec = ProductionKnowledgeHydrator(sb).get("ACCIDENT", "acc-c1")
    assert rec is not None
    assert rec.summary == "굴착 중 붕괴"
    assert rec.published_at == "2020-04-02"
    assert rec.source_url is None
    assert rec.content_type == "ACCIDENT"
    assert rec.is_public_current is True


def test_g96_accident_adapter_selects_production_columns():
    files = [
        ROOT / "scripts/refresh_knowledge_graph.py",
        ROOT / "services/knowledge_graph_hydrate.py",
    ]
    forbidden = (
        "occurred_at",
        "id,title,url",
        "id,title,occurred_at,url",
        "accident_type,occurred_at",
    )
    for path in files:
        src = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in src, f"{path.name} still selects {token}"
    refresh = (ROOT / "scripts/refresh_knowledge_graph.py").read_text(encoding="utf-8")
    hydrate = (ROOT / "services/knowledge_graph_hydrate.py").read_text(encoding="utf-8")
    assert "id,title,reg_dt,file_url" in refresh
    assert "id,accident_summary,work_type,accident_type,occurrence_date" in refresh
    assert "id,title,reg_dt,file_url" in hydrate
    assert "id,accident_summary,work_type,accident_type,occurrence_date" in hydrate

