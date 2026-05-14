"""SaaS Core — 인증, 사용자, 회사, 사업장 등 필수 라우터.

이 그룹 실패 시 서비스 의미 없음. 최우선 로드.
"""
ROUTERS = [
    {"module": "routers.auth"},
    {"module": "routers.auth_oauth"},
    {"module": "routers.pw_reset"},
    {"module": "routers.users"},
    {"module": "routers.companies"},
    {"module": "routers.factories"},
    {"module": "routers.system_codes"},
    {"module": "routers.contacts"},
    {"module": "routers.roles"},
    {"module": "routers.teams"},
    {"module": "routers.areas"},
    {"module": "routers.buildings"},
    {"module": "routers.notifications"},
    {"module": "routers.feature_flags"},
    {"module": "routers.health"},
    {"module": "routers.alert_messages"},
    {"module": "routers.factory_process_v3"},
    {"module": "routers.process_management"},
    {"module": "routers.ksic_engine"},
    {"module": "routers.posts"},
    {"module": "routers.workers"},
]
