# [BACKEND] TAI Safe Phase 2 — 미완료 작업 일괄 처리

**작성일:** 2026-04-16  
**담당 윈도우:** backend (tai-api)  
**사전조건:** construction v2.2.1 main 배포 완료 ✅

---

## 전체 작업 목록 (우선순위순)

| # | ID | 작업 | 긴급도 | 예상 시간 |
|---|---|---|---|---|
| 1 | SB-01 | BUG #3: `_auto_diagnose_and_schedule()` rule coverage 통일 | 🔴 | 30분 |
| 2 | SB-02 | 실패 로깅 강화 (silent fail 제거) | 🔴 | 30분 |
| 3 | SB-03 | `routers/weather.py` 신규: 기상청 API + 작업중지 판정 | 🟡 | 2시간 |
| 4 | SB-04 | `routers/precedent_api.py` 신규: 법제처 판례 API | 🟡 | 2시간 |
| 5 | SB-05 | `agent-service` 라우터 상태 점검 + 불필요 시 삭제 | 🟢 | 30분 |
| 6 | SB-06 | 산재판례 수집 cron (pg_cron 전환 전에는 HTTP trigger) | 🟢 | 1시간 |

동일 커밋에 묶지 말고 각 ID당 독립 커밋로 올리기.

---

## SB-01 🔴 BUG #3: rule coverage 통일

### 배경
2026-04-16 검증 과정에서 두 경로의 스케줄 생성 수 불일치 발견:
- `POST /sites` → `_auto_diagnose_and_schedule()`: **inspection_required 만** 스케줄화 (78건)
- `POST /sites/{id}/generate-schedules`: **inspection + action** 둘 다 스케줄화 (177~178건)

같은 BUILDING 180억 55명 조건인데 결과가 다른 것은 버그.

### 위치
`routers/construction.py` → `_auto_diagnose_and_schedule()` 내부

### 수정 내용
```python
# BEFORE (v2.2.1 현재)
inspection_rules = diag["result_data"].get("inspection_required") or []
sched = _run_generate_schedules(supabase, factory_id, inspection_rules, company_id)

# AFTER (v2.2.2)
inspection_rules = diag["result_data"].get("inspection_required") or []
action_rules     = diag["result_data"].get("action_required") or []
all_rules = inspection_rules + action_rules
sched = _run_generate_schedules(supabase, factory_id, all_rules, company_id)
```

VERSION: 2.2.1 → 2.2.2, docstring에 BUG-FIX #3 항목 추가.

### 검증
배포 후 신규 현장 등록 시 response.auto.schedules.created가 170여건으로 켜져야 함:
```bash
curl -X POST https://api.taieng.co.kr/construction/sites \
  -d '{...same as verify test...}' | jq '.auto.schedules.created'
# 기대: 170~180 (이전 78에서 증가)
```

---

## SB-02 🔴 silent fail 제거

### 배경
BUG #1이 발견되지 않고 프로덕션을 오래 달렸던 근본 원인: `try/except Exception as e: print(...)` 패턴이 DB check constraint 위반을 조용히 삼킬. 스킠 불가.

### 작업
1. 프로젝트 루트에 `utils/logger.py` 신규 생성 (Python 표준 logging 래퍼, JSON 로그)
2. `routers/construction.py`에서 모든 `print(...)` 호출을 `logger.error(..., exc_info=True)` 또는 `logger.warning(...)`으로 교체
3. 식별 대상 패턴 (최소한 이번 스프린트는 construction.py만 처리):
   - `[CONSTRUCTION] factories 자동생성 실패 (무시): ...`
   - `[AUTO_INSPECT_SETS] ...  자동생성 실패 (무시): ...`
   - `[CONSTRUCTION] 자동진단/일정생성 실패 (무시): ...`
   - `[FCM] 점검 알림 발송 실패 (무시): ...`

### utils/logger.py 시안 구조
```python
import logging, json, os, sys

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    fmt = '%(asctime)s [%(levelname)s] %(name)s | %(message)s'
    handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    return logger
```

Fly.io 로그에서 `grep '\[ERROR\]'` 또는 UptimeRobot keyword monitor로 감지 가능.

### 추후 확장 (이번 스프린트 밬위 외)
다른 라우터(building.py, industry.py 등)도 순차 적용. 이번에는 construction.py만.

---

## SB-03 🟡 weather.py — 기상청 API + 작업중지 판정

### 법령 근거
- 산업안전보건기준에 관한 규칙 제383조·제334조 등
- 강풍·강우·폭염 → 완전한 작업중지 의무

### 엔드포인트 설계
| Method | Path | 설명 |
|---|---|---|
| GET | `/weather/current?lat=&lon=` | 현재 날씨 (행정구역 좌표 기반) |
| GET | `/weather/work-stoppage?site_id=` | 현재 site 기반 작업중지 대상 여부 |
| GET | `/weather/forecast?site_id=&days=3` | N일간 예보 + 작업중지 시각 예측 |

### 작업중지 판정 기준 (기본값, 체감상 조정 가능)
| 조건 | 판정 |
|---|---|
| 순간풍속 ≥ 10 m/s (경지 상) | 경고 |
| 순간풍속 ≥ 15 m/s 또는 1시간 강우량 ≥ 30 mm | 작업중지 의무 |
| 폭염주의보 발령 | 야외 작업 제한 |
| 놀 관련 특보 | 동결 작업 제한 |

### 기상청 API 연동
- 단기예보 API (`getUltraSrtNcst`, `getVilageFcst`)
- 정사은 변동: 기상청 정보 API 발급 받으면 `.env`에 `KMA_API_KEY` 추가
- `site.site_address` → 위도·경도 변환 필요 (신규 KMA 변환 유틸 또는 도로명주소 API 일자도 사용)

### 기존 구현 확인
메모리에 "기상청 API + 작업중지 법령 조합하여 작업중지 경고 기능 이미 구현"이라 적혀 있으나 routers 폴더에 weather.py 미존재 상태. 기존에 프론트에만 일부가 있는 것인지 확인 후 중복 피하고 통합.

---

## SB-04 🟡 precedent_api.py — 법제처 판례 API

### 엔드포인트
| Method | Path | 설명 |
|---|---|---|
| GET | `/precedents/search?keyword=&sector=&year=` | 판례 검색 |
| GET | `/precedents/{id}` | 단건 조회 |
| POST | `/precedents/sync` | 배치 수집 (SB-06 cron이 호출) |

### 데이터 소스
법제처 DRF API (https://www.law.go.kr/DRF/lawService.do) — 국토교통부·고용노동부 관련 산재·중대재해 판례.

### DB 스키마 (신규 테이블 필요)
```sql
CREATE TABLE industrial_accident_precedents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_number VARCHAR(50) UNIQUE NOT NULL,  -- 사건번호
  case_name VARCHAR(500),
  court_name VARCHAR(100),
  decision_date DATE,
  sector VARCHAR(20),  -- BUILDING/INDUSTRY/CONSTRUCTION
  hazard_type VARCHAR(50),  -- 전도/충돌/추락 등
  keywords TEXT[],
  summary TEXT,
  full_text TEXT,
  violation_laws JSONB,  -- 위반 법령 목록
  penalty_info JSONB,    -- 업체 과태료·대표 처벌 정보
  source_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_precedents_sector ON industrial_accident_precedents(sector);
CREATE INDEX idx_precedents_hazard_type ON industrial_accident_precedents(hazard_type);
CREATE INDEX idx_precedents_decision_date ON industrial_accident_precedents(decision_date DESC);
```
Supabase `apply_migration`으로 적용.

---

## SB-05 🟢 agent-service 라우터 점검

### 확인 사항
1. `main.py`에서 `agent_service` 라우터 등록 여부
2. `routers/agent_service.py` 존재 여부
3. 존재하면 실제 호출되는 엔드포인트인지 로그 확인
4. 사용안 됨 → 제거, 사용 됨 → 기능 문서화

---

## SB-06 🟢 산재판례 수집 cron

### 현재 상태
- pg_cron 전환은 개발 100% 완료 후 예정
- 그전에는 HTTP trigger (외부 cron 서비스 호출)

### 구현
- `POST /precedents/sync` 엔드포인트 호출만으로 동작하도록 설계
- cron 서비스 (GitHub Actions schedule 또는 cron-job.org) 매일 04:00 KST
- 실행 결과를 `cron_execution_log` 테이블에 기록 (기존 테이블 사용)

---

## 코드 품질 기준

- 모든 신규 라우터에 `VERSION` 스트링 + docstring 버전 로그 포함
- 신규 에더포인트는 FastAPI `tags=[...]` 부여해 Swagger 그룹화
- 전역적으로 `from utils.logger import get_logger` 사용 (SB-02 완료 후)
- 모든 주석·로그 문자열은 한국어
- 커밋은 `dev` 브랜치에만
- 각 SB-XX마다 **독립 커밋**으로 올리세요 (롤백 용이성)
- 모든 작업 완료 후 `dev→main` PR 1개 생성

---

## 완료 기준

- [ ] SB-01 construction.py v2.2.2 dev 커밋
- [ ] SB-02 utils/logger.py + construction.py print→logger 교체
- [ ] SB-03 routers/weather.py + 3개 에더포인트 동작 확인
- [ ] SB-04 routers/precedent_api.py + DB 스키마 적용
- [ ] SB-05 agent-service 점검 결과 보고
- [ ] SB-06 /precedents/sync 에더포인트 동작 확인
- [ ] dev→main PR 생성
- [ ] Fly.io 배포 후 smoke test

---

## 프론트 연결 지점

- 프론트 safe 대시보드에서 `/weather/work-stoppage?site_id=` 호출할 예정 (FE-SAFE-02)
- 판례 목록은 추후 프론트 기회 페이지에서 소비
- weather·precedent 시간이 부족하면 SB-03/SB-04 스키마만 먼저 확정하고 다음 스프린트로 미루기 가능. SB-01/SB-02는 반드시 이번에.
