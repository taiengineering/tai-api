"""Workflow Scenarios — 10개 시나리오."""

SCENARIOS = {
    "signup_flow": {
        "label": "\ud68c\uc6d0\uac00\uc785",
        "flow_key": "signup",
        "steps": [
            {"step_key": "input_info", "order": 1, "fail_rate": 0.02},
            {"step_key": "verify_phone", "order": 2, "fail_rate": 0.05},
            {"step_key": "save_db", "order": 3, "fail_rate": 0.01},
        ],
    },
    "login_flow": {
        "label": "\ub85c\uadf8\uc778",
        "flow_key": "login",
        "steps": [
            {"step_key": "input_credential", "order": 1, "fail_rate": 0.03},
            {"step_key": "auth_check", "order": 2, "fail_rate": 0.04},
            {"step_key": "token_issue", "order": 3, "fail_rate": 0.01},
        ],
    },
    "diagnosis_flow": {
        "label": "\ubc95\ub839\uc9c4\ub2e8",
        "flow_key": "diagnosis",
        "steps": [
            {"step_key": "sector_select", "order": 1, "fail_rate": 0.01},
            {"step_key": "input_factory", "order": 2, "fail_rate": 0.03},
            {"step_key": "engine_run", "order": 3, "fail_rate": 0.06},
            {"step_key": "result_display", "order": 4, "fail_rate": 0.02},
        ],
    },
    "process_registration": {
        "label": "\uacf5\uc815\ub4f1\ub85d",
        "flow_key": "process_registration",
        "steps": [
            {"step_key": "select_factory", "order": 1, "fail_rate": 0.02},
            {"step_key": "select_process", "order": 2, "fail_rate": 0.03},
            {"step_key": "save_db", "order": 3, "fail_rate": 0.02},
        ],
    },
    "document_generation": {
        "label": "\ubb38\uc11c\uc0dd\uc131",
        "flow_key": "document_generation",
        "steps": [
            {"step_key": "select_template", "order": 1, "fail_rate": 0.02},
            {"step_key": "render_pdf", "order": 2, "fail_rate": 0.08},
            {"step_key": "upload_storage", "order": 3, "fail_rate": 0.03},
        ],
    },
    "payment_attempt": {
        "label": "\uacb0\uc81c\uc2dc\ub3c4",
        "flow_key": "payment",
        "steps": [
            {"step_key": "select_plan", "order": 1, "fail_rate": 0.01},
            {"step_key": "pg_request", "order": 2, "fail_rate": 0.1},
            {"step_key": "pg_callback", "order": 3, "fail_rate": 0.05},
            {"step_key": "activate_subscription", "order": 4, "fail_rate": 0.02},
        ],
    },
    "subscription_flow": {
        "label": "\uad6c\ub3c5\uad00\ub9ac",
        "flow_key": "subscription",
        "steps": [
            {"step_key": "check_status", "order": 1, "fail_rate": 0.01},
            {"step_key": "renew_or_cancel", "order": 2, "fail_rate": 0.04},
        ],
    },
    "notification_ack": {
        "label": "\uc54c\ub9bc\ud655\uc778",
        "flow_key": "notification_ack",
        "steps": [
            {"step_key": "receive_alert", "order": 1, "fail_rate": 0.02},
            {"step_key": "ack_action", "order": 2, "fail_rate": 0.05},
        ],
    },
    "workflow_retry": {
        "label": "\uc7ac\uc2dc\ub3c4",
        "flow_key": "retry_flow",
        "steps": [
            {"step_key": "detect_failure", "order": 1, "fail_rate": 0.01},
            {"step_key": "retry_action", "order": 2, "fail_rate": 0.15},
            {"step_key": "verify_result", "order": 3, "fail_rate": 0.05},
        ],
    },
    "recovery_action_flow": {
        "label": "\ubcf5\uad6c\uc870\uce58",
        "flow_key": "recovery",
        "steps": [
            {"step_key": "identify_issue", "order": 1, "fail_rate": 0.02},
            {"step_key": "apply_fix", "order": 2, "fail_rate": 0.1},
            {"step_key": "verify_fix", "order": 3, "fail_rate": 0.05},
        ],
    },
}
