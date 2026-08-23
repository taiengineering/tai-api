"""
WP-DOCUMENT-ARCH-05A — Schema-based deterministic renderer (confirm 봉인용).

목적: confirm 시점의 working state 를 **원본 재조회 없이** 그대로 재현 가능한
canonical HTML 로 봉인한다. 사람이 보기 좋은 문서가 아니라 **증거 보존용 render** 다.

계약:
  INPUT   = runtime_document_data + runtime_form_schema + runtime_field + runtime_checklist_item
            (호출자가 조회해서 넘긴다. 이 모듈은 DB 를 건드리지 않는다.)
  OUTPUT  = rendered_body / template_identity / source_trace_snapshot / evidence_manifest
  PURE    = DB 접근 없음 · 현재시각 없음 · 난수 없음 · URL/hostname 없음 · locale 의존 없음
  DETERMINISTIC = 같은 schema + 같은 runtime data + 같은 renderer version
                  → byte-for-byte 동일 HTML
  LOSSLESS      = runtime_data_json 의 어떤 key 도 조용히 버리지 않는다.
                  schema 에 없는 key 는 "unmapped values" 영역에 결정적 순서로 반드시 포함.
  MISSING != OMITTED = schema field 에 값이 없으면 빈칸이 아니라 "미입력" 으로 명시 표기.

금지:
  auto fill (default_value 를 값처럼 렌더하지 않는다)
  원본 source DB 재조회 · doc_type 이름 추론 · registry semantic matching
  PDF 생성 · archive INSERT · approval · status seal (전부 이 모듈 범위 밖)

hash domain:
  여기서 계산하는 schema_structure_hash 는 confirmed snapshot hash(Q4)와 **별개 도메인**이다.
  services/document_snapshot_integrity.py 와 합치지 않는다.
"""

from __future__ import annotations

import hashlib
import html
import json
from typing import Any, Dict, List, Tuple

__all__ = [
    "RENDERER_VERSION",
    "build_render_artifacts",
    "SchemaRenderError",
]

# 렌더 결과 형식이 바뀌면 반드시 올린다. template_identity 에 포함된다.
RENDERER_VERSION = "1"

# 값이 없을 때 쓰는 명시 표기. 빈칸(omitted)과 구분된다.
_MISSING_TEXT = "(미입력)"


class SchemaRenderError(Exception):
    """렌더 입력 계약 위반. FAIL-CLOSED — confirm 을 중단시킨다."""


def _fail(msg: str) -> "SchemaRenderError":
    return SchemaRenderError(msg)


# ─────────────────────────────────────────────────────────────────────────
# 값 표현 — JSON-native 만 허용 (Q4 hash 입력과 타입 체계를 맞춘다)
# ─────────────────────────────────────────────────────────────────────────

def _assert_json_native(value: Any, _path: str) -> None:
    """nested depth 까지 JSON-native 만 허용 (Q4 와 동일한 타입 경계).

    json.dumps 는 tuple 을 list 처럼 직렬화하므로 그대로 두면 05A 가 Q4 보다 느슨해진다.
    산출물이 Q4 hash 로 그대로 넘어가는 계약이므로 렌더 단계에서도 같은 경계를 강제한다.
    """
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise _fail("non-finite float at %s" % _path)
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise _fail("non-string dict key %s at %s" % (type(k).__name__, _path))
            _assert_json_native(v, "%s.%s" % (_path, k))
        return
    if isinstance(value, list):
        for i, v in enumerate(value):
            _assert_json_native(v, "%s[%d]" % (_path, i))
        return
    raise _fail(
        "non-JSON-native type %s at %s (runtime_data_json 은 "
        "null/bool/int/float/str/list/dict 만 허용)" % (type(value).__name__, _path)
    )


def _value_to_text(value: Any, _path: str) -> str:
    """runtime 값을 결정적 문자열로. scalar 는 그대로, 구조는 canonical JSON."""
    _assert_json_native(value, _path)
    if value is None:
        return _MISSING_TEXT
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    # dict / list — 여기 오면 이미 nested 까지 JSON-native 임이 보장된다.
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    )


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


# ─────────────────────────────────────────────────────────────────────────
# 순서 — 결정적 정렬 (order NULL / 동률에도 흔들리지 않게 id 로 tie-break)
# ─────────────────────────────────────────────────────────────────────────

def _order_key(row: Dict[str, Any], order_field: str) -> Tuple[int, int, str]:
    raw = row.get(order_field)
    if raw is None:
        return (1, 0, str(row.get("id") or ""))          # order 없는 행은 뒤로
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise _fail("%s must be int or None" % order_field)
    return (0, raw, str(row.get("id") or ""))


def _require_str(row: Dict[str, Any], key: str, where: str) -> str:
    val = row.get(key)
    if not isinstance(val, str) or val == "":
        raise _fail("%s.%s must be a non-empty str" % (where, key))
    return val


# ─────────────────────────────────────────────────────────────────────────
# template_identity — 렌더에 영향을 주는 schema 속성만 hash 한다
# ─────────────────────────────────────────────────────────────────────────

def _schema_structure(
    schema: Dict[str, Any],
    fields: List[Dict[str, Any]],
    checklists: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """HTML 생성에 실제로 쓰이는 속성만 모은다.

    created_at/updated_at/status/source_trace/candidate_id 등 저장·계보 메타는 제외.
    렌더러가 소비하지 않는 default_value/validation_rule/placeholder 도 제외한다
    (렌더 결과를 바꾸지 않는 변경이 identity 를 흔들면 안 된다).
    """
    return {
        "form_schema_id": str(schema.get("id") or ""),
        "form_name": schema.get("form_name"),   # <title>/<h1> 에 렌더됨 → 반드시 포함
        "fields": [
            {
                "id": str(f.get("id") or ""),
                "field_key": f.get("field_key"),      # None 가능 — 값 매핑 불가 필드
                "field_label": f.get("field_label"),
                "input_type": f.get("input_type"),
                "field_order": f.get("field_order"),
            }
            for f in fields
        ],
        "checklists": [
            {
                "id": str(c.get("id") or ""),
                "raw_text": c.get("raw_text"),
                "input_type": c.get("input_type"),
                "item_order": c.get("item_order"),
            }
            for c in checklists
        ],
    }


def _structure_hash(structure: Dict[str, Any]) -> str:
    payload = json.dumps(
        structure, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _template_identity(structure: Dict[str, Any]) -> str:
    return "schema-renderer:%s:sha256:%s" % (
        RENDERER_VERSION, _structure_hash(structure)
    )


# ─────────────────────────────────────────────────────────────────────────
# 렌더
# ─────────────────────────────────────────────────────────────────────────

def _render_rows(
    fields: List[Dict[str, Any]],
    data: Dict[str, Any],
    consumed: set,
) -> List[str]:
    out: List[str] = []
    for f in fields:
        fid = str(f.get("id") or "")
        label = _require_str(f, "field_label", "runtime_field")
        input_type = _require_str(f, "input_type", "runtime_field")
        key = f.get("field_key")
        if key is not None and not isinstance(key, str):
            raise _fail("runtime_field.field_key must be str or None")

        if key is None:
            # 값 조회 키가 없는 필드 — 값을 추측하지 않는다(auto fill 금지).
            state, text = "unmappable", _MISSING_TEXT
        elif key in data:
            consumed.add(key)
            raw = data[key]
            if raw is None or raw == "":
                state, text = "missing", _MISSING_TEXT
            else:
                state, text = "present", _value_to_text(raw, "runtime_data_json.%s" % key)
        else:
            state, text = "missing", _MISSING_TEXT

        out.append(
            '<tr data-field-id="%s" data-field-key="%s" data-input-type="%s" data-state="%s">'
            "<th>%s</th><td>%s</td></tr>"
            % (
                _esc(fid),
                _esc(key) if key is not None else "",
                _esc(input_type),
                state,
                _esc(label),
                _esc(text),
            )
        )
    return out


def _render_checklists(
    checklists: List[Dict[str, Any]],
    data: Dict[str, Any],
    consumed: set,
) -> List[str]:
    out: List[str] = []
    for c in checklists:
        cid = str(c.get("id") or "")
        text = _require_str(c, "raw_text", "runtime_checklist_item")
        input_type = _require_str(c, "input_type", "runtime_checklist_item")
        # 응답은 checklist item id 를 key 로 저장된 값만 인정한다(추론 금지).
        if cid in data:
            consumed.add(cid)
            raw = data[cid]
            if raw is None or raw == "":
                state, resp = "missing", _MISSING_TEXT
            else:
                state, resp = "present", _value_to_text(raw, "runtime_data_json.%s" % cid)
        else:
            state, resp = "missing", _MISSING_TEXT
        out.append(
            '<tr data-item-id="%s" data-input-type="%s" data-state="%s">'
            "<td>%s</td><td>%s</td></tr>"
            % (_esc(cid), _esc(input_type), state, _esc(text), _esc(resp))
        )
    return out


def _render_unmapped(data: Dict[str, Any], consumed: set) -> List[str]:
    """schema 에 매핑되지 않은 working 값 — 절대 버리지 않는다(lossless)."""
    leftovers = sorted(k for k in data.keys() if k not in consumed)
    return [
        '<tr data-key="%s"><th>%s</th><td>%s</td></tr>'
        % (
            _esc(k),
            _esc(k),
            _esc(_value_to_text(data[k], "runtime_data_json.%s" % k)),
        )
        for k in leftovers
    ]


def build_render_artifacts(
    *,
    document: Dict[str, Any],
    schema: Dict[str, Any],
    fields: List[Dict[str, Any]],
    checklists: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """confirm 봉인에 필요한 렌더 산출물을 만든다(순수 함수).

    반환:
        rendered_body           결정적 HTML 문자열
        template_identity       schema-renderer:<ver>:sha256:<schema_structure_hash>
        source_trace_snapshot   UNKNOWN 1-element (provenance 미완성의 명시적 봉인)
        evidence_manifest       [] (실제 sealed evidence 없음 — 가짜 생성 금지)
    """
    if not isinstance(document, dict) or not isinstance(schema, dict):
        raise _fail("document/schema must be dict")
    if not isinstance(fields, list) or not isinstance(checklists, list):
        raise _fail("fields/checklists must be list")

    doc_id = str(document.get("id") or "")
    if not doc_id:
        raise _fail("document.id required")
    schema_id = str(schema.get("id") or "")
    if not schema_id:
        raise _fail("schema.id required")
    if str(document.get("form_schema_id") or "") != schema_id:
        raise _fail("schema does not belong to this document")

    version = document.get("version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)      # bool 은 int 의 subclass
        or version < 1
    ):
        raise _fail("document.version must be int >= 1")
    # 이후로는 검증된 version 하나만 사용한다.
    # "1"(str) 과 1(int) 은 rendered_body 에서 구분되지 않지만 source_trace 에서는
    # 타입이 갈려 Q4 hash 가 달라진다. ARCH-02/Q4 계약(int>=1)을 여기서 조기 강제한다.

    data = document.get("runtime_data_json")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise _fail("runtime_data_json must be an object")
    for k in data:
        if not isinstance(k, str):
            raise _fail("runtime_data_json keys must be str")

    for f in fields:
        if str(f.get("form_schema_id") or "") != schema_id:
            raise _fail("runtime_field belongs to another schema")
    for c in checklists:
        if str(c.get("form_schema_id") or "") != schema_id:
            raise _fail("runtime_checklist_item belongs to another schema")

    ordered_fields = sorted(fields, key=lambda r: _order_key(r, "field_order"))
    ordered_checks = sorted(checklists, key=lambda r: _order_key(r, "item_order"))

    consumed: set = set()
    field_rows = _render_rows(ordered_fields, data, consumed)
    check_rows = _render_checklists(ordered_checks, data, consumed)
    unmapped_rows = _render_unmapped(data, consumed)

    form_name = schema.get("form_name")
    parts: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="ko"><head><meta charset="utf-8">',
        "<title>%s</title>" % _esc(form_name if isinstance(form_name, str) else ""),
        "</head><body>",
        '<section class="doc-identity">',
        '<h1 class="form-name">%s</h1>'
        % _esc(form_name if isinstance(form_name, str) else ""),
        '<dl><dt>runtime_document_id</dt><dd>%s</dd>' % _esc(doc_id),
        "<dt>form_schema_id</dt><dd>%s</dd>" % _esc(schema_id),
        "<dt>document_version</dt><dd>%s</dd></dl>" % _esc(str(version)),
        "</section>",
        '<section class="fields"><table>%s</table></section>' % "".join(field_rows),
        '<section class="checklist"><table>%s</table></section>' % "".join(check_rows),
        '<section class="unmapped-values"><table>%s</table></section>'
        % "".join(unmapped_rows),
        "</body></html>",
    ]
    rendered_body = "".join(parts)

    structure = _schema_structure(schema, ordered_fields, ordered_checks)

    source_trace_snapshot = [
        {
            "source_type": "runtime_document_data",
            "source_id": doc_id,
            "entity": "runtime_document_data",
            "source_version": version,
            "captured_values": "runtime_data_json",
            "legal_ref": None,
            "provenance": "UNKNOWN",
            "reason": "provenance pipeline 미완성 — 확정 시점의 working state 만 봉인",
        }
    ]

    return {
        "rendered_body": rendered_body,
        "template_identity": _template_identity(structure),
        "source_trace_snapshot": source_trace_snapshot,
        "evidence_manifest": [],
    }
