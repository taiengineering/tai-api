# BE-10: 법령진단 통합 백엔드

**작성일:** 2026-04-18  
**파일:** `routers/diagnosis_integrated.py` v1.0.0  
**main.py:** v5.30.0  
**PR:** https://github.com/taiengineering/tai-api/pull/1 (dev→main)

---

## DB migration: `be10_free_diagnosis_backend`

| 테이블/코럼 | 내용 |
|---|---|
| `anonymous_diagnosis_results` (**신규**) | 익명 진단 결과 저장 (anonymous_diagnosis.py 라우터가 참조) |
| `diagnosis_disclaimer_log` (**신규**) | 면접 동의 구체적 기록 |
| `diagnosis_auth_log.auth_token` (**추가**) | FE에 노출되는 임시 세션 토큰 (CI 직접 노출 방지) |

---

## 엔드포인트 7개

| TASK | 메서드 | URL | 설명 |
|---|---|---|---|
| 1-A | POST | `/diagnosis/auth/prepare` | 이니시스 팝업 파라미터 |
| 1-B | POST | `/diagnosis/auth/callback` | 이니시스 콜백 → CI 저장 → auth_token HTML |
| 2   | GET  | `/diagnosis/auth/check` | 무료 횟수 확인 |
| 4   | GET  | `/diagnosis/price-tier` | 가격 자동 판정 |
| 6   | POST | `/diagnosis/disclaimer` | 면접 동의 저장 |
| 3   | POST | `/diagnosis/run` | 통합 진단 실행 (무료/유료 동일 API) |
| 5   | POST | `/diagnosis/upgrade` | 업그레이드 차액 결제 |

---

## TASK 1: 본인인증

**흐름:**
```
FE: POST /diagnosis/auth/prepare
  ↓ 이니시스 팝업 파라미터 반환
FE: 이니시스 JS SDK 팝업 실행
  ↓ 콜백 POST /diagnosis/auth/callback
    CI 해시 → diagnosis_auth_log upsert → auth_token HTML
  ↓ window.postMessage({type:'DIAG_AUTH', authToken, freeRemaining})
FE: auth_token 저장 (localStorage or memory)
```

**CI 보호:**
- CI는 SHA256 해시후 `diagnosis_auth_log.ci_hash`에만 저장
- FE는 auth_token(UUID)만 수신
- CI 직접 노출 없음

---

## TASK 2: 무료 제한 (CI당 총 3회, 리셋 없음)

```
GET /diagnosis/auth/check?auth_token={token}
→ {can_free: true, free_used: 1, free_limit: 3, free_remaining: 2}
```

- `diagnosis_auth_log.free_count` / `free_limit` 기반
- 리셋 없음: 이웴도 사용 수 양승 유지

---

## TASK 3: 통합 진단 실행

**일련 체크:**
1. auth_token 검증
2. disclaimer_log_id 검증 (ci_hash 일치)
3. tier 자동 판정
4. FREE: 횟수 초과 시 402
5. PAID: payment_ref 없으면 402
6. `diagnose_step1` 실행
7. `anonymous_diagnosis_results` 저장
8. FREE면 free_count+1

---

## TASK 4: 가격 자동 판정

| 섹터 | 기준 | 티어 |
|---|---|---|
| BUILDING | 면적 ≥ 5,000㎡ | BUILDING_LARGE_V2 (249K) |
| BUILDING | 면적 < 5,000㎡ | BUILDING_V2 (99K) |
| CONSTRUCTION | 공사금액 ≥ 50억 | CONSTRUCTION_PREMIUM (299K) |
| CONSTRUCTION | 공사금액 < 50억 | CONSTRUCTION (145K) |
| INDUSTRY | 사용자 선택 | 79K / 149K / 249K |

---

## TASK 5: 업그레이드

```
POST /diagnosis/upgrade
{
  "auth_token": "...",
  "public_token": "...",
  "target_tier_code": "BUILDING_LARGE_V2",
  "payment_ref": "KG-INICIS-20260418-..."
}
→ 엔진 재실행 + anonymous_diagnosis_results.full_result 업데이트
→ {prev_tier, new_tier, diff_paid_krw, result}
```

---

## TASK 6: 면접 동의

**확정 데틸 문구:**
> 이 진단 결과는 입력하신 사업장 정보를 기반으로 정밀 분석하여 도출된 참고 자료입니다. 최종 법적 해석 및 준수 여부는 담당 안전관리자 또는 전문가와 함께 확인하시기 바랍니다. TAI Engineering은 이 진단 결과로 인한 직·간접적 손해에 대하여 재임을 지지 않습니다.

- "**기계적 대조**" 표현 금지
- "**더 많이 입력하면 더 정확**" 표현 금지
- 동의 시점의 문구 스냅샷을 `diagnosis_disclaimer_log.disclaimer_text`에 저장

---

## TASK 7: diagnosis_plan_recommend.py v1.1.0

**변경 내용:**
- `recommended`: monthly_krw / pricing_note / is_custom 제거 → `necessity` 필드 추가
- `comparison`: TAI Safe 연간비용 제거, 과태료 위험 금액만 유지
- `alternatives`: monthly 제거

**necessity 예시:**
```json
{"plan_code": "INDUSTRY_PRO",
 "plan_name": "산업 PRO",
 "necessity": "고위험·대규모 사업장 전수 설비 관리와 API 연동에 필요합니다"}
```

---

## 주요 코드 원칙

- CI 노출 없음: auth_token(UUID) 세션만 FE에 노출
- INICIS_VERIFY_MID 미설정 시 `/auth/prepare` 503 반환
- 무료/유료 결과 모두 `anonymous_diagnosis_results` 저장
- 유료 업그레이드: 제도 엀지로만, 동일 엔진 재실행
