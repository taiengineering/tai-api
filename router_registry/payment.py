"""Payment — 결제·계약·정산 라우터."""
ROUTERS = [
    {"module": "routers.payment"},
    {"module": "routers.payment_test"},
    {"module": "routers.payment_ops"},
    {"module": "routers.payment_ledger"},  # WO-7 환불/크레딧/증빙 결선 + 결제원장 조회
    {"module": "routers.payment_billing"},
    {"module": "routers.payment_plan_resolver"},  # GET /payments/plan-amount — 기존계약 SaaS 월요금(price_master SSOT)
    {"module": "routers.contracts"},
    # {"module": "routers.contracts_engine", "prefix": "/matching/contracts", "tags": ["계약서"]},  # ISOLATED 2026-08-20 (unlaunched 매칭계약)
    {"module": "routers.quotes"},
    {"module": "routers.price_setting"},
    {"module": "routers.price_master_admin"},
    # 2026-07-23 OBJ-C4: 정본=price_master 단일화. 아래 2개 레거시 가격 라우터 은퇴(프론트 소비처 0, 테이블 archive 격리).
    #   {"module": "routers.product_pricing"},   # /products/pricing — product_pricing 테이블(archive)
    #   {"module": "routers.price_policy"},      # /price-policy — price_policy 테이블(archive)
    # {"module": "routers.connection_commission"},  # ISOLATED 2026-08-20 (unlaunched 연결수수료)
    # {"module": "routers.settlements", "prefix": "/settlements", "tags": ["정산"]},  # ISOLATED 2026-08-20 (unlaunched 매칭정산)
]
