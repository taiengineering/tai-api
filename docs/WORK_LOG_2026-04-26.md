# 작업 내역 — 2026-04-26

## 완료 작업

### 1. 법령 내부 뷰어 구축 (taieng 레포)
- **신규:** `nexas/law-view.html`
  - URL: `/law-view.html?id={law_master.id}` 또는 `?mst={law_mst_no}`
  - `law_master` → `law_version(is_current)` → `law_article` + `law_paragraph` 조회
  - 조문 번호순 표시, 실시간 검색, 펼침/닫힘
- **변경:** `law_revision_board.source_url` 일괄 업데이트
  - 94건: `https://new.taieng.co.kr/law-view.html?id={uuid}` 내부 뷰어
  - 1건 (건설업 산안관리비 행정규칙): `law.go.kr` 유지

---

### 2. law-updates.html 전면 개편 (taieng 레포)
- **데이터소스 변경:** `law_version` + `law_master` (3테이블 조인) → `law_revision_board` 단일 테이블
- **링크 내부화:** "국가법령정보센터에서 원문 보기" (외부) → "조문 전체 보기" (내부 law-view.html)
- **개정 조문 요약 표시:** `body` 필드 — XML xpath로 파싱한 변경 조문 목록
- **영향도 필터 추가:** 높음 / 보통 / 낮음

---

### 3. 개정 조문 요약 생성 (Supabase SQL)
- `law_content_raw.raw_xml` XML xpath로 `<조문변경여부>Y</조문변경여부>` 파싱
- 83/95건 `law_revision_board.body` 업데이트 완료
- 형식:
  ```
  ■ 개정 개요
  일부개정 (2026.02.27 공포, 2026.02.27 시행)

  ■ 변경된 조문 (8개)
  • 제8조(건축허가서 등)
  • 제12조(건축신고)
  ...

  ■ 적용 영향
  법령 일부 조항이 개정되었습니다.
  ```

---

### 4. KOSHA API 라우터 v1.5.0 → v1.5.1 (tai-api main)

**v1.5.0 신규 엔드포인트:**
- `GET /kosha/construction-safety-light` — 건설현장 안전 신호등 (시도/시군구/현장명/신호 필터)
- `GET /kosha/risk-assessment-accredited` — 위험성평가 인정사업장 (사업장명/시도/업종 필터)
- `GET /kosha/accident-cases/attachments` — 국내재해사례 첨부파일 경로

**v1.5.1 키 우선순위 변경:**
```python
# 이전: KOSHA_SERVICE_KEY > BUILDING_API_KEY
# 변경: DATA_GO_KR_SERVICE_KEY > KOSHA_SERVICE_KEY > BUILDING_API_KEY
def _get_service_key() -> str:
    return (
        os.getenv("DATA_GO_KR_SERVICE_KEY")
        or os.getenv("KOSHA_SERVICE_KEY")
        or os.getenv("BUILDING_API_KEY", "")
    )
```

---

### 5. KOSHA 수집 라우터 v1.1.0 (tai-api main)
- 동일한 키 우선순위 적용
- `/kosha-collect/status` 응답에 `key_hint` 추가 (디버깅용 — 앞 8자리)

---

### 6. pg_cron KOSHA 수집 크론 등록 (Supabase)
| 크론명 | 스케줄 (UTC) | 대상 |
|--------|------------|------|
| kosha-signal-morning | 매일 21:00 (= KST 06:00) | 건설현장 신호등 |
| kosha-signal-noon    | 매일 03:00 (= KST 12:00) | 건설현장 신호등 |
| kosha-signal-evening | 매일 09:00 (= KST 18:00) | 건설현장 신호등 |
| kosha-accident-daily | 매일 17:00 (= KST 02:00) | 국내재해사례 |
| kosha-weekly         | 매주 일 18:00 (= 월 KST 03:00) | 안전자료·가이드 등 |

---

### 7. 안전정보 페이지 전면 개편 (taieng 레포)
- **파일:** `nexas/safety-news.html`
- **구조:** 탭 기반 6개 섹션

| 탭 | API 엔드포인트 | 필터 |
|----|--------------|------|
| 국내 재해사례 | `GET /kosha/accident-cases` | 업종 (제조/건설/조선/서비스/기타) |
| 건설현장 신호등 | `GET /kosha/construction-safety-light` | 🔴위험/🟡주의/🟢양호 |
| 안전보건자료 | `GET /kosha/safety-materials` | 업종 |
| 건설 중대재해 | `GET /kosha/construction-accidents` | — |
| 위험성평가 인정 | `GET /kosha/risk-assessment-accredited` | — |
| KOSHA GUIDE | `GET /kosha/kosha-guide` | 분야 (G/M/C/B/H) |

- 탭 클릭 시 해당 섹션만 로드 (지연 로딩)
- "더 보기" 페이지네이션
- 건설현장 신호등: RED/YELLOW/GREEN 시각적 구분
- 위험성평가 인정: 만료임박 뱃지 자동 표시

---

## 🔴 미해결 이슈 — KOSHA API APICODE_ERROR

### 증상
```json
{"status":"success","data":{"header":{"resultCode":"90","resultMsg":"APICODE_ERROR"}}}
```

### 진단
- 현재 사용 키 힌트: `da4e8263...` (`BUILDING_API_KEY` 값)
- `DATA_GO_KR_SERVICE_KEY`가 Railway에 있으나 값이 `BUILDING_API_KEY`와 동일하거나 비어있어 폴백됨
- `APICODE_ERROR (90)` = **해당 키 계정에서 이 API 서비스가 활용중이지 않은 상태**

### 확인 필요
1. **공공데이터포털** → 마이페이지 → 오픈API → **개발계정 활용현황** 접속
2. 아래 API들이 목록에 있고 상태가 "활용"인지 확인:
   - 국내재해사례 게시판 정보 조회서비스
   - 안전보건자료 링크 서비스
   - 건설업종 일별 중대재해 현황
   - 건설현장 안전 신호등
   - KOSHA GUIDE
3. **브라우저 직접 테스트:**
   ```
   https://apis.data.go.kr/B552468/disaster_api02/getdisaster_api02?serviceKey={본인키}&callApiId=국내재해사례 게시판 조회&pageNo=1&numOfRows=3
   ```

### 해결 후 할 일
```
POST https://api.taieng.co.kr/kosha-collect/run?since_year=2024&background=true
```
한 번 호출 → 2024년~ 전체 수집 시작 → pg_cron이 이후 자동 갱신

---

## 관련 파일 변경 요약

| 레포 | 파일 | 변경 내용 |
|------|------|---------|
| taieng | `nexas/law-view.html` | 신규 — 내부 법령 조문 뷰어 |
| taieng | `nexas/law-updates.html` | 전면 개편 — DB 직접 조회, 링크 내부화, 개정 조문 요약 |
| taieng | `nexas/safety-news.html` | 전면 개편 — KOSHA 6개 섹션 탭 구조 |
| tai-api | `routers/kosha_apis.py` | v1.5.1 — 신규 엔드포인트 3개, 키 우선순위 수정 |
| tai-api | `routers/kosha_collect.py` | v1.1.0 — 키 우선순위 수정, key_hint 추가 |
| Supabase | `law_revision_board` | source_url 내부화 94건, body(개정조문요약) 83건 업데이트 |
| Supabase | `cron.job` | KOSHA 수집 크론 5개 등록 |
