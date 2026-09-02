"""services/paid_result_product_svc.py — EVIDENCE PRODUCT ASSEMBLER v1

PAID-DIAGNOSIS-VALUE-REBUILD-01 · STEP4C-2 PKG-2C

WHAT THIS IS
    순수한 Product Contract 와 DB 를 읽는 Evidence Resolver 를 한 payload 로
    조립하는 층. 조립만 한다 — 파생도, 재집계도, 재해석도 하지 않는다.

        row
         |
         v
        build_paid_result_contract_v1(row)          ← 순수. DB 조회 0
         |
         +-- diagnosis
         +-- diagnosis_profile
         +-- paid_result_materials_v1 ──┬──────────────┐
                                        v              v
            build_paid_result_evidence_v1     build_paid_result_source_text_v1
                        |  ← DB READ              |  ← LEG Runtime HTTP (WO-05C)
                        v                         v
              paid_result_evidence_v1     paid_result_source_text_v1
                        |                         |
                        +────────────┬───────────+
                                     v
                    FINAL INTERNAL PRODUCT PAYLOAD (6 keys)

WHY A SEPARATE LAYER
    build_paid_result_contract_v1() 안에 Supabase 조회를 넣지 않는다.
    그 함수가 지금 갖고 있는 세 가지 성질 — 순수 함수 · 저장된 결과의
    결정적 변환 · Materializer 에 대한 정확한 위임 — 이 그것 하나로 무너진다.

WHAT IT DOES NOT DO
    · Materializer 재실행 = 0.
      evidence 와 source-text 의 입력은 반드시 contract["paid_result_materials_v1"] 이며,
      row["full_result"] 를 resolver 가 다시 독자적으로 해석하지 않는다.
    · 입력 mutation = 0. row 도, contract 도 바꾸지 않는다.
    · 새 파생 필드 = 0. 세 산출물을 합치기만 한다.
    · contract_version bump = 0. 이번 것은 미공개 additive internal assembly 다.

ERROR BEHAVIOR
    조문 하나가 안 풀리는 것과 DB/LEG Runtime 이 죽은 것은 다른 사건이다.

        조문 resolution 실패      -> evidence/source-text 의 unresolved 에 남고 payload 는 정상
        DB / loader / HTTP 예외   -> 그대로 위로 던진다

    후자를 삼켜서 "조문이 원래 없었던 것처럼" 성공 payload 를 돌려주지 않는다.
    LEG Runtime 실패 시 기존 duty.what 을 canonical source 로 위장하지도 않는다.

경계 (STEP4C-2 PKG-2C · WO-05C)
    ROUTER = 0 · PUBLIC ENDPOINT = 0 · PAID RESULT ROUTE = 0
    DB MUTATION = 0 · migration = 0 · requirements = 0
    paid_result_contract_svc.py / paid_result_evidence_svc.py /
    paid_result_materializer.py 변경 = 0 · LEG mutation = 0 · deploy = 0

PUBLIC RELEASE REPRODUCIBILITY GATE = OPEN
    paid_result_evidence_v1 은 live public.law_article 을 읽어 만들어진다.
    paid_result_source_text_v1 은 LIVE_LEG_SOURCE 로, LEG Runtime 이 live
    law_article_part.part_text 를 읽어 만든다. 두 산출물 모두 저장 진단에
    source snapshot / immutable binding 을 남기지 않는다.

    따라서 같은 저장 진단이라도 향후 법령 source 가 바뀌면 evidence /
    source-text 가 달라질 수 있다. assembler · source-text sidecar 구현이
    완료됐다고 해서 이 gate 가 닫히지 않는다.

    snapshot / immutability / reproducibility 해결은 별도 RELEASE GATE 에서
    수행한다. 이 gate 는 OPEN 상태를 유지한다.
"""

from __future__ import annotations

from typing import Any, Dict

from services.paid_result_contract_svc import build_paid_result_contract_v1
from services.paid_result_evidence_svc import build_paid_result_evidence_v1
from services.paid_result_source_text_svc import build_paid_result_source_text_v1

#: payload 안에서 evidence 가 놓이는 자리. 기존 4키 뒤에 붙는 다섯 번째다.
EVIDENCE_KEY = "paid_result_evidence_v1"

#: payload 안에서 source-text sidecar 가 놓이는 자리. 여섯 번째다(WO-05C).
SOURCE_TEXT_KEY = "paid_result_source_text_v1"

#: evidence / source-text 의 입력이 되는 계약 안의 자리. row["full_result"] 가 아니다.
MATERIALS_KEY = "paid_result_materials_v1"


def build_paid_result_product_v1(row: Any, evidence_loader: Any = None,
                                 source_text_loader: Any = None) -> Dict[str, Any]:
    """저장된 진단 row -> 내부 상품 payload (contract 4키 + evidence 1키 + source-text 1키).

    Args:
        row: build_paid_result_contract_v1 이 받는 것과 같은 저장 row.
        evidence_loader: law_master / law_article batch loader. 주입하지 않으면
            resolver 가 SupabaseArticleLoader 를 만든다. 테스트는 항상 주입한다.
        source_text_loader: atom_ids -> LEG source-text loader. 주입하지 않으면
            LEG Runtime client(fetch_source_texts)를 사용한다. 테스트는 항상 주입한다.

    Returns:
        새 dict. contract 의 4키는 값 그대로 옮기고 evidence·source-text 2키를 더한다.

    Raises:
        loader / HTTP 가 던지는 모든 예외를 그대로 전파한다. 여기서 잡지 않는다.
    """
    contract = build_paid_result_contract_v1(row)

    # evidence 와 source-text 의 입력은 계약이 이미 만든 materials 하나뿐이다.
    # row["full_result"] 를 다시 열지 않는다 — Materializer 를 두 번 돌리지 않는다.
    materials = contract.get(MATERIALS_KEY)

    # try/except 를 두지 않는다. DB/HTTP 실패는 결과가 비는 사건이 아니라
    # 결과를 만들지 못한 사건이므로 호출자가 알아야 한다.
    evidence = build_paid_result_evidence_v1(materials, loader=evidence_loader)
    source_text = build_paid_result_source_text_v1(materials, loader=source_text_loader)

    product = dict(contract)
    product[EVIDENCE_KEY] = evidence
    product[SOURCE_TEXT_KEY] = source_text
    return product


__all__ = [
    "EVIDENCE_KEY",
    "SOURCE_TEXT_KEY",
    "MATERIALS_KEY",
    "build_paid_result_product_v1",
]
