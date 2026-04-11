# 근로복지공단 산재보험 판례 판결문 API — 백엔드 작업지시서

> 작성일: 2026-04-11  
> 담당: 백엔드창 (tai-api repo)  
> 우선순위: 중간  
> API 승인일: 2026-04-11 / 만료: 2028-04-11

---

## 배경

law.go.kr 판례 API에 `datSrcNm=근로복지공단산재판례` 파라미터로
산재 전용 판례만 필터링 가능 — **별도 엔드포인트·키 불필요**.

기존 `law_collector.py`에서 사용 중인 `LAW_API_OC` 환경변수 그대로 재사용.

---

## API 명세

### 판례 목록 조회
```
GET http://www.law.go.kr/DRF/lawSearch.do
  ?OC={LAW_API_OC}
  &target=prec
  &type=JSON
  &query={검색어}
  &datSrcNm=근로복지공단산재판례   ← 산재 전용 필터
  &display=20
  &page=1
  &sort=ddes
```

### 판례 본문 조회
```
GET http://www.law.go.kr/DRF/lawService.do
  ?OC={LAW_API_OC}
  &target=prec
  &type=JSON
  &ID={판례일련번호}
```

### 응답 주요 필드 (목록)
`판례일련번호, 사건명, 사건번호, 선고일자, 법원명, 판결유형, 데이터출처명, 판례상세링크`

### 응답 주요 필드 (본문)
`판시사항, 판결요지, 참조조문, 판례내용`

---

## 작업 1. routers/precedent_api.py 신규 생성

**prefix:** `/precedents`

### 엔드포인트

```python
GET  /precedents/search
  # 파라미터: query(str), source(str='sanjae'|None), page(int), size(int)
  # source='sanjae' → datSrcNm=근로복지공단산재판례 추가
  # source=None → datSrcNm 없음 (전체 법제처 판례)

GET  /precedents/{prec_id}
  # 판례 본문 단건 조회

POST /precedents/collect
  # 안전 키워드로 산재판례 일괄 수집 → posts 테이블 저장
  # 키워드: ['산업안전보건', '중대재해처벌', '과태료', '산업재해', '안전관리자', '작업중지']
  # post_type='penalty_case', source='comwel_sanjae'
  # 중복 체크: 판례일련번호 기준 UPSERT
```

### posts 테이블 저장 형식
```python
{
  "title":      사건명,
  "content":    판결요지 (본문 조회 후),
  "post_type":  "penalty_case",
  "sector_tag": 업종 자동 추출 (건설/산업/시설),
  "source":     "comwel_sanjae",
  "link_url":   판례상세링크,
  "prec_id":    판례일련번호,  # 중복 방지용
  "published_at": 선고일자,
}
```

---

## 작업 2. posts 테이블 컬럼 추가 (없으면)

```sql
ALTER TABLE posts ADD COLUMN IF NOT EXISTS prec_id VARCHAR(50);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS prec_source VARCHAR(50);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS link_url TEXT;
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

```sql
INSERT INTO cron_job_master (job_code, cron_expression, endpoint_url, http_method, is_active)
VALUES ('PREC_SANJAE_COLLECT', '0 5 * * 1', '/precedents/collect', 'POST', true)
ON CONFLICT (job_code) DO NOTHING;
```
→ 매주 월요일 05:00 자동 수집

---

## 완료 기준

- [ ] `GET /precedents/search?query=산재&source=sanjae` 응답 정상
- [ ] `GET /precedents/search?query=산업안전` 전체 판례 응답 정상
- [ ] `GET /precedents/{id}` 본문 응답 정상
- [ ] `POST /precedents/collect` → posts 테이블 저장 확인
- [ ] 크론 등록 확인
