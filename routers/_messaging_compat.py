# routers/law_collector.py — import fix
# 기존: from routers.messaging import SMS_URL, _call_messageme, _get_cfg
# messaging.py v6.2.0에서 SMS_URL → EDGE_SMS_URL, _call_messageme → _call_edge_function 변경됨
# 하위호환 wrapper로 해결

from routers.messaging import EDGE_SMS_URL as SMS_URL, _call_edge_function as _call_messageme, _get_cfg
