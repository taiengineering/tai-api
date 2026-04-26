## 🔴 KOSHA API APICODE_ERROR (미해결)

### 증상
모든 KOSHA API 호출 시 아래 응답 반환:
```json
{"status":"success","data":{"header":{"resultCode":"90","resultMsg":"APICODE_ERROR"}}}
```

### 원인 분석
- `resultCode 90` = **해당 키 계정에서 API 서비스가 활용 중이지 않은 상태**
- 현재 사용 키: `da4e8263...` (`BUILDING_API_KEY` = `DATA_GO_KR_SERVICE_KEY` 동일 값)
- 키 자체는 유효하나, 이 키 계정에서 KOSHA API 활용신청이 활성화되지 않은 것으로 추정

### 확인 필요 사항
1. 공공데이터포털(data.go.kr) → 마이페이지 → 오픈API → **개발계정 활용현황**
2. 아래 API 상태가 **"활용"** 인지 확인:
   - `한국산업안전보건공단_국내재해사례 게시판 정보 조회서비스`
   - `한국산업안전보건공단_안전보건자료 링크 서비스`
   - `한국산업안전보건공단_건설업종 일별 중대재해 현황`
   - `한국산업안전보건공단_건설현장 안전 신호등`
   - `한국산업안전보건공단_KOSHA GUIDE`

3. 브라우저 직접 테스트 (키 교체 후 접속):
   ```
   https://apis.data.go.kr/B552468/disaster_api02/getdisaster_api02?serviceKey=da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b&callApiId=국내재해사례 게시판 조회&pageNo=1&numOfRows=3
   ```

### 해결 후 즉시 실행
```bash
# 2024년~현재 전체 초기 수집
POST https://api.taieng.co.kr/kosha-collect/run?since_year=2024&background=true
```

### 관련 파일
- `routers/kosha_apis.py` v1.5.1
- `routers/kosha_collect.py` v1.1.0
- pg_cron: `kosha-signal-*` (3개), `kosha-accident-daily`, `kosha-weekly` 등록 완료

### 참고: 크론 등록 현황 (해결 즉시 자동 가동)
| 크론명 | 스케줄 (KST) | 대상 |
|--------|------------|------|
| kosha-signal-morning | 매일 06:00 | 건설현장 신호등 |
| kosha-signal-noon | 매일 12:00 | 건설현장 신호등 |
| kosha-signal-evening | 매일 18:00 | 건설현장 신호등 |
| kosha-accident-daily | 매일 02:00 | 국내재해사례 |
| kosha-weekly | 매주 월 03:00 | 안전자료·가이드 등 |
