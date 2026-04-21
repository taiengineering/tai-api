from services import contract_helpers as h


def test_now_iso_has_utc_offset():
    now = h._now_iso()
    assert "T" in now
    assert now.endswith("+00:00")


def test_expert_type_label_mapping_snapshot():
    assert h._expert_type_label("EXPERT") == "선임대행"
    assert h._expert_type_label("CONSULTING") == "컨설팅"
    assert h._expert_type_label("UNKNOWN") == "UNKNOWN"


def test_entity_type_label_mapping_snapshot():
    assert h._entity_type_label("INDIVIDUAL") == "개인"
    assert h._entity_type_label("CORPORATION") == "법인"
    assert h._entity_type_label("UNKNOWN") == "UNKNOWN"


def test_default_sections_structure_snapshot():
    sections = h._default_sections("EXPERT")
    assert set(sections.keys()) == {"article3", "article5", "article6", "article7"}
    assert sections["article3"].startswith("<p>")
