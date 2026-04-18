# 작업지시서: 카카오 API 완전 제거

**작성일:** 2026-04-14  
**우선순위:** 즉시  
**지시자:** TAI Fix 설계 창  

---

## 배경

대표 결정: **카카오 API 전면 사용 금지.** 주소검색, 지도, 로그인, 알림톡 등 모든 카카오 관련 API/SDK 사용하지 않음.

- 주소검색 → 행정안전부 도로명주소 API (juso.go.kr)
- 알림 → 메세지미(MessageMi) 유지

## 즉시 조치 사항

### 1. `routers/juso.py` — 전체 교체 (최우선)

**현재:** 카카오 로컬 API (`dapi.kakao.com/v2/local/search/address.json`) 직접 호출  
**변경:** 행정안전부 도로명주소 API (`www.juso.go.kr/addrlink/addrLinkApi.do`) 사용

**교체 내용:**
- `KAKAO_REST_API_KEY` 환경변수 → `JUSO_CONFIRM_KEY` (행안부 API 승인키)
- 카카오 API URL → juso.go.kr API URL
- 응답 파싱 로직 변경 (행안부 API 응답 구조에 맞게)
- 좌표 변환이 필요하면 네이버 Geocoding API 또는 행안부 좌표제공 API 사용

**엔드포인트 유지:**
- `GET /juso/coord?query=주소` → 동일 응답 구조 유지
- `GET /juso/search?query=주소` → 동일

**행안부 도로명주소 API 참고:**
- 신청: https://www.juso.go.kr/addrlink/devAddrLinkRequestWrite.do
- 문서: https://www.juso.go.kr/addrlink/devAddrLinkRequestGuide.do
- 요청: `GET /addrlink/addrLinkApi.do?confmKey=KEY&keyword=주소&resultType=json`
- 응답: `results.juso[0].roadAddr` (도로명), `results.juso[0].jibunAddr` (지번)

### 2. Fly.io 환경변수

- `KAKAO_REST_API_KEY` 삭제
- `JUSO_CONFIRM_KEY` 추가 (행안부 API 승인키)

### 3. 프론트엔드 확인

카카오 주소검색 SDK(`postcode.js` 등)를 사용하는 프론트 페이지가 있으면 제거.
프론트에서 주소검색은 백엔드 `/juso/search` API를 호출하는 방식으로 통일.

## 보류 사항 (건드리지 않음)

- `notifications.py`의 kakao 채널 참조 → MessageMi 경유이므로 유지
- `users` 테이블의 `kakao_id`, `allow_kakao` 컬럼 → DB 구조 변경은 별도
- docs/ 폴더의 문서들 → 기록이므로 유지

## 완료 조건

- [ ] `juso.py`가 행안부 API로 동작
- [ ] `KAKAO_REST_API_KEY` 환경변수 삭제
- [ ] `/juso/coord`, `/juso/search` 정상 응답 확인
- [ ] 프론트에서 카카오 SDK 직접 호출 없음 확인
