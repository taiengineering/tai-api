"""OBJ-GRAPH G01–G51 + GUIDE shadow compatibility. No production DB."""
from __future__ import annotations

import ast
import inspect
import json
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
from scripts.refresh_knowledge_graph import main as refresh_main

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase/migrations/20260913_knowledge_graph_relations.sql").read_text(encoding="utf-8")
GRAPH_PY = [
    ROOT / "services/knowledge_graph_svc.py",
    ROOT / "services/knowledge_graph_producers.py",
    ROOT / "services/knowledge_graph_rules.py",
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
    assert read_context(store, hydrator, relation_type="equipment", relation_key="forklift")["total"] == 0


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
    assert read_context(store, hydrator, relation_type="equipment", relation_key="forklift")["total"] == 0


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
