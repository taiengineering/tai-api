# 안전정보 백엔드 작업지시서

> 작성일: 2026-04-11  
> 담당: 백엔드창 (tai-api repo)  
> 우선순위: 높음

---

## 작업 범위

| 파일 | 작업 | 상태 |
|---|---|---|
| `routers/weather.py` | 신규 생성 | ❌ 미개발 |
| `routers/precedent_api.py` | 신규 생성 | ❌ 미개발 |
| `main.py` | 라우터 등록 | 수정 필요 |
| `cron_job_master` | 크론 등록 | 수정 필요 |

---

## 작업 1. routers/weather.py 신규 생성

**prefix:** `/weather`  
**환경변수:** `KMA_SERVICE_KEY` (Railway에 별도 등록됨)

### 사용 API 3종

| API | 엔드포인트 | 용도 |
|---|---|---|
| 기상청 단기예보 | `apis.data.go.kr/1360000/VilageFcstInfoService_2.0` | 풍속·기온·강수량·낙뢰 |
| 기상청 특보 | `apis.data.go.kr/1360000/WthrWrnInfoService` | 강풍·폭염·한파·호우 특보 |
| 기상청 특보구역 | `apis.data.go.kr/1360000/WthrWrnInfoService` | 지역 코드 매핑 |

### 핵심 로직: 위도·경도 → 기상청 격자(nx, ny) 변환

```python
import math

def latlon_to_grid(lat, lon):
    """위도·경도 → 기상청 격자 좌표 변환 (Lambert 투영)"""
    RE = 6371.00877
    GRID = 5.0
    SLAT1, SLAT2 = 30.0, 60.0
    OLON, OLAT = 126.0, 38.0
    XO, YO = 43, 136

    DEGRAD = math.pi / 180.0
    re = RE / GRID
    slat1 = SLAT1 * DEGRAD
    slat2 = SLAT2 * DEGRAD
    olon  = OLON  * DEGRAD
    olat  = OLAT  * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)

    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / (ra ** sn)
    theta = lon * DEGRAD - olon
    if theta > math.pi:  theta -= 2.0 * math.pi
    if theta < -math.pi: theta += 2.0 * math.pi
    theta *= sn

    nx = int(ra * math.sin(theta) + XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + YO + 0.5)
    return nx, ny
```

### 엔드포인트

```python
# GET /weather/now?lat=37.56&lon=126.98
# 현재 날씨 + 작업중지 판단
# 응답 예시:
{
  "location": {"lat": 37.56, "lon": 126.98, "nx": 60, "ny": 127},
  "weather": {
    "wind_speed": 12.3,      # WSD (m/s)
    "temperature": 34.5,     # T1H (°C)
    "rain": 0.0,             # RN1 (mm)
    "lightning": 0,          # LGT (0/1)
    "sky": 4,                # SKY (1맑음/3구름많음/4흐림)
    "pty": 1,                # PTY (0없음/1비/3눈)
    "base_time": "202604110800"
  },
  "work_stop": {
    "required": True,        # 작업중지 필요 여부
    "reasons": [
      {"code": "WIND_HIGH", "msg": "풍속 12.3m/s — 고소작업·타워크레인 작업중지 기준(10m/s) 초과", "law": "산안법 제51조"},
      {"code": "HEAT",      "msg": "기온 34.5°C — 폭염 주의보 수준", "law": "산안법 시행규칙 별표 1"}
    ]
  }
}

# GET /weather/alert?region_code=11
# 특보 조회 (지역코드 기준)

# GET /weather/alert-regions
# 특보구역 코드 목록

# GET /weather/work-stop-criteria
# 작업중지 기준 전체 목록 (법령 근거 포함)
```

### 작업중지 기준 DB (코드 내 상수로 관리)

```python
WORK_STOP_CRITERIA = [
    # 풍속
    {"code": "WIND_HIGH",   "field": "WSD", "op": ">=", "value": 10.0,  "unit": "m/s",
     "work_type": "고소작업·타워크레인", "msg": "풍속 {v}m/s — 작업중지",
     "law": "산업안전보건법 시행규칙 별표 1"},
    {"code": "WIND_CRANE",  "field": "WSD", "op": ">=", "value": 14.0,  "unit": "m/s",
     "work_type": "타워크레인", "msg": "풍속 {v}m/s — 타워크레인 즉시 중단",
     "law": "건설기계 안전기준"},
    # 기온 (폭염)
    {"code": "HEAT_WARN",   "field": "T1H", "op": ">=", "value": 33.0,  "unit": "°C",
     "work_type": "야외작업", "msg": "기온 {v}°C — 폭염 주의보 수준, 옥외작업 단축 권고",
     "law": "산업안전보건법 제51조"},
    {"code": "HEAT_ALERT",  "field": "T1H", "op": ">=", "value": 35.0,  "unit": "°C",
     "work_type": "야외작업", "msg": "기온 {v}°C — 폭염 경보 수준, 옥외작업 중지 권고",
     "law": "산업안전보건법 제51조"},
    # 기온 (한파)
    {"code": "COLD_WARN",   "field": "T1H", "op": "<=", "value": -10.0, "unit": "°C",
     "work_type": "야외작업", "msg": "기온 {v}°C — 한파 경보 수준, 옥외작업 주의",
     "law": "산업안전보건법 제51조"},
    # 낙뢰
    {"code": "LIGHTNING",   "field": "LGT", "op": ">=", "value": 1,     "unit": "",
     "work_type": "철골·고소작업", "msg": "낙뢰 감지 — 즉시 작업중지",
     "law": "건설공사 안전관리 지침"},
    # 강수
    {"code": "RAIN_HEAVY",  "field": "RN1", "op": ">=", "value": 1.0,   "unit": "mm",
     "work_type": "콘크리트 타설", "msg": "강수 {v}mm — 콘크리트 타설 작업 중단",
     "law": "콘크리트 표준시방서"},
]
```

---

## 작업 2. routers/precedent_api.py 신규 생성

**prefix:** `/precedents`  
**환경변수:** 기존 `LAW_API_OC` 재사용 (추가 키 불필요)

### 사용 API
```
GET http://www.law.go.kr/DRF/lawSearch.do?target=prec
  - 전체 산업안전 판례: query=산업안전보건
  - 산재 전용:          query=산재 + datSrcNm=근로복지공단산재판례

GET http://www.law.go.kr/DRF/lawService.do?target=prec&ID={id}
  - 판례 본문 단건 조회
```

### 엔드포인트

```python
GET /precedents/search
  파라미터:
    query: str          # 검색어
    source: str = None  # 'sanjae' → 산재 전용 / None → 전체
    page: int = 1
    size: int = 20

GET /precedents/{prec_id}
  # 판례 본문 단건 조회

POST /precedents/collect
  # 안전 키워드로 일괄 수집 → posts 테이블 저장
  # 키워드: 산업안전보건, 중대재해처벌, 과태료, 산업재해, 안전관리자, 작업중지
  # post_type = 'penalty_case'
  # source = 'comwel_sanjae' 또는 'law_go_kr'
  # 중복 체크: prec_id 기준 UPSERT
```

### posts 테이블 컬럼 추가

```sql
ALTER TABLE posts ADD COLUMN IF NOT EXISTS prec_id VARCHAR(50);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS prec_source VARCHAR(50);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS link_url TEXT;
```

---

## 작업 3. main.py 라우터 등록

```python
from routers.weather       import router as weather_router      # v5.8.1
from routers.precedent_api import router as precedent_router    # v5.8.1
app.include_router(weather_router)
app.include_router(precedent_router)
```
APP_VERSION = `"5.8.1"`

---

## 작업 4. 크론 등록

```sql
INSERT INTO cron_job_master (job_code, cron_expression, endpoint_url, http_method, is_active)
VALUES
  ('PREC_SANJAE_COLLECT', '0 5 * * 1', '/precedents/collect', 'POST', true)
ON CONFLICT (job_code) DO NOTHING;
```

---

## 완료 기준

**weather.py**
- [ ] `GET /weather/now?lat=37.56&lon=126.98` 정상 응답
- [ ] `work_stop.required` + `reasons` 필드 정상 반환
- [ ] `GET /weather/alert?region_code=11` 특보 조회 정상
- [ ] `GET /weather/work-stop-criteria` 기준 목록 반환

**precedent_api.py**
- [ ] `GET /precedents/search?query=산업안전` 정상 응답
- [ ] `GET /precedents/search?source=sanjae&query=산재` 산재 전용 필터 정상
- [ ] `GET /precedents/{id}` 본문 정상
- [ ] `POST /precedents/collect` → posts 저장 확인
- [ ] 크론 등록 확인
