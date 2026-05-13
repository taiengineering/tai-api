"""Public — 마케팅/공개 라우터 (인증 불필요)."""
ROUTERS = [
    {"module": "routers.public"},
    {"module": "routers.site_public"},
    {"module": "routers.site_public", "attr": "admin_router"},
    {"module": "routers.public_admin"},
    {"module": "routers.public_pricing"},
    {"module": "routers.anonymous_diagnosis"},
    {"module": "routers.connect_registration"},
    {"module": "routers.admin_connect"},
    {"module": "routers.admin_pricing"},
    {"module": "routers.internal_inbox"},
    {"module": "routers.admin_inquiries"},
]
