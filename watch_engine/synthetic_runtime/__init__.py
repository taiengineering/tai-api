"""Synthetic Runtime — 살아있는 가짜 SaaS 세계.

Persona + Scenario + Chaos + Orchestrator.
모든 Event는 Runtime Bus 경유. environment='mock'.
"""

from watch_engine.synthetic_runtime.orchestrator import run_synthetic_tick
from watch_engine.synthetic_runtime.chaos_engine import inject_chaos
from watch_engine.synthetic_runtime.personas import PERSONAS
from watch_engine.synthetic_runtime.scenarios import SCENARIOS
