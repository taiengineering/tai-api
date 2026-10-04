"""KECO 화학물질 canonical content hash. SHA-256 기반."""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from services.keco_chemical.parse import KecoChemicalItem, KecoRegulatoryFact


def _fact_sort_key(fact: KecoRegulatoryFact) -> tuple:
    """Semantic ordering key — typeList 배열 순서 변경에도 동일 hash 보장."""
    return (
        fact.sbstn_clsf_type_nm or "",
        fact.unq_no or "",
        fact.ancmnt_ymd or "",
        fact.cont_info or "",
    )


def type_list_canonical(facts: list[KecoRegulatoryFact]) -> list[dict]:
    """typeList를 semantic tuple 기준 deterministic ordering으로 정렬한 dict 목록 반환."""
    sorted_facts = sorted(facts, key=_fact_sort_key)
    return [
        {
            "sbstn_clsf_type_nm": f.sbstn_clsf_type_nm,
            "unq_no": f.unq_no,
            "cont_info": f.cont_info,
            "excp_info": f.excp_info,
            "ancmnt_ymd": f.ancmnt_ymd,
            "ancmnt_info": f.ancmnt_info,
        }
        for f in sorted_facts
    ]


def chemical_content_hash(item: KecoChemicalItem) -> str:
    """단일 화학물질 항목의 deterministic canonical hash.

    - typeList 배열 순서가 바뀌어도 동일 hash
    - sort_keys=True JSON serialization
    - raw payload와 별도 (raw는 원본 순서 유지)
    """
    canonical = {
        "sbstn_id": item.sbstn_id,
        "cas_no": item.cas_no,
        "korexst_raw": item.korexst_raw,
        "sbstn_nm_kor": item.sbstn_nm_kor,
        "sbstn_nm_eng": item.sbstn_nm_eng,
        "sbstn_nm2_kor": item.sbstn_nm2_kor,
        "sbstn_nm2_eng": item.sbstn_nm2_eng,
        "mlcfrm": item.mlcfrm,
        "mlcwgt": item.mlcwgt,
        "type_list": type_list_canonical(item.type_list),
    }
    text = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def regulatory_fact_hash(fact: KecoRegulatoryFact) -> str:
    """단일 규제 사실 항목의 content hash."""
    canonical = {
        "ancmnt_info": fact.ancmnt_info,
        "ancmnt_ymd": fact.ancmnt_ymd,
        "cont_info": fact.cont_info,
        "excp_info": fact.excp_info,
        "sbstn_clsf_type_nm": fact.sbstn_clsf_type_nm,
        "unq_no": fact.unq_no,
    }
    text = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
