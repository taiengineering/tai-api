"""SaaS Core — 인증·사용자·회사·시설·기본설정 라우터."""
ROUTERS = [
    {"module": "routers.auth"},
    {"module": "routers.users"},
    {"module": "routers.companies"},
    {"module": "routers.factories"},
    {"module": "routers.system_codes"},
    {"module": "routers.file_upload"},
    {"module": "routers.notifications"},
    {"module": "routers.fcm"},
    {"module": "routers.onboarding"},
]
