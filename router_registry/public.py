"""Public — 마케팅/공개 라우터 (인증 불필요)."""
ROUTERS = [
    {"module": "routers.public"},
    {"module": "routers.site_public"},
    {"module": "routers.site_public", "attr": "admin_router"},
    {"module": "routers.public_admin"},
    {"module": "routers.public_pricing"},
    # WO-ISOLATE-001: 축3 익명진단 생성/조회/claim 격리.
    #   라이브(tai-www)는 /diagnosis/run(생성)·/diagnosis/result(조회)만 사용 → 축3 URL 미사용.
    #   파일 routers/anonymous_diagnosis.py 는 보존(anonymous_diagnosis_leg 가 _build_step1_body 등 import).
    #   부활 시 아래 한 줄 주석 해제.
    # {"module": "routers.anonymous_diagnosis"},
    {"module": "routers.anonymous_diagnosis_admin"},  # WO-ISOLATE-001: 관리자 조회 유지(tai-admin anon-diagnosis-list)
    {"module": "routers.connect_registration"},
    {"module": "routers.admin_connect"},
    {"module": "routers.admin_pricing"},
    {"module": "routers.internal_inbox"},
    {"module": "routers.admin_inquiries"},
    {"module": "routers.admin_audit"},  # P3-4 감사로그 조회 (GET /admin/audit-logs)
    {"module": "routers.inicis_auth"},
    {"module": "routers.safe_help"},  # safe 헬프센터 검색/조회/upsert (/help/*) — Phase2
    {"module": "routers.helpcenter"},  # help.taieng.co.kr 헬프센터 조회 (/helpcenter/*) — 서버 종결 게이팅
]
