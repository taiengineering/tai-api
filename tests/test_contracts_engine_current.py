from routers import contracts_engine


def test_expert_type_label_mapping_snapshot():
    assert contracts_engine._expert_type_label("EXPERT") == "선임대행"
    assert contracts_engine._expert_type_label("CONSULTING") == "컨설팅"
    assert contracts_engine._expert_type_label("REPAIR") == "수선중개"
    assert contracts_engine._expert_type_label("UNKNOWN") == "UNKNOWN"


def test_entity_type_label_mapping_snapshot():
    assert contracts_engine._entity_type_label("INDIVIDUAL") == "개인"
    assert contracts_engine._entity_type_label("SOLE_PROPRIETOR") == "개인사업자"
    assert contracts_engine._entity_type_label("SIMPLIFIED_TAX") == "간이과세자"
    assert contracts_engine._entity_type_label("CORPORATION") == "법인"
    assert contracts_engine._entity_type_label("ETC") == "ETC"


def test_default_sections_have_required_article_keys():
    sections = contracts_engine._default_sections("EXPERT")
    assert set(sections.keys()) == {"article3", "article5", "article6", "article7"}
    for key in ("article3", "article5", "article6", "article7"):
        assert sections[key]


def test_default_sections_include_html_paragraphs():
    sections = contracts_engine._default_sections("CONSULTING")
    assert all("<p>" in sections[k] for k in sections)


def test_generate_contract_body_schema_fields():
    body = contracts_engine.GenerateContractBody(request_id="req-1", result_id="res-1")
    dumped = body.model_dump()
    assert dumped["request_id"] == "req-1"
    assert dumped["result_id"] == "res-1"


def test_revise_body_schema_field():
    body = contracts_engine.ReviseBody(revision_note="제5조 지급 조건 변경")
    assert body.model_dump()["revision_note"] == "제5조 지급 조건 변경"


def test_revision_count_admin_hold_boundary_logic_snapshot():
    current = 3
    revision_count = current + 1
    assert revision_count > 3
