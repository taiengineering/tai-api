"""Notification Engine Phase 1 — Central Operations Communication Runtime.

Architecture:
  Any Engine → Signal/Event → Notification Runtime → Recipient Resolution
  → Delivery Queue → Channel Adapter → Audit

Principles:
  1. Engine은 Signal만 발생한다
  2. Notification Engine만 Delivery를 수행한다
  3. 비즈니스 로직은 Notification Engine에 넣지 않는다
  4. 사람은 마지막 Escalation에만 개입한다
"""
