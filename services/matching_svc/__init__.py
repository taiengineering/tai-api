"""매칭 서비스 패키지 — 라우터는 `import services.matching_svc as ms` 유지."""
from db.supabase_client import get_supabase as _health_get_supabase
from services.health_registry import register_probe
from .dashboard import get_dashboard_stats, get_pipeline
from .errors import MatchingSvcError
from .request import (
    admin_stats_simple,
    calc_commission,
    create_matching_request,
    get_request_detail,
    list_my_requests,
    list_requests_admin,
    update_request_status,
)
from .results import (
    create_match_result_record,
    list_proposals_data,
    mark_result_viewed,
    my_proposals_list,
    notify_expert_for_result,
    select_expert_result,
    submit_proposal_for_result,
)

__all__ = [
    "MatchingSvcError",
    "calc_commission",
    "create_matching_request",
    "list_my_requests",
    "list_requests_admin",
    "get_request_detail",
    "update_request_status",
    "admin_stats_simple",
    "create_match_result_record",
    "notify_expert_for_result",
    "mark_result_viewed",
    "submit_proposal_for_result",
    "list_proposals_data",
    "select_expert_result",
    "my_proposals_list",
    "get_dashboard_stats",
    "get_pipeline",
]


async def _probe_matching():
    sb = _health_get_supabase()
    r = sb.table("fix_chat_sessions").select("id", count="exact").limit(1).execute()
    return {"sessions_count": r.count or 0}


register_probe(
    "matching",
    _probe_matching,
    critical=False,
    desc_ko="전문가 매칭",
    meta={
        "impacts": [{"name": "전문가 매칭", "page": "safe > 연결 서비스 > 전문가 매칭"}],
        "fix_links": [{"name": "Supabase DB", "url": "https://supabase.com/dashboard/project/vwlahtguyggrhvslabax"}],
        "api": "POST /fix/chat/start",
        "code": "services/matching_svc/__init__.py",
    },
)
