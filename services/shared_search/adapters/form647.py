"""FORM647 검색 어댑터 — 기존 안전관리서식 검색에 647종 연결.

WO-TAI-FORM647-EXISTING-LIBRARY-INTEGRATION-001

Source of truth: LEG `form647_review` 스키마
  - form_snapshots: ek, frozen_name, api_target, created_at (G2: run_id 포함)
  - service_gate.is_approved = true 가 고객 공개의 유일한 Gate
    (form_snapshots.service_sot_gate='BLOCKED' 불변 — 쿼리 대상 아님)

검색 결과 형식: 기존 `REFERENCE_FORM` object_type 재사용.
  - `canonical_id` = `f647-{ek}` — 기존 138종 UUID와 충돌 없음.
  - `source_id` = `FORM647` — 기존 `TAI_REFERENCE_FORM`과 구분.
  - `public_url` = `/reference-form/f647-{ek}` — 기존 상세 화면 재사용.

ek 타입: form_snapshots.ek 는 text 컬럼이므로 str(ek) 로 조회.
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    MISSING_TIMESTAMP, as_str_list, expected_hashes_from_documents, first_present_iso,
)


Fetcher = Callable[[], Iterable[dict]]
FetchById = Callable[[str], Optional[dict]]


class Form647SearchAdapter:
    """FORM647 647종을 기존 REFERENCE_FORM 검색 결과로 제공하는 어댑터.

    LEG client 가 None 이면 fail-closed (0건 반환). 예외 발생 없음.
    service_gate.is_approved=true 행만 인덱싱 — 기존 138종에 영향 없음.
    """

    domain_name = "FORM647"
    object_type = "REFERENCE_FORM"

    def __init__(
        self,
        *,
        fetch_current: Fetcher,
        fetch_by_id: Optional[FetchById] = None,
    ):
        self._fetch_current = fetch_current
        self._fetch_by_id = fetch_by_id or (lambda _: None)

    def iter_documents(self) -> Iterator[dict]:
        for row in self._fetch_current():
            payload = _normalize(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        """단건 재인덱스 — sync_object() 경유 철회 시 None 반환 → delete_document().

        G3: 반환 None → sync_object() → delete_document(refresh=False) → 'DELETE'.
            즉시 검색 반영 보장 없음 — 호출자가 별도 GET 404 확인 필요.
        """
        row = self._fetch_by_id(canonical_id)
        if row is None:
            return None
        return _normalize(row)


def _normalize(row: dict) -> Optional[dict]:
    ek = row.get("ek")
    frozen_name = row.get("frozen_name")
    api_target = row.get("api_target")

    if not ek or not frozen_name or not api_target:
        return None
    if row.get("is_approved") is not True:
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
