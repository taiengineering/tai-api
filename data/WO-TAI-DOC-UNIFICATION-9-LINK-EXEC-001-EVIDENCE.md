# WO-TAI-DOC-UNIFICATION-9-LINK-EXEC-001 — 등록 실행 증거

**작성일**: 2026-10-21  
**작업 유형**: PRODUCTION WRITE — fn_udl_propose RPC 9회 실행  
**Owner 승인**: CONFIRMED (세션 내 직접 승인)  
**실행 시각**: 2026-10-21 19:48:26 ~ 19:49:20 KST

---

## 1. 실행 결과 (9/9 SUCCESS)

| # | Pair | link_id | review_state | created_at |
|---|------|---------|-------------|-----------|
| 1 | DOC-OSH-058 ↔ ref-gov-01 | `e6e1fe14-bfb7-4c21-b3a4-64e2d4500278` | PROPOSED | 19:48:26 |
| 2 | DOC-OSH-045 ↔ ref-c023 | `6dd4be77-4407-429d-be17-ad14c31d8aaa` | PROPOSED | 19:48:31 |
| 3 | DOC-OSH-047 ↔ ref-conf-01 | `2f75fd78-0b96-43b0-9c76-16887e6824b1` | PROPOSED | 19:48:38 |
| 4 | DOC-CON-011 ↔ ref-gov-06 | `35191c1d-0949-4a8c-8ff5-2a1747eb7204` | PROPOSED | 19:48:45 |
| 5 | DOC-OSH-037 ↔ ref-c031 | `872c7695-b5fa-4760-adc8-b6bd9842b54b` | PROPOSED | 19:48:53 |
| 6 | DOC-CON-041 ↔ ref-p-14 | `56ffbab4-406f-47a6-ba65-de3c2807b6d1` | PROPOSED | 19:49:00 |
| 7 | DOC-OSH-006 ↔ ref-c031 | `f42dffde-9503-4240-b911-b73511032e1c` | PROPOSED | 19:49:06 |
| 8 | DOC-OSH-049 ↔ ref-c025 | `98b2f548-969d-4832-a7b6-9f1dbf509d26` | PROPOSED | 19:49:13 |
| 9 | DOC-OSH-015 ↔ ref-gov-06 | `e4583d1d-8011-4c67-83b7-c7b011da871a` | PROPOSED | 19:49:20 |

**FAILED = 0 / DUPLICATE = 0 / SUCCESS = 9**

---

## 2. 실행 파라미터 (공통)

| 파라미터 | 값 |
|---------|---|
| p_actor_id | `c4b3d044` (TAI_DOC_OWNER_USER_ID) |
| p_relation_type | `RELATED_FORM` |
| version (all) | 1 |
| review_state (all) | PROPOSED |

---

## 3. 다중 매핑 확인

| Ref | Pair # | link_id | 비고 |
|-----|--------|---------|------|
| ref-c031 (`ee664e1a`) | Pair 5 (DOC-OSH-037) | `872c7695` | 보조 매핑 |
| ref-c031 (`ee664e1a`) | Pair 7 (DOC-OSH-006) | `f42dffde` | 우선 매핑 |
| ref-gov-06 (`58ba7434`) | Pair 4 (DOC-CON-011) | `35191c1d` | 건설 특화 |
| ref-gov-06 (`58ba7434`) | Pair 9 (DOC-OSH-015) | `e4583d1d` | 우선 매핑 |

unique constraint `(saas_catalog_id, reference_form_id)` — 4건 모두 서로 다른 saas_catalog_id. 제약 충족 확인.

---

## 4. 최종 검증 쿼리 결과

```
9행 반환 / relation_type=RELATED_FORM 9/9 / review_state=PROPOSED 9/9 / version=1 9/9
```

DB 직접 조회(unified_document_link WHERE id IN (...)) — 전건 일치.

---

## 5. 종료 보고

```
WO = WO-TAI-DOC-UNIFICATION-9-LINK-EXEC-001

PROPOSED_PAIRS     = 9
FAILED_PAIRS       = 0
DUPLICATE_PAIRS    = 0

RELATION_TYPE      = RELATED_FORM
REVIEW_STATE       = PROPOSED (전건)
ACTOR_ID           = c4b3d044

MULTI_MAPPING:
  ref-c031  → Pair5(보조)+Pair7(우선) 동시 등록 완료
  ref-gov-06 → Pair4(건설)+Pair9(우선) 동시 등록 완료

STATE_TRANSITION   = 0 (PROPOSED→UNDER_REVIEW 미실행)
PRODUCTION_WRITE   = 9 (fn_udl_propose RPC × 9)
NEW_DEVELOPMENT    = 0

RESULT = PROPOSED_COMPLETE — GPT IV 대기
```

---

**조회 소스 식별자**:
- fn_udl_propose RPC: vwlahtguyggrhvslabax 2026-10-21 19:48~19:49 (9회)
- unified_document_link 검증: vwlahtguyggrhvslabax 2026-10-21 19:49:25 KST (9행 PROPOSED 확인)
- 기준 커밋: f19657a4 (PREFLIGHT 증거 직전)
