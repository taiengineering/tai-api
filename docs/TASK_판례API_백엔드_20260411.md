# 판례 API 백엔드 작업지시서

> 작성일: 2026-04-11  
> 담당: 백엔드창 (tai-api repo)  
> 우선순위: 중간

---

## 배경

두 가지 판례 데이터를 TAI 안전정보 콘텐츠로 수집한다.

| 소스 | 특징 | API |
|---|---|---|
| **법제처 판례** (law.go.kr) | 산업안전·중대재해 관련 전체 판례 | 이미 신청 완료 / 동일 OC 키 사용 |
| **근로복지공단 산재판례** | 산재 전문 판례 (신청 예정) | 동일 엔드포인트, datSrcNm 파라미터 구분 |

**핵심:** 두 API 모두 `http://www.law.go.kr/DRF/lawSearch.do?target=prec` 동일 엔드포인트.
`datSrcNm=근로복지공단산재판례` 파라미터 하나로 산재 판례만 필터링 가능.
→ 라우터 하나로 두 소스 통합 처리.

---

## API 명세 (law.go.kr)

### 판례 목록 조회
```
GET http://www.law.go.kr/DRF/lawSearch.do
  ?OC={인증값}      ← LAW_API_OC 환경변수 (기존 taieng)
  &target=prec
  &type=JSON
  &query={검색어}   ← 예: 산업안전, 중대재해, 과태료
  &datSrcNm={소스} ← 근로복지공단산재판례 | (생략시 전체)
  &display=20
  &page=1
  &sort=ddes        ← 최신순
```

### 판례 본문 조회
```
GET http://www.law.go.kr/DRF/lawService.do
  ?OC={인증값}
  &target=prec
  &type=JSON
  &ID={판례일련번호}
```

### 주요 응답 필드
- 목록: 판례일련번호, 사건명, 사건번호, 선고일자, 법원명, 판결유형, 데이터출처명, 판례상세링크
- 본문: 사건명, 사건번호, 선고일자, 법원명, 판시사항, 판결요지, 참조조문, 판례내용

---

## 작업 1. routers/precedent_api.py 신규 생성

**prefix:** `/precedents`

```
GET /precedents/search              판례 목록 검색
GET /precedents/{prec_id}          판례 본문 단건 조회
POST /precedents/collect            키워드 기반 수집 → posts 저장
GET /precedents/safety-keywords     산업안전 키워드 자동 수집 결과
```

### 엔드포인트 상세

**GET /precedents/search**
```python
파라미터:
  query: str         # 검색어 (예: 산업안전, 중대재해, 과태료)
  source: str = None # 'sanjae' → datSrcNm=근로복지공단산재판례
                     #  None → 전체
  page: int = 1
  size: int = 20
  sort: str = 'ddes' # 최신순
```

**POST /precedents/collect**
```python
# 크론 또는 수동 실행
# 아래 키워드로 두 소스 모두 수집 → posts 테이블 저장
SAFETY_KEYWORDS = [
    '산업안전보건',
    '중대재해처벌',
    '과태료',
    '산업재해',
    '안전관리자',
    '작업중지',
]

저장 방식:
  post_type = 'penalty_case' (판례·과태료)
  sector_tag = 업종 자동 추출 (건설/제조/시설)
  source = 'law_go_kr' 또는 'comwel_sanjae'
  원문 링크: 판례상세링크 필드 활용
  중복 체크: 판례일련번호 기준 UPSERT
```

---

## 작업 2. posts 테이블 컬럼 확인

아래 컬럼이 없으면 추가:
```sql
ALTER TABLE posts ADD COLUMN IF NOT EXISTS prec_id VARCHAR(50);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS prec_source VARCHAR(50);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS prec_link TEXT;
```

---

## 작업 3. main.py 등록

```python
from routers.precedent_api import router as precedent_router  # v5.8.1
app.include_router(precedent_router)
```
APP_VERSION = `"5.8.1"`

---

## 작업 4. 크론 등록

cron_job_master 테이블에 아래 INSERT:
```sql
INSERT INTO cron_job_master (job_code, cron_expression, endpoint_url, http_method, is_active)
VALUES
  ('PREC_COLLECT_WEEKLY', '0 5 * * 1', '/precedents/collect', 'POST', true)
ON CONFLICT (job_code) DO NOTHING;
```
→ 매주 월요일 05:00 자동 수집

---

## 완료 기준

- [ ] `GET /precedents/search?query=산업안전` 응답 정상
- [ ] `GET /precedents/search?query=산재&source=sanjae` 산재 판례만 반환
- [ ] `GET /precedents/{id}` 본문 응답 정상
- [ ] `POST /precedents/collect` 실행 → posts 테이블 저장 확인
- [ ] 크론 등록 확인
