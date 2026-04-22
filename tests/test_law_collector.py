"""law_collector XML 파싱·force 삭제 관련 단위 테스트."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from routers.law_collector import (
    delete_law_version_cascade_for_recollect,
    parse_law_content_xml,
)


def _generic_version_dep_mock() -> MagicMock:
    m = MagicMock()
    m.delete.return_value.eq.return_value.execute.return_value = MagicMock()
    m.update.return_value.eq.return_value.execute.return_value = MagicMock()
    return m


SAMPLE_XML_CLEAN = """<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <기본정보>
    <법령ID>TEST001</법령ID>
    <공포일자>20260101</공포일자>
    <공포번호>1</공포번호>
    <법령명_한글>테스트법</법령명_한글>
    <법종구분>법률</법종구분>
    <시행일자>20260101</시행일자>
    <제개정구분>제정</제개정구분>
  </기본정보>
  <조문>
    <조문단위 조문키="제1조">
      <조문번호>1</조문번호>
      <조문제목>목적</조문제목>
      <조문내용>이 법은 테스트를 위한다.</조문내용>
    </조문단위>
    <조문단위 조문키="제2조">
      <조문번호>2</조문번호>
      <조문제목>정의</조문제목>
      <조문내용>용어의 뜻은 다음과 같다.</조문내용>
    </조문단위>
  </조문>
</법령>"""


SAMPLE_XML_NESTED = """<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <기본정보>
    <법령ID>TEST002</법령ID>
    <공포일자>20260101</공포일자>
    <공포번호>1</공포번호>
    <법령명_한글>테스트법2</법령명_한글>
    <법종구분>법률</법종구분>
    <시행일자>20260101</시행일자>
    <제개정구분>제정</제개정구분>
  </기본정보>
  <조문>
    <조문단위 조문키="제1조">
      <조문번호>1</조문번호>
      <조문제목>목적</조문제목>
      <조문내용>이 법은 「제2조」에 따라...</조문내용>
      <항>
        <항번호>①</항번호>
        <항내용>파편 본문</항내용>
        <조문단위><조문번호>1</조문번호><조문내용>중첩 파편</조문내용></조문단위>
      </항>
    </조문단위>
  </조문>
</법령>"""


SAMPLE_DUP_KEYS = """<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <기본정보>
    <법령ID>TEST003</법령ID>
    <공포일자>20260101</공포일자>
    <공포번호>1</공포번호>
    <법령명_한글>중복키법</법령명_한글>
    <법종구분>법률</법종구분>
    <시행일자>20260101</시행일자>
    <제개정구분>제정</제개정구분>
  </기본정보>
  <조문>
    <조문단위 조문키="K001">
      <조문번호>1</조문번호>
      <조문제목></조문제목>
      <조문내용>짧음</조문내용>
    </조문단위>
    <조문단위 조문키="K001">
      <조문번호>1</조문번호>
      <조문제목>완전</조문제목>
      <조문내용>완전한 긴 내용입니다AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA</조문내용>
    </조문단위>
  </조문>
</법령>"""


SAMPLE_HANG_HO_MOK = """<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <기본정보>
    <법령ID>TEST004</법령ID>
    <공포일자>20260101</공포일자>
    <공포번호>1</공포번호>
    <법령명_한글>항호목법</법령명_한글>
    <법종구분>법률</법종구분>
    <시행일자>20260101</시행일자>
    <제개정구분>제정</제개정구분>
  </기본정보>
  <조문>
    <조문단위 조문키="제1조">
      <조문번호>1</조문번호>
      <조문제목>시험</조문제목>
      <조문내용>머리글입니다.</조문내용>
      <항>
        <항번호>①</항번호>
        <항내용>항본문A</항내용>
        <호>
          <호번호>1.</호번호>
          <호내용>호내용1</호내용>
          <목><목번호>가.</목번호><목내용>목가</목내용></목>
          <목><목번호>나.</목번호><목내용>목나</목내용></목>
        </호>
        <호>
          <호번호>2.</호번호>
          <호내용>호내용2</호내용>
        </호>
      </항>
    </조문단위>
  </조문>
</법령>"""


def test_parse_clean_xml_returns_correct_count():
    result = parse_law_content_xml(SAMPLE_XML_CLEAN)
    assert len(result["articles"]) == 2


def test_parse_nested_xml_deduplicates():
    """./조문/조문단위 만 보므로 항 안의 중첩 조문단위는 별도 조문으로 잡히지 않음."""
    result = parse_law_content_xml(SAMPLE_XML_NESTED)
    assert len(result["articles"]) == 1
    assert result["articles"][0]["article_title"] == "목적"


def test_parse_keeps_more_complete_version():
    result = parse_law_content_xml(SAMPLE_DUP_KEYS)
    assert len(result["articles"]) == 1
    assert result["articles"][0]["article_title"] == "완전"


def test_article_text_includes_hang_ho_mok_content():
    result = parse_law_content_xml(SAMPLE_HANG_HO_MOK)
    text = result["articles"][0]["article_text"]
    assert "머리글입니다." in text
    assert "[①]" in text or "①" in text
    assert "항본문A" in text
    assert "호내용1" in text
    assert "호내용2" in text
    assert "목가" in text
    assert "목나" in text


def test_parse_sanbohoeonbeop_sample_if_present():
    p = Path(__file__).resolve().parent.parent / "scripts" / "debug" / "sanbohoeon_raw.xml"
    if not p.is_file():
        pytest.skip("sanbohoeon_raw.xml 없음 (scripts/debug/fetch_law_raw_xml.py 실행)")
    xml = p.read_text(encoding="utf-8")
    result = parse_law_content_xml(xml)
    keys = [a["article_internal_key"] for a in result["articles"]]
    assert len(keys) == len(set(keys))
    assert len(result["articles"]) >= 200


def test_force_recollect_deletes_existing_articles():
    """delete_law_version_cascade_for_recollect 가 하위 테이블 삭제 후 law_version 삭제를 호출한다."""
    del_exec = MagicMock()
    del_exec.execute.return_value = MagicMock()

    law_article = MagicMock()
    law_article.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "art-1"}])
    law_article.delete.return_value.eq.return_value = del_exec

    law_paragraph = MagicMock()
    law_paragraph.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[{"id": "par-1"}])
    law_paragraph.delete.return_value.in_.return_value = del_exec

    law_item = MagicMock()
    law_item.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
    law_item.delete.return_value.in_.return_value = del_exec
    law_item.delete.return_value.eq.return_value = del_exec

    law_content_raw = MagicMock()
    law_content_raw.delete.return_value.eq.return_value.execute.return_value = MagicMock()

    law_version = MagicMock()
    law_version.delete.return_value.eq.return_value.execute.return_value = MagicMock()

    law_rule_drafts = MagicMock()
    law_rule_drafts.update.return_value.in_.return_value = del_exec

    inspection_set_items = MagicMock()
    inspection_set_items.update.return_value.in_.return_value = del_exec

    tables = {
        "law_article": law_article,
        "law_paragraph": law_paragraph,
        "law_item": law_item,
        "law_content_raw": law_content_raw,
        "law_version": law_version,
        "law_rule_drafts": law_rule_drafts,
        "inspection_set_items": inspection_set_items,
        "law_parsing_result": _generic_version_dep_mock(),
        "law_attachment": _generic_version_dep_mock(),
        "law_update_tracking": _generic_version_dep_mock(),
        "law_article_diff": _generic_version_dep_mock(),
        "law_change_log": _generic_version_dep_mock(),
        "law_rule_source_map": _generic_version_dep_mock(),
    }
    sb = MagicMock()
    sb.table.side_effect = lambda name, *a, **k: tables[name]

    delete_law_version_cascade_for_recollect(sb, "ver-1")

    names = [c.args[0] for c in sb.table.call_args_list if c.args]
    assert "law_article" in names
    assert "law_paragraph" in names
    assert "law_version" in names
    assert "law_content_raw" in names
    assert "law_parsing_result" in names
    assert "law_attachment" in names


def test_delete_cascade_no_articles():
    law_article = MagicMock()
    law_article.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    law_content_raw = MagicMock()
    law_content_raw.delete.return_value.eq.return_value.execute.return_value = MagicMock()
    law_version = MagicMock()
    law_version.delete.return_value.eq.return_value.execute.return_value = MagicMock()
    tables = {
        "law_article": law_article,
        "law_content_raw": law_content_raw,
        "law_version": law_version,
        "law_parsing_result": _generic_version_dep_mock(),
        "law_attachment": _generic_version_dep_mock(),
        "law_update_tracking": _generic_version_dep_mock(),
        "law_article_diff": _generic_version_dep_mock(),
        "law_change_log": _generic_version_dep_mock(),
        "law_rule_source_map": _generic_version_dep_mock(),
    }
    sb = MagicMock()
    sb.table.side_effect = lambda name, *a, **k: tables[name]
    delete_law_version_cascade_for_recollect(sb, "ver-empty")
    assert law_version.delete.called


def test_cascade_delete_handles_law_parsing_result():
    law_parsing_result = MagicMock()
    law_parsing_result.delete.return_value.eq.return_value.execute.return_value = MagicMock()
    law_attachment = _generic_version_dep_mock()
    law_article = MagicMock()
    law_article.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    tables = {
        "law_article": law_article,
        "law_parsing_result": law_parsing_result,
        "law_attachment": law_attachment,
        "law_update_tracking": _generic_version_dep_mock(),
        "law_article_diff": _generic_version_dep_mock(),
        "law_change_log": _generic_version_dep_mock(),
        "law_rule_source_map": _generic_version_dep_mock(),
        "law_content_raw": _generic_version_dep_mock(),
        "law_version": _generic_version_dep_mock(),
    }
    sb = MagicMock()
    sb.table.side_effect = lambda name, *a, **k: tables[name]
    delete_law_version_cascade_for_recollect(sb, "vid-parsing")
    law_parsing_result.delete.assert_called()
    law_parsing_result.delete.return_value.eq.assert_called_with("law_version_id", "vid-parsing")


def test_cascade_delete_handles_law_attachment():
    law_attachment = MagicMock()
    law_attachment.delete.return_value.eq.return_value.execute.return_value = MagicMock()
    law_article = MagicMock()
    law_article.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    tables = {
        "law_article": law_article,
        "law_parsing_result": _generic_version_dep_mock(),
        "law_attachment": law_attachment,
        "law_update_tracking": _generic_version_dep_mock(),
        "law_article_diff": _generic_version_dep_mock(),
        "law_change_log": _generic_version_dep_mock(),
        "law_rule_source_map": _generic_version_dep_mock(),
        "law_content_raw": _generic_version_dep_mock(),
        "law_version": _generic_version_dep_mock(),
    }
    sb = MagicMock()
    sb.table.side_effect = lambda name, *a, **k: tables[name]
    delete_law_version_cascade_for_recollect(sb, "vid-attach")
    law_attachment.delete.assert_called()
    law_attachment.delete.return_value.eq.assert_called_with("law_version_id", "vid-attach")
