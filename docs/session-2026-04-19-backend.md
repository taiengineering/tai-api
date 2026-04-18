# 백엔드 세션 작업내역 — 2026-04-19

**담당:** 백엔드 창 (tai-api, dev 브랜치)  
**PR #1:** dev→main 미머지 (다수 BE 작업 누적)

---

## 완료 작업

### BE-08: 진단 기반 SaaS 플랜 추천 API v1.0.0

| 항목 | 내용 |
|---|---|
| 파일 | `routers/diagnosis_plan_recommend.py` v1.0.0 |
| 엔드포인트 | `GET /diagnosis/{diagnosis_id}/recommend-plan` (공개) |
| 등록 | main.py v5.29.0 |
| 로직 | AI 없음. severity → obl_cnt → workers 조건 분기 |
| 워크오더 | `docs/workorder-be08-plan-recommend.md` |
| FN-06 워크오더 | `docs/workorder-fn06-plan-recommend.md` (프론트 창 전달) |

**DB 검증:**
| diagnosis_id | sector | severity | 추천 |
|---|---|---|---|
| f48fbff2 | INDUSTRY | CRITICAL | PRO 249K ✅ |
| 233cc6de | CONSTRUCTION | CRITICAL | PREMIUM 385K ✅ |

---

### BE-09: 익명 진단 토큰 기반 플랜 추천

| 항목 | 내용 |
|---|---|
| 파일 | `routers/anonymous_diagnosis.py` 내부 추가 |
| 엔드포인트 | `GET /anonymous-diagnosis/{token}/recommend-plan` |
| 핵심 | BE-08 함수 import 재사용, 코드 중복 0줄 |
| main.py | 변경 없음 (기존 라우터 내부 추가) |
| 워크오더 | `docs/workorder-be09-anon-recommend.md` |

**sector 보정 매핑:**
| 입력 | 출력 |
|---|---|
| MANUFACTURING | INDUSTRY |
| SPECIAL_FACILITY | BUILDING |

---

### 이슈#2 해결: GET /{token}/transform 엔드포인트 추가

**원인:** JS에서 `fetch(\`${API}/anonymous-diagnosis/${token}/transform\`)` 참조하는데  
백엔드에 `/transform` 엔드포인트가 없었음.

**결정:** JS 수정 없이 백엔드 추가 (목적이 `/{token}`과 다름 — 항상 표준 스키마 반환)  
**처리:** `anonymous_diagnosis.py`에 `GET /{token}/transform` 추가  
**재사용:** `diagnosis_transform.py` 함수 import (중복 0줄)  
**응답:** headline / obligations / warnings / exposure / inspection_schedule / roi 표준 스키마

---

### BE-10: 법령진단 통합 백엔드 v1.0.0

| 항목 | 내용 |
|---|---|
| 파일 | `routers/diagnosis_integrated.py` v1.0.0 |
| main.py | v5.30.0 |
| 워크오더 | `docs/workorder-be10-diagnosis-backend.md` |

**DB migration `be10_free_diagnosis_backend`:**
| 대상 | 내용 |
|---|---|
| `anonymous_diagnosis_results` (신규) | ci_hash / auth_log_id / disclaimer_log_id / tier_code / paid_amount 포함 |
| `diagnosis_disclaimer_log` (신규) | 면책 동의 기록 (ci_hash, 문구 스냅샷, IP) |
| `diagnosis_auth_log.auth_token` (추가) | FE 노출용 임시 UUID 세션 토큰 |

**엔드포인트 7개 (모두 공개):**
| TASK | URL | 핵심 |
|---|---|---|
| 1-A | `POST /diagnosis/auth/prepare` | 이니시스 팝업 파라미터 |
| 1-B | `POST /diagnosis/auth/callback` | CI→ci_hash→auth_token HTML |
| 2 | `GET /diagnosis/auth/check` | free_count/limit/remaining |
| 4 | `GET /diagnosis/price-tier` | 면적/공사금액 자동판정 |
| 6 | `POST /diagnosis/disclaimer` | 면책 동의 저장 |
| 3 | `POST /diagnosis/run` | 무료(횟수제한)/유료(payment_ref) 동일 API |
| 5 | `POST /diagnosis/upgrade` | 차액 결제 → 엔진 재실행 |

**TASK 7 — diagnosis_plan_recommend.py v1.1.0:**
- `recommended`: monthly_krw / pricing_note / is_custom **제거** → `necessity` 추가
- `comparison`: TAI Safe 연간비용 **제거**, 과태료 위험만 유지
- `alternatives`: monthly **제거**

**면책 확정 문구:**
> 본 진단 결과는 현행 법령과 사업장 정보를 정밀 분석하여 적용 가능한 법적 의무를 도출한 것입니다. 본 서비스는 법률 상담·자문·의견 제공이 아니며, 개별 사안에 대한 법적 판단이나 해석을 포함하지 않습니다. 실제 행정 처분·감독 기준은 관할 기관의 판단에 따라 달라질 수 있으므로, 구체적 법률 적용이 필요한 경우 관할 행정기관 또는 법률 전문가에게 확인하시기 바랍니다.

---

### fix(BE-10): 5건 수정 — diagnosis_integrated.py v1.0.1

| Fix | 내용 |
|---|---|
| FIX-1 | "면접" → "면책" 오타 전체 8곳 |
| FIX-2 | DISCLAIMER_TEXT 확정 문구 교체 |
| FIX-3 | 가격 판정 설명 오타 4곳 ("대형건물으로" → "대형건물로" 등) |
| FIX-4 | callback docstring 인코딩 깨짐 수정 |
| FIX-5 | CI 평문 저장 제거 (보안) — `"ci": ""` |

---

## 커밋 이력 (dev 브랜치, 이번 세션)

| SHA | 내용 |
|---|---|
| 42be77e6 | feat(BE-10): 법령진단 통합 백엔드 v1.0.0 + main.py v5.30.0 |
| ae849a39 | fix(BE-10): 5건 수정 v1.0.1 |
| 9cd6259d | feat(BE-08): diagnosis_plan_recommend.py v1.0.0 + FN-06 워크오더 |
| ade648a8 | feat(BE-09): 익명 진단 token recommend-plan |
| cf08b6ba | fix(이슈#2): GET /{token}/transform 엔드포인트 추가 |

---

## PENDING 사항

| 항목 | 내용 |
|---|---|
| **PR #1 머지** | dev→main 미머지 (기획창 승인 후) |
| **Fly.io Secrets** | INICIS_VERIFY_MID, INICIS_VERIFY_SITE_CD, INICIS_VERIFY_SITE_KEY, INICIS_VERIFY_RETURN_URL |
| **Fly.io 전용 IP** | `flyctl ips allocate-v4 --dedicated` → 이니시스 IP 등록 |
| **FN-06** | 프론트 창: 진단 결과 하단 추천 카드 UI |
| **SB-06** | `POST https://api.taieng.co.kr/precedents/collect` 1회 수동 실행 |
