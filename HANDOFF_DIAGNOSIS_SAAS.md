# 법령진단서비스 / SaaS 반복설정 분리 — 핸드오프

## 작업 일시

2026-05-11

## 핵심

법령진단은 '결과 출력'까지 한다.
SaaS는 '승인받아 운영설정'까지 한다.
둘 다 Candidate 기반. 최종 반영은 승인 후에만.

---

## DB 6테이블

| 테이블 | 역할 | 영역 |
|---|---|---|
| diagnosis_session | 진단 세션 마스터 | 진단서비스 |
| diagnosis_candidate | 의무/금지/적용 후보 | 진단서비스 |
| diagnosis_penalty_link | 처벌 연결 후보 | 진단서비스 |
| diagnosis_schedule_hint | 스케줄 힌트 (SaaS가 소비) | 경계 |
| saas_setup_candidate | 반복설정 후보 | SaaS |
| saas_registration_log | Runtime 등록 이력 | SaaS |

## API

### 법령진단서비스 (`/api/v1/diagnosis-engine`)

| API | 용도 |
|---|---|
| POST /evaluate | **진단 실행** |
| GET /session/{id} | 세션 상세 |
| GET /sessions | 세션 목록 |

### SaaS 반복설정 (`/api/v1/saas-setup`)

| API | 용도 |
|---|---|
| POST /extract/{session_id} | **후보 추출** |
| GET /candidates | 후보 목록 |
| POST /approve/{id} | **사용자 승인** |
| POST /reject/{id} | 거절 |
| POST /needs-data/{id} | 추가 데이터 요청 |
| POST /register/{id} | **Runtime 등록** (승인 후만) |

## 플로우

```
사업장 입력 → POST /diagnosis-engine/evaluate
→ Candidate 결과 출력 (여기까지 진단서비스)
→ POST /saas-setup/extract/{session_id}
→ 반복관리 후보 추출 (자동 등록 안 함)
→ POST /saas-setup/approve/{id} (사용자 승인)
→ POST /saas-setup/register/{id} (Runtime 등록)
```

## 금지 규칙

- ❌ candidate → 의무 확정
- ❌ schedule candidate → 자동 일정 등록
- ❌ penalty candidate → 처벌 확정
- ❌ residual 숨김
- ❌ UNKNOWN 제거
- ❌ 미승인 항목 자동 등록
