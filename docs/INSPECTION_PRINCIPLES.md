# TAI Safe 서비스 점검 원칙

> 모든 기능 구현 시 이 원칙에 따라 점검 코드를 함께 만든다.
> 새 라우터/서비스 추가 시 반드시 이 문서를 참조한다.

---

## 1. 점검 체계: 3계층

```
Layer 1 — 인프라 (서버가 살아있는가?)
  도구: UptimeRobot (1분마다)
  체크: /health 200
  알림: 3회 연속 실패 시 SMS

Layer 2 — 서비스 (기능이 동작하는가?)
  도구: /health/deep (6시간마다, GitHub Actions)
  체크: 등록된 모든 프로브 자동 실행
  알림: 실패 시 SMS + 한글 메시지

Layer 3 — 데이터 (결과가 정확한가?)
  도구: pg_cron (6시간마다)
  체크: 교차 검증, 정합성, 누락 데이터
  알림: 일일 요약
```

---

## 2. 점검 기준: 사용자 행동 단위

모든 서비스 페이지는 3가지 행동으로 구성된다:

```
① 읽기 (LIST/READ)  — 페이지를 열면 데이터가 보이는가?
② 쓰기 (CREATE)     — 새 데이터를 저장할 수 있는가?
③ 수정 (UPDATE)     — 기존 데이터를 변경할 수 있는가?

이 3가지가 되면 → 서비스 정상
이 중 하나라도 안 되면 → 서비스 장애
```

### 체크 레벨

```
Level 1 (연결): DB 테이블에 접근 가능한가? → SELECT count
Level 2 (동작): API를 호출하면 올바른 응답이 오는가? → 200 + 올바른 구조
Level 3 (흐름): 사용자의 핵심 동선이 끝까지 완료되는가? → E2E
```

### 프로브 등록 시 필수 포함 사항

```python
register_probe(
    name="서비스명",           # 영문 식별자
    fn=_probe_function,       # 체크 함수
    critical=True/False,      # 실패 시 전체 장애 여부
    desc_ko="한글 설명",       # SMS/알림에 표시
    meta={
        "impacts": [...],     # 영향받는 페이지/기능
        "fix_links": [...],   # 수정 링크 (Railway, Supabase 등)
        "api": "...",         # 관련 API 엔드포인트
        "code": "...",        # 관련 코드 파일
    }
)
```

---

## 3. 새 기능 추가 시 필수 절차

### 라우터/서비스 추가 시

```
1. 기능 코드 작성
2. 서비스 파일 하단에 register_probe 추가
   - Level 1: 최소한 테이블 접근 확인
   - Level 2: 가능하면 실제 API 동작 확인
3. meta에 impacts, fix_links 포함
4. health_registry.py의 ERROR_MESSAGES_KO에 한글 에러 메시지 추가
5. → /health/deep에 자동 포함. yml 수정 불필요.
```

### 프론트엔드 페이지 추가 시

```
1. 해당 페이지의 API 의존성 파악
2. 해당 API의 프로브가 있는지 확인
3. 없으면 프로브 추가
4. meta.impacts에 새 페이지 URL/경로 추가
```

---

## 4. 놓치기 쉬운 것들 — 정기 점검 항목

### 매주 확인

```
□ 백그라운드 작업: pg_cron, Edge Function 정상 실행 여부
□ 외부 의존성: 기상청 API, KG이니시스, MessageMi 연결 상태
□ 데이터 정합성: 교차 참조 깨진 것 없는지 (orphan records)
□ 응답 시간: 3초 초과 API 있는지 (/health/deep latency_ms)
```

### 매월 확인

```
□ RLS 적용 누락 테이블 없는지 (Issue #61)
□ 라우터 목록 vs 프로브 목록 대조 (누락 프로브 확인)
□ SSL 인증서 만료 확인
□ Supabase/Railway 사용량 확인
```

---

## 5. 알림 원칙

```
정상 시: 알림 0통 (아무것도 안 오면 좋은 것)
장애 시: SMS 1통 즉시 (한글, 영향 범위 포함)
        15분 쿨다운 (같은 장애 반복 알림 방지)
복구 시: SMS 1통 (정상 복구 알림)

메일: 실패 시에만 (GitHub Actions)
      성공 메일 = 보내지 않음
```

---

## 6. 멀티테넌시 원칙

```
아키텍처: 공유 DB + 공유 테이블 + company_id 분리
격리: Supabase RLS (서버 레벨 강제)
API: 모든 쿼리에 WHERE company_id 필수
테스트: anon key로 다른 회사 데이터 접근 불가 확인
```

---

## 7. 프로브 체크 체인

```
사용자 → 프론트 → API → 서비스 로직 → DB → 응답
                                        ↓
                              외부 의존 (PDF, SMS, PG)

체크 포인트:
  ① 프론트: URL 접근 가능 (HTTP 200)
  ② API: 엔드포인트 응답 (200 + 올바른 구조)
  ③ DB: 테이블 접근 + 데이터 존재
  ④ 외부: 연결 상태 (환경변수 + 핑)
  ⑤ 성능: 응답 시간 3초 이내
```

---

## 8. 이 문서의 적용

```
기획창 (Claude): 작업지시 작성 시 이 원칙 포함
Cursor/Code: 코드 작성 시 register_probe 함께 구현
DEV_RULES_SERVICE_LAYER.md: 서비스 분리 시 프로브 포함
README_HEALTH_PROBE.md: 프로브 작성 가이드 (이미 존재)
```

이 문서는 TAI Safe의 모든 기능 개발에 적용되는 필수 참조 문서이다.
