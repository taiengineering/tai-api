# TAI Agent — 백엔드 작업지시서

> 작성일: 2026-04-11
> 담당: 백엔드창 (tai-api repo)
> 우선순위: 높음

---

## 배경 및 결정사항

**TAI Agent** = 수선연결 + 대행연결 통합 서비스

법령진단 리포트를 받은 고객이 "직접 처리할 수 없는 항목"을 외부 전문업체에 맡기는 흐름:

```
법령진단 리포트
├── 선임 의무  → TAI Manager (선임연결)
├── 점검 의무  → TAI Safe SaaS (운영관리)
├── 서류/인허가 → TAI Agent (대행연결) ★ 신규
└── 수선 의무  → TAI Agent (수선연결) ★ 기존 → 통합
```

수선연결과 대행연결을 **TAI Agent** 단일 브랜드로 통합.
기존 `connection_commission` 테이블의 `service_type: 'repair'` 유지,
`service_type: 'agency'` 신규 추가.

---

## 작업 1. DB — agent_service 테이블 생성

대행 서비스 목록을 관리하는 테이블.
(수선은 기존 connection_commission 테이블 그대로 사용)

```sql
CREATE TABLE IF NOT EXISTS agent_service (
  id           SERIAL PRIMARY KEY,
  sector       VARCHAR(20) NOT NULL,  -- 'construction' | 'facility' | 'industrial'
  service_code VARCHAR(50) NOT NULL UNIQUE,
  service_name VARCHAR(100) NOT NULL,  -- 서비스명 (예: '유해위험방지계획서')
  price        INTEGER NOT NULL DEFAULT 0,  -- 0 = 별도문의, -1 = 협의
  price_display VARCHAR(50),           -- 표시문구 (예: '200만원~', '별도문의')
  legal_basis  VARCHAR(200),           -- 법적 근거 (예: '산업안전보건법 제42조')
  is_active    BOOLEAN NOT NULL DEFAULT true,
  sort_order   INTEGER NOT NULL DEFAULT 0,
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);
```

**초기 데이터 삽입:**

```sql
INSERT INTO agent_service
  (sector, service_code, service_name, price, price_display, legal_basis, sort_order)
VALUES
  -- 건설 분야
  ('construction','HAZARD_PLAN',       '유해위험방지계획서',        2000000, '200만원~',  '산업안전보건법 제42조', 1),
  ('construction','SAFETY_PLAN_SMALL', '안전관리계획서 (중외)',      1500000, '150만원~',  '건설기술진흥법 제62조', 2),
  ('construction','SAFETY_PLAN_LARGE', '안전관리계획서 (1,2종)',     2000000, '200만원~',  '건설기술진흥법 제62조', 3),
  ('construction','EDU_SAFETY_EVAL',   '교육시설 안전성평가',        1500000, '150만원~',  '교육시설 안전 및 유지관리 등에 관한 법률', 4),
  ('construction','BASIC_SHE_PLAN',    '기본안전보건대장',           500000,  '50만원~',   '건설기술진흥법 제67조', 5),
  ('construction','DESIGN_SHE_PLAN',   '설계안전보건대장',           1000000, '100만원~',  '건설기술진흥법 제67조', 6),
  ('construction','CONST_SHE_PLAN',    '공사안전보건대장',           800000,  '80만원~',   '건설기술진흥법 제67조', 7),
  ('construction','RAILWAY_SAFETY',    '철도보호지구 안전관리계획서',1000000, '100만원~',  '철도안전법 제45조', 8),
  ('construction','QUALITY_TEST',      '품질시험관리계획서',          500000,  '50만원~',   '건설기술진흥법 제55조', 9),
  ('construction','DFS',               '설계안전성검토 (DFS)',        1500000, '150만원~',  '건설기술진흥법 제75조', 10),
  ('construction','DEMOLISH_PLAN',     '해체계획서',                 0,       '별도문의',  '건축물관리법 제30조', 11),
  ('construction','TEMP_STRUCT',       '가시설구조검토',             0,       '별도문의',  '건설기술진흥법', 12),
  -- 산업 분야
  ('industrial', 'SAFETY_MGMT',        '안전관리 대행',              0,       '별도문의',  '산업안전보건법 제17조', 1),
  ('industrial', 'HEALTH_MGMT',        '보건관리 대행',              0,       '별도문의',  '산업안전보건법 제18조', 2),
  ('industrial', 'WORK_ENV_MEASURE',   '작업환경측정',               0,       '별도문의',  '산업안전보건법 제125조', 3),
  ('industrial', 'HEALTH_CHECKUP',     '특수건강검진',               0,       '별도문의',  '산업안전보건법 제130조', 4),
  ('industrial', 'LEGAL_INSPECTION',   '법정 안전검사 (크레인·압력용기 등)', 0, '별도문의', '산업안전보건법 제93조', 5),
  ('industrial', 'CHEM_RISK_ASSESS',   '화학물질 위험성평가',        0,       '별도문의',  '화학물질관리법', 6),
  ('industrial', 'PSM',                '공정안전보고서 (PSM)',        0,       '별도문의',  '산업안전보건법 제44조', 7),
  -- 건물·시설 분야
  ('facility',   'FIRE_MGMT',          '소방안전관리 대행',          0,       '별도문의',  '화재예방법 제24조', 1),
  ('facility',   'ELEC_MGMT',          '전기안전관리 대행',          0,       '별도문의',  '전기안전관리법 제22조', 2),
  ('facility',   'GAS_MGMT',           '가스안전관리 대행',          0,       '별도문의',  '고압가스안전관리법', 3),
  ('facility',   'FIRE_INSPECT',       '소방시설 점검',              0,       '별도문의',  '화재예방법 제22조', 4),
  ('facility',   'ELEC_INSPECT',       '전기안전점검',               0,       '별도문의',  '전기안전관리법', 5),
  ('facility',   'ELEVATOR_INSPECT',   '승강기 안전검사',            0,       '별도문의',  '승강기 안전관리법 제32조', 6)
ON CONFLICT (service_code) DO NOTHING;
```

---

## 작업 2. API — routers/agent_service.py 신규 생성

**prefix:** `/agent-service`

```
GET  /agent-service              전체 목록 (sector 필터)
GET  /agent-service/{id}         단건 조회
PATCH /agent-service/{id}        가격·표시문구 수정 (어드민)
```

**응답 필드:** `id, sector, service_code, service_name, price, price_display, legal_basis, is_active, sort_order`

**공개 API** (인증 불필요) — new.taieng.co.kr에서 직접 호출.

---

## 작업 3. main.py 등록

```python
from routers.agent_service import router as agent_service_router  # v5.8.0

app.include_router(agent_service_router)
```

APP_VERSION = `"5.8.0"`

---

## 작업 4. 어드민 price-setting.html — TAI Agent 탭 추가

`admin/full-version/html/horizontal-menu-template-no-customizer/price-setting.html`

**탭 추가:**
```
[법령진단 가격] [SaaS 요금제] [선임 수수료] [수선 수수료] [TAI Agent 대행] [미확정 항목]
```

**TAI Agent 대행 탭 구조:**
- 섹터 탭: [건설] [산업] [건물·시설]
- 각 섹터별 서비스 목록 테이블
- 컬럼: 서비스명 | 가격(원) | 표시문구 | 저장
- `GET /agent-service?sector=construction` 으로 로드
- `PATCH /agent-service/{id}` 로 저장

---

## 완료 기준

- [ ] `agent_service` 테이블 생성 + 초기 데이터 28건 삽입
- [ ] `GET /agent-service` 응답 정상
- [ ] `PATCH /agent-service/{id}` 저장 정상
- [ ] main.py v5.8.0 등록
- [ ] 어드민 price-setting.html TAI Agent 탭 추가
