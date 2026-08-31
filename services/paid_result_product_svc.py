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
         +-- paid_result_materials_v1 ──┐
                                        v
                    build_paid_result_evidence_v1(materials, loader)
                                        |            ← DB READ (2 roundtrip)
                                        v
                              paid_result_evidence_v1
                                        |
                                        v
                       FINAL INTERNAL PRODUCT PAYLOAD (5 keys)

WHY A SEPARATE LAYER
    build_paid_result_contract_v1() 안에 Supabase 조회를 넣지 않는다.
    그 함수가 지금 갖고 있는 세 가지 성질 — 순수 함수 · 저장된 결과의
    결정적 변환 · Materializer 에 대한 정확한 위임 — 이 그것 하나로 무너진다.
    같은 row 를 넣으면 언제나 같은 계약이 나온다는 보장이 사라지고,
    테스트가 DB 를 필요로 하게 되며, 실패 모드가 뒤섞인다.

    그래서 DB 에 의존하는 evidence 부착은 계약이 아니라 조립의 책임이다.
    이 모듈이 생긴 뒤에도 build_paid_result_contract_v1 은 손대지 않았다.

WHAT IT DOES NOT DO
    · Materializer 재실행 = 0.
      evidence 의 입력은 반드시 contract["paid_result_materials_v1"] 이며,
      row["full_result"] 를 resolver 가 다시 독자적으로 해석하지 않는다.
      한 payload 안에 서로 다른 두 번의 집계 결과가 섞이지 않게 하기 위해서다.
    · 입력 mutation = 0. row 도, contract 도 바꾸지 않는다.
    · 새 파생 필드 = 0. 두 산출물을 합치기만 한다.
    · contract_version bump = 0. 이번 것은 미공개 additive internal assembly 다.

ERROR BEHAVIOR
    조문 하나가 안 풀리는 것과 DB 가 죽은 것은 다른 사건이다.

        조문 resolution 실패   -> evidence["unresolved"] 에 남고 payload 는 정상
        DB / loader exception -> 그대로 위로 던진다

    후자를 삼켜서 "조문이 원래 없었던 것처럼" 성공 payload 를 돌려주지 않는다.
    그건 고객에게 조용히 거짓을 말하는 것이다. public runtime 에서 이 예외를
    어떻게 보여줄지는 public wiring 단계에서 따로 정한다.

경계 (STEP4C-2 PKG-2C 작업지시)
    ROUTER = 0 · PUBLIC ENDPOINT = 0 · PAID RESULT ROUTE = 0
    DB MUTATION = 0 · migration = 0 · requirements = 0
    paid_result_contract_svc.py / paid_result_evidence_svc.py /
    paid_result_materializer.py 변경 = 0
    판례 = 0 · law.go.kr URL = 0  (근거가 생기기 전까지 HOLD)
    아직 고객은 이 payload 를 받을 수 없다. tai-www 연결은 PKG-2D 다.

PUBLIC RELEASE REPRODUCIBILITY GATE = OPEN
    evidence 는 live public.law_article 을 읽어 만들어진다. snapshot 을
    저장하지 않으므로 법령 데이터가 바뀌면 같은 진단의 조문이 달라질 수 있다.
    assembler 가 생겼다고 이 gate 가 닫히지 않는다.
"""

from __future__ import annotations

from typing import Any, Dict

from services.paid_result_contract_svc import build_paid_result_contract_v1
from services.paid_result_evidence_svc import build_paid_result_evidence_v1

#: payload 안에서 evidence 가 놓이는 자리. 기존 4키 뒤에 붙는 다섯 번째다.
EVIDENCE_KEY = "paid_result_evidence_v1"

#: evidence 의 입력이 되는 계약 안의 자리. row["full_result"] 가 아니다.
MATERIALS_KEY = "paid_result_materials_v1"


def build_paid_result_product_v1(row: Any, evidence_loader: Any = None) -> Dict[str, Any]:
    """저장된 진단 row -> 내부 상품 payload (contract 4키 + evidence 1키).

    Args:
        row: build_paid_result_contract_v1 이 받는 것과 같은 저장 row.
        evidence_loader: law_master / law_article batch loader. 주입하지 않으면
            resolver 가 SupabaseArticleLoader 를 만든다. 테스트는 항상 주입한다.

    Returns:
        새 dict. contract 의 4키는 값 그대로 옮기고 evidence 1키를 더한다.

    Raises:
        loader 가 던지는 모든 예외를 그대로 전파한다. 여기서 잡지 않는다.
    """
    contract = build_paid_result_contract_v1(row)

    # evidence 의 입력은 계약이 이미 만든 materials 하나뿐이다.
    # row["full_result"] 를 다시 열지 않는다 — Materializer 를 두 번 돌리면
    # 한 payload 안에 서로 다른 집계가 섞일 수 있다.
    materials = contract.get(MATERIALS_KEY)

    # try/except 를 두지 않는다. DB 실패는 결과가 비는 사건이 아니라
    # 결과를 만들지 못한 사건이므로 호출자가 알아야 한다.
    evidence = build_paid_result_evidence_v1(materials, loader=evidence_loader)

    # 얕은 병합. contract 의 값들을 복제하지 않고 그대로 옮긴다 —
    # 이 모듈도, resolver 도 그 값을 바꾸지 않으므로 복제할 이유가 없고,
    # 복제하면 "계약 그대로"인지 확인하기만 더 어려워진다.
    product = dict(contract)
    product[EVIDENCE_KEY] = evidence
    return product


__all__ = [
    "EVIDENCE_KEY",
    "MATERIALS_KEY",
    "build_paid_result_product_v1",
]
