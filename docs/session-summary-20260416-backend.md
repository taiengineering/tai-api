# 백엔드 세션 작업 요약 — 2026-04-16

**담당:** backend (tai-api)  
**세션 시각:** 2026-04-16 KST  
**최종 main 버전:** construction.py v2.2.3

---

## 완료 작업 목록

### ① dev 동기화 — v2.2.3 통합 커밋

**배경:** main에 핫픽스(FS-05: latitude/longitude)가 직접 push됨 → dev 미반영 상태

**해결:** main v2.2.2(FS-05) + dev SB-01/SB-02를 합쳐 v2.2.3으로 단일 커밋

```
routers/construction.py  v2.2.3
  - FS-05: SiteCreate/SitePatch latitude, longitude (Optional[float]) 추가
  - SB-01 BUG-FIX #3: _auto_diagnose_and_schedule() inspection+action 모두 스케줄화
  - SB-02: utils.logger 사용 (print→logger.error/warning 교체)
```

---

### ② SB-01 BUG-FIX #3 (v2.2.3 포함)

**문제:** `_auto_diagnose_and_schedule()`이 `inspection_required`만 스케줄로 변환
- `POST /sites` 자동생성: **78건**
- `POST /sites/{id}/generate-schedules`: **177건**
- 동일 조건에서 두 경로 결과 불일치

**수정:**
```python
# BEFORE
inspection_rules = diag["result_data"].get("inspection_required") or []
sched = _run_generate_schedules(supabase, factory_id, inspection_rules, company_id)

# AFTER
inspection_rules = diag["result_data"].get("inspection_required") or []
action_rules     = diag["result_data"].get("action_required") or []
all_rules = inspection_rules + action_rules
sched = _run_generate_schedules(supabase, factory_id, all_rules, company_id)
```

**검증 결과 (Supabase DB):**
| 현장 | 수정 전 | 수정 후 |
|---|---|---|
| [검증] BUG#1 테스트 | 78건 (04:54) | — |
| 강남 센트럴타워 | — | **178건** (05:04) |
| E2E테스트 서울강남 | — | **177건** (05:05) |

---

### ③ SB-02 Silent Fail 제거 (v2.2.3 포함)

**신규 파일:** `utils/logger.py` v1.0.0
```python
from utils.logger import get_logger
log = get_logger(__name__)
log.error("[CONSTRUCTION] 실패", exc_info=True)  # Fly.io [ERROR] grep 감지
log.warning("[FCM] 알림 실패 (무시)")            # Fly.io [WARNING] 감지
```

**교체 위치 (construction.py):**
1. `_create_factory_for_site()` factories INSERT 실패
2. `_auto_diagnose_and_schedule()` 전체 실패
3. `_auto_diagnose_and_schedule()` inspection_sets 생성 실패
4. `diagnose_site()` inspection_sets 생성 실패
5. `_send_fcm_inspection_alert()` FCM 발송 실패

---

### ④ SB-06 산재판례 수집

**현황:** `posts.category='산재판례'` **0건**

**배포 후 1회 수동 실행 필요:**
```bash
curl -X POST https://api.taieng.co.kr/precedents/collect \
  -H "Content-Type: application/json" -d '{}' --max-time 130
```

**확인:**
```bash
curl "https://api.taieng.co.kr/precedents/search?query=추락" | jq '.total'
```

---

### ⑤ Supabase Storage 버킷 `inspections` 생성

**Migration:** `create_inspections_storage_bucket_rls` 적용 완료

| 항목 | 값 |
|---|---|
| 버킷명 | `inspections` |
| 공개 설정 | public=true |
| 최대 파일 크기 | 10MB |
| 허용 MIME | JPEG / PNG / WEBP / HEIC / HEIF |

**RLS 정책 3개:**
- SELECT: 누구나 (공개 읽기)
- INSERT: `authenticated` + `path prefix = auth.uid()`
- DELETE: `owner = auth.uid()` (본인 소유만)

**프론트 교체 가이드:** `docs/fs04-storage-migration.md` 참조

---

### ⑥ PR #1 업데이트

**PR URL:** https://github.com/taiengineering/tai-api/pull/1  
**제목:** `feat+fix: v2.2.3 — BUG #3 해결 + silent fail 제거 + FS-05 좌표 필드 + Storage 마이그레이션 문서`  
**방향:** dev → main  
**상태:** main에 v2.2.3 이미 반영됨 (pushed_at 08:01 KST)

---

## Smoke Test 결과

| 항목 | 결과 | 비고 |
|---|---|---|
| BUG #3 검증 (78→177건) | ✅ PASS | DB 직접 확인 |
| FS-05 좌표 컬럼 존재 | ✅ PASS | latitude/longitude DOUBLE PRECISION |
| SB-06 산재판례 수집 | ⏳ 대기 | /precedents/collect 수동 실행 필요 |

---

## 신규 DB 테이블

- `industrial_accident_precedents` — 산재판례 전용 테이블 (4개 인덱스)
  - case_number, sector, hazard_type, decision_date, summary, violation_laws 등

---

## 변경된 파일 목록

| 파일 | 버전 | 변경 내용 |
|---|---|---|
| `routers/construction.py` | v2.2.3 | BUG#3, SB-01, SB-02, FS-05 통합 |
| `utils/logger.py` | v1.0.0 | 신규 (표준 로거) |
| `routers/weather.py` | v1.3.0 | GET /weather/work-stoppage?site_id= 추가 |
| `routers/precedent_api.py` | v1.4.0 | /sync 별칭, sector/year 파라미터, iap/search 추가 |
| `routers/inspection_set_auto.py` | v1.0.1 | inspection_cycle_code fallback 추가 |
| `docs/fs04-storage-migration.md` | 신규 | Storage 교체 스니펫 |
| `docs/workorder-backend-phase2-20260416.md` | 기존 | SB-01~06 워크오더 |
| `docs/workorder-be-construction-20260416.md` | 기존 | BE-1~4 워크오더 |

---

## 다음 E2E 검증 단계

기획 윈도우 주도로 아래 순서 진행 예정:

1. SB-06 판례 수집 1회 실행 → 적재 건수 확인
2. 건설현장 신규 등록 E2E: 현장생성 → 자동진단 → 스케줄(177건) → inspection_sets 확인
3. weather/work-stoppage?site_id= 엔드포인트 동작 확인
4. 프론트 Storage 교체 작업 (FE-SAFE-04) 착수 가능 상태
