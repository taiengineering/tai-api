"""FORM647 검색 어댑터 — 기존 안전관리서식 검색에 647종 연결.

WO-TAI-FORM647-EXISTING-LIBRARY-INTEGRATION-001

Source of truth: LEG `form647_review.form_snapshots`
  - service_sot_gate = 'BLOCKED' (DB CHECK 강제) → Gate OPEN 전 0건 반환
  - Gate OPEN 후 `service_sot_gate` ∈ _GATE_OPEN_VALUES 행만 인덱싱

검색 결과 형식: 기존 `REFERENCE_FORM` object_type 재사용.
  - `canonical_id` = `f647-{ek}` — 기존 138종 UUID와 충돌 없음.
  - `source_id` = `FORM647` — 기존 `TAI_REFERENCE_FORM`과 구분.
  - `public_url` = `/reference-form/f647-{ek}` — 기존 상세 화면 재사용.

ek 타입: form_snapshots.ek 는 text 컬럼이므로 str(ek) 로 조회.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP, as_str_list, expected_hashes_from_documents, first_present_iso,
)

# form_snapshots.service_sot_gate 에서 허용하는 Gate 개방 값
# 현재 DB CHECK = 'BLOCKED' 로 강제되므로 실제 해당하는 값 없음
_GATE_OPEN_VALUES = frozenset({"APPROVED", "OPEN", "RELEASED"})

_CHUNK = 200


Fetcher = Callable[[], Iterable[dict]]


class Form647SearchAdapter:
    """FORM647 647종을 기존 REFERENCE_FORM 검색 결과로 제공하는 어댑터.

    LEG client 가 None 이면 fail-closed (0건 반환). 예외 발생 없음.
    Gate BLOCKED 시 0건 반환 — 기존 138종에 영향 없음.
    """

    domain_name = "FORM647"
    object_type = "REFERENCE_FORM"

    def __init__(self, *, fetch_current: Fetcher):
        self._fetch_current = fetch_current

    def iter_documents(self) -> Iterator[dict]:
        for row in self._fetch_current():
            payload = _normalize(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        return None   # 단건 재인덱스는 Gate 해제 후 별도 구현


def _normalize(row: dict) -> Optional[dict]:
    ek = row.get("ek")
    frozen_name = row.get("frozen_name")
    api_target = row.get("api_target")
    service_sot_gate = row.get("service_sot_gate", "BLOCKED")

    if not ek or not frozen_name or not api_target:
        return None
    if service_sot_gate not in _GATE_OPEN_VALUES:
        return None

    canonical_id = f"f647-{ek}"
    description = "법령별 서식" if api_target == "licbyl" else "행정규칙별 서식"

    ts = first_present_iso(row.get("created_at"))
    if ts is MISSING_TIMESTAMP:
        return None

    search_text = " ".join(as_str_list([frozen_name, description]))

    return {
        "object_type": Form647SearchAdapter.object_type,
        "canonical_id": canonical_id,
        "source_id": "FORM647",
        "source_key": canonical_id,
        "title": str(frozen_name),
        "summary": description,
        "search_text": search_text,
        "aliases": [],
        "keywords": [],
        "subjects": [],
        "context": [],
        "public_url": f"/reference-form/{canonical_id}",
        "saas_url": None,
        "publication_status": "PUBLISHED",
        "visibility_scopes": ["PUBLIC"],
        "source_updated_at": ts,
    }
