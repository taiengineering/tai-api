"""Payment — 결제·계약·정산 라우터."""
ROUTERS = [
    {"module": "routers.payment"},
    {"module": "routers.payment_test"},
    {"module": "routers.payment_ops"},
    {"module": "routers.payment_billing"},
    {"module": "routers.contracts"},
    {"module": "routers.contracts_engine", "prefix": "/matching/contracts", "tags": ["계약서"]},
    {"module": "routers.quotes"},
    {"module": "routers.price_setting"},
    {"module": "routers.product_pricing"},
    {"module": "routers.price_policy"},
    {"module": "routers.connection_commission"},
    {"module": "routers.settlements", "prefix": "/settlements", "tags": ["정산"]},
]
