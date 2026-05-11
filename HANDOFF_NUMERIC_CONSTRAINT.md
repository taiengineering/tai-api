# Numeric Constraint Extraction — 핸드오프 문서

## 작업 일시

2026-05-11

## 작업 요약

프롬프트 "Numeric Constraint Extraction Layer" 17단계 전체 실행 완료.
법령 원문의 정량 조건(\uc22b\uc790+\ub2e8\uc704+\uc5f0\uc0b0\uc790)을 구조화하여 10,329건 Numeric Constraint IR 생성.

---

## 핵심 원칙 (준수 확인)

- ✅ 원문에 있는 숫자만 추출 (\uc0dd\uc131 \uc5c6\uc74c)
- ✅ 원문에 있는 단위만 추출
- ✅ 단위 환산 미발생 (1\ub144\u2192365\uc77c, 1\ud1a4\u21921000kg \ub4f1 \uae08\uc9c0)
- ✅ "정기적으로"→월 1\ud68c, "즉시"→24\uc2dc\uac04 \ubcc0\ud658 \uc5c6\uc74c
- ✅ 숫자 조건을 확정 Rule로 변환하지 않음
- ✅ 모든 출력 CANDIDATE 상태
- ✅ source_span 전건 보유
- ✅ Issue 0건 (\ud30c\uc2f1 \uc2e4\ud328 \uc5c6\uc74c)

---

## 실행 스크립트

| 파일 | 용도 |
|---|---|
| `scripts/run_numeric_full.py` | 테이블 자동 생성 + 17단계 전체 실행 |

실행 방법:
```bash
cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
railway run python3 scripts/run_numeric_full.py
```

재실행 시 기존 데이터 자동 TRUNCATE 후 재추출.

---

## 생성 테이블

| 테이블 | 건수 | 역할 |
|---|---|---|
| numeric_constraint | 10,329 | 숫자 조건 후보 (value/unit/operator/span) |
| numeric_family_relation | 8,791 | Family 연결 후보 |
| numeric_issue | 0 | 파싱 실패 이슈 |

---

## 실행 결과

### status 분포

| status | 건수 |
|---|---|
| CANDIDATE | 10,329 |

전건 CANDIDATE. FAIL/AMBIGUOUS 0건.

### constraint_type 분포

| constraint_type | 건수 |
|---|---|
| DEADLINE_OR_PERIOD_CANDIDATE | 5,056 |
| UNKNOWN_THRESHOLD_CANDIDATE | 1,538 |
| FREQUENCY_THRESHOLD_CANDIDATE | 891 |
| EMPLOYEE_THRESHOLD_CANDIDATE | 783 |
| DISTANCE_THRESHOLD_CANDIDATE | 691 |
| MONETARY_THRESHOLD_CANDIDATE | 563 |
| CONCENTRATION_THRESHOLD_CANDIDATE | 302 |
| VOLTAGE_THRESHOLD_CANDIDATE | 277 |
| CAPACITY_THRESHOLD_CANDIDATE | 181 |
| POWER_THRESHOLD_CANDIDATE | 26 |
| AREA_THRESHOLD_CANDIDATE | 21 |

### operator 분포

| operator | 건수 | 설명 |
|---|---|---|
| <= | 5,195 | 이하/이내 |
| >= | 3,415 | 이상 |
| < | 483 | 미만 |
| BEFORE_CANDIDATE | 457 | 전까지 |
| PERIODIC | 438 | 주기 표현 (마다) |
| RANGE | 226 | 범위 (이상~이하/미만) |
| AFTER_CANDIDATE | 70 | 이후 |
| > | 45 | 초과 |

### unit 상위 15

| unit | 건수 |
|---|---|
| 일 | 2,701 |
| 년 | 1,719 |
| 개월 | 871 |
| 미터 | 790 |
| 명 | 676 |
| m | 575 |
| 회 | 453 |
| 개 | 389 |
| % | 298 |
| 만원 | 286 |
| 억원 | 267 |
| 시간 | 186 |
| 분 | 163 |
| V | 143 |
| 톤 | 135 |

### Family 연결 후보

| family_name | 건수 |
|---|---|
| DEADLINE_FAMILY | 5,056 |
| FREQUENCY_FAMILY | 891 |
| EMPLOYEE_SCOPE_FAMILY | 783 |
| DISTANCE_SCOPE_FAMILY | 691 |
| MONETARY_SCOPE_FAMILY | 563 |
| CONCENTRATION_SCOPE_FAMILY | 302 |
| VOLTAGE_SCOPE_FAMILY | 277 |
| CAPACITY_SCOPE_FAMILY | 181 |
| POWER_SCOPE_FAMILY | 26 |
| AREA_SCOPE_FAMILY | 21 |

UNKNOWN_THRESHOLD_CANDIDATE 1,538건은 Family 연결 미생성 (단위 미매칭).

---

## Validation

| 검증 항목 | 결과 |
|---|---|
| source_span 누락 | 0건 ✅ |
| 단위 환산 | 미발생 ✅ |
| semantic expansion | 미발생 ✅ |
| 원문에 없는 숫자 생성 | 없음 ✅ |
| "즉시"→24시간 변환 | 없음 ✅ |
| Rule 확정 변환 | 없음 ✅ |
| FAIL 건수 | 0건 ✅ |
| Issue 건수 | 0건 ✅ |

---

## 잔여 항목

| 항목 | 건수 | 비고 |
|---|---|---|
| UNKNOWN_THRESHOLD_CANDIDATE | 1,538 | 단위가 개(대)/척/편/세트 등 registry에 없는 단위 |
| UNKNOWN_SUBJECT | 다수 | subject 패턴 미매칭 (\uc55e 20\uc790 \ub0b4 \uba85\uc0ac\uad6c \uc5c6\uc74c) |
| 한글 숫자 | 미처리 | "십오명", "삼백" 등 순수 한글 숫자는 미추출 |
| 혼합 숫자 | 부분 | "1천만", "3억" 등 복합 혼합 숫자는 부분 지원 |
| 분수 표현 | 미처리 | "2분의 1" 패턴 미구현 |

---

## 다음 단계 후보

1. **Penalty Candidate & Obligation-Penalty Mapping Engine** — 벌칙/과태료 조문 식별 및 의무-처벌 연결
2. **한글 숫자 추출** — "십오", "삼백" 등 순수 한글 숫자 패턴 추가
3. **분수 표현** — "2분의 1" 패턴 추가
4. **Unit Registry 확장** — UNKNOWN_THRESHOLD 1,538건 감소
5. **Numeric→Constraint Graph 연결** — constraint_node와 numeric_constraint 교차 매핑
