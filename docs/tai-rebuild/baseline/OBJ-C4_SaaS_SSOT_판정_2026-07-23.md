# OBJ-C4 (SaaS SSOT) — 4개 도메인 판정 (데이터 대조)

**작성일:** 2026-07-23 · **방법:** 각 도메인의 병렬 저장소 실데이터·행수 대조.
**총평:** C4는 기계적 청소가 아니다. **활성 리스크는 가격(비즈니스 결정)·커미션(정본 확인)에 집중**되고, 교육·알림 이원화는 **휴면 코드중복(0행)**이라 정리 단계 저위험 처리.

---

## 1. 가격 — ⚠️ 비즈니스 결정 선행 (상세: [OBJ-C4_가격판정](./OBJ-C4_가격판정_2026-07-23.md))
- `price_master`·`price_policy`·`product_pricing` **3개 모델이 같은 서비스에 다른 실제 가격**(SaaS 산업기본 149k vs 99k, 공개 79k/149k). → 뷰 수렴 불가.
- 기술 SSOT(price_master)는 admin price-setting·public_pricing v3 경로에서 단일화됨. tai-www 공개페이지(product_pricing)·`/price-policy`가 **다른 가격**으로 소비.
- **필요:** 정본 가격표 확정(비즈니스) → 이후 나머지 모델 수렴/격리.

## 2. 커미션 — 🔎 정본 확인 필요 (데이터 있음)
- `price_commission`(3행) = **service_type × flat fee_rate 준-SSOT**: EXPERT 10% / REPAIR 8% / CONSULTING 10% "기본 수수료".
- 그 위 상세 override: `price_repair_brokerage`(REPAIR 구간·긴급·보증), `connection_commission`(연결서비스: grade·escrow = **별개 서비스**), `experts.platform_fee_rate`(전문가별).
- **구조 판정:** "기본율 + 서비스/전문가별 override" 계층 — 설계 자체는 합리적. **문제는 정산 시 어느 게 정본인지 불명확**(REPAIR가 8% flat인지 `price_repair_brokerage` 구간표인지). 정산은 `matching_contracts.expert_amount` + 원천징수 3.3%(Z4)에서 오는 것으로 보여, flat `price_commission`이 실사용·상세표는 admin 설정용일 가능성.
- **필요(저위험):** 코드경로 확인(matching_commission / settlements / repair) → 계층 문서화 or 통합. connection_commission=별개 유지.

## 3. 교육 — 💤 휴면 코드중복 (0행)
- `education_history`·`education_assignment` **둘 다 0행**. 이원화(`completed` vs `COMPLETED`)·중복 엔드포인트는 **코드 설계 중복**이나 **활성 데이터 없음**.
- ※ admin 교육이수현황(20건)은 이 두 테이블이 아닌 **다른 테이블**에서 옴 → 실소스 별도 확인 필요(저우선).
- **필요:** 정리 단계(O6/데드코드)에서 코드 dedup. 데이터 충돌 없음 → 저위험.

## 4. 알림 — 💤 휴면 + 레거시 대체 (0행)
- `notifications`(레거시)·`runtime_notification_queue`(엔진) **둘 다 0행**(휴면/일시성). 레거시 `notifications.py`는 runtime 알림엔진에 사실상 대체됨(물리 co-write 없음, 05 확인).
- **필요:** 레거시 알림 스택 실사용 0 확인 후 은퇴(저위험, O8/O6와 함께).

---

## 5. C4 판정 요약
| 도메인 | 상태 | 필요 조치 | 위험 |
|---|---|---|---|
| 가격 | 활성 충돌(다른 가격) | **정본 가격표 결정(비즈니스)** | 高(고객 노출가) |
| 커미션 | 계층형, 데이터 有 | 정산 정본 코드경로 확인 → 문서화/통합 | 中 |
| 교육 | 휴면 중복(0행) | 코드 dedup(정리단계) | 低 |
| 알림 | 휴면·레거시 대체(0행) | 레거시 은퇴 확인 | 低 |

## 6. 다음
- **가격:** 정본 가격표 결정 대기(고객). 결정 전 컷오버 금지.
- **커미션:** matching/settlement 코드경로 1차 정독 → "기본율+override" 정본 규칙 확정(안전 후속).
- **교육·알림:** O6/O8 정리와 함께 코드 dedup·레거시 은퇴.
- 안전 기술 후속(별도 PR): pricing_validation docstring 정정, dev_otp env-gate.
