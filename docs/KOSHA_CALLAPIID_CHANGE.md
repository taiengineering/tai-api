# KOSHA callApiId 변경 이력 (2026-04-30 확인)

## 변경된 callApiId 값

| API | 이전 callApiId | 신규 callApiId | 상태 |
|---|---|---|---|
| 안전보건자료 | `1030` | `1030` (변경 없음) | ✅ |
| 국내재해사례 | `"국내재해사례 게시판 조회"` | **`1040`** | ✅ 수정 |
| 건설 중대재해 | `1010` | **`1050`** | ✅ 수정 |
| 건설안전신호등 | `1020` | 모든 값 실패 | ❌ KOSHA 서버 장애 |
| 위험성평가 | 없음 | 모든 값 실패 | ❌ KOSHA 서버 장애 |
| KOSHA GUIDE | 폐기됨 | 스마트검색 대체 | ✅ |

## 발견 경위

2026-04-30 data.go.kr 문서 확인 + callApiId 범위 스캔(1000~1100)으로 확인.
KOSHA 포털 개편 이후 callApiId 체계가 숫자로 통일된 것으로 보임.

## 테스트 URL

```
# 국내재해사례 (1040)
https://api.taieng.co.kr/kosha/debug-raw/test?path=disaster_api02/getdisaster_api02&call_api_id=1040&num_of_rows=2

# 건설 중대재해 (1050)
https://api.taieng.co.kr/kosha/debug-raw/test?path=constDsstr01/getconstDsstr01&call_api_id=1050&num_of_rows=2
```
