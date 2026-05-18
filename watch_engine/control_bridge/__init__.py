"""Control Bridge — Event → Operational Truth 변환.

Workflow Runtime의 사실(INFO event)을
Control Runtime이 운영 의미(WARNING/CRITICAL)로 해석.
"""

from watch_engine.control_bridge.bridge_evaluator import evaluate_bridge
from watch_engine.control_bridge.severity_projection import project_severity
from watch_engine.control_bridge.bridge_rules import BRIDGE_RULES
