# WORK ORDER 2026-04-24 · PWA 백엔드 보강 (P0)

- **대상**: Claude Code (백엔드창)
- **레포/브랜치**: `tai-api` / `dev`
- **배포**: `dev` → main merge → Railway Singapore 자동 배포
- **관련 리뷰 문서**: `tai-admin/docs/PWA_APP_REVIEW_20260424.md`
- **프론트 지시서**: `tai-admin/docs/WORK_ORDER_20260424_pwa_frontend.md`
- **의존 관계**: **프론트 P0-1~P0-3은 이 작업 완료/배포 후 연동 가능**

---

## 필수 준수 규칙

1. `/health` 절대 503 금지 — 실패 시 "degraded" 반환
2. 200+ 라인 파일 MCP 수정 금지 → Cursor/Claude Code 사용
3. `from db.supabase_client import get_supabase` 패턴 유지
4. **Service Layer 분리 규칙** (20KB+ 라우터는 수정 전 분리):
   - 본 작업 대상 중 경계선: `tbm.py` (17.7KB) — 500B 미만 순증이면 유지 OK, 초과 예상 시 선제 분리
   - `inspection_sets.py` (38KB) 본 작업 미수정
   - 새 파일/새 엔드포인트는 처음부터 Router/Service/Schema 구조로
5. 커밋 전 로컬 `/health` + 신규 엔드포인트 smoke test

---

## 배경

프론트 PWA 점검 결과 긴급신고·이상신고·작업자점검에서 다음 확인:

- 사진을 Base64로 JSON body에 담아 전송 → 413 위험 + 서버 저장 로직 없음
- `/emergency/report`, `/safety-reports`, `/worker-check/submit`, `/tbm/sign` Authorization 검증 미확인
- 신고번호를 프론트에서 `Date.now()`로 생성 — 서버 DB와 매칭 불가
- FCM 알림 트리거가 백엔드에서 연동됐는지 불명

**본 작업 목적**: 프론트가 (a) Authorization 헤더 부착, (b) 사진을 URL로 전송, (c) 서버가 발급한 신고번호 수령하도록 백엔드 계약 정비.

---

## TASK 1. 사진 업로드 엔드포인트 신설 (최우선)

### 신규 엔드포인트
```
POST /uploads/inspection-photo
Authorization: Bearer {access_token}  (필수)
Content-Type: multipart/form-data

form fields:
  file: 파일 (image/jpeg, image/png, image/webp만 허용)
  context: 'inspection' | 'report' | 'emergency' | 'tbm'
  inspection_id: UUID (선택)
  factory_id: UUID (선택)
  site_id: UUID (선택)

제약:
  - 파일당 최대 5MB
  - 허용 MIME: image/jpeg, image/png, image/webp
  - 확장자 서버 측 검증 필수 (Content-Type 신뢰 금지)

응답 200:
{
  "url": "https://xntdkrjhgcscmqctdzyo.supabase.co/storage/v1/object/public/inspections/...",
  "path": "inspections/2026/04/24/{inspection_id}/001.jpg",
  "size": 234567,
  "mime": "image/jpeg"
}

응답 오류:
  401: Authorization 미제공/만료
  413: 파일 크기 초과
  415: 허용되지 않은 MIME
  500: 스토리지 실패
```

### 구현 위치
- **새 파일 신설**: `routers/uploads.py` (Router만, 400줄 미만)
- **서비스 로직**: `services/upload_service.py` 신설
  - `async def upload_inspection_photo(file: UploadFile, context: str, user_id: str, **ids) -> dict`
- **Supabase Storage 버킷**: 기존 `inspections` 버킷 재사용
- **경로 규칙**: `{context}/{YYYY}/{MM}/{DD}/{inspection_id or factory_id or 'anon'}/{sequence}.{ext}`
- **시퀀스**: `uuid4().hex[:8]` 사용 (충돌 무시 가능)

### main.py 등록
```python
from routers import uploads
app.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
```

---

## TASK 2. `/emergency/report` 보강

### 현재 상태 확인
- `routers/` 전체에서 `emergency` grep → 해당 파일/엔드포인트 실재 여부 확인
- 없으면 신설. 있으면 개선.

### 요구사항
```
POST /emergency/report
Authorization: Bearer {access_token}  (필수)
Content-Type: application/json

request body:
{
  "phone": "010...",
  "worker_name": "string",
  "accident_type": "string",
  "accident_type_key": "fall|fire|pinch|electric|chem|other",
  "location": "lat,lng" | null,
  "location_lat": number | null,
  "location_lng": number | null,
  "photo_urls": ["https://...", ...]  // 선택, TASK 1로 선업로드된 URL
}

응답 200:
{
  "report_number": "EMG-{YYYYMMDD}-{SEQ}",   // 서버 발급
  "id": "UUID",
  "received_at": "ISO8601",
  "notified_managers": ["manager_id1", ...]
}
```

### 구현 포인트
- `report_number` 서버 생성: `EMG-{날짜}-{일일시퀀스}`
- factory/site의 안전관리자(role='SAFETY_MANAGER')에게 **즉시 FCM 알림**
  - `fcm.py`의 기존 send 함수 재사용
  - 알림 data: `{type: 'emergency', report_number, accident_type}`
- `photo_urls`는 리포트 row에 JSON 컬럼으로 저장

---

## TASK 3. `/safety-reports` 보강

### 요구사항
```
POST /safety-reports
Authorization: Bearer {access_token}  (필수)

request body:
{
  "phone": "...",
  "worker_id": "UUID",
  "factory_id": "UUID" | null,
  "site_id": "UUID" | null,
  "report_type": "설비이상|환경위험|신체이상|작업방법이상",
  "description": "string (min 10)",
  "urgency": "normal|urgent|critical",
  "location_lat": number | null,
  "location_lng": number | null,
  "location_text": "string",
  "photo_urls": ["https://...", ...]   // 변경: Base64 배열 → URL 배열
  "submitted_at": "ISO8601"
}

응답 200:
{
  "report_number": "RPT-{YYYYMMDD}-{SEQ}",
  "id": "UUID",
  "received_at": "ISO8601"
}
```

### 핵심 변경
- **`photos: [base64...]` → `photo_urls: [url...]`** 필드명 변경
- 서버 발급 `report_number`
- Authorization 필수화
- urgency='critical' 즉시 FCM 알림

---

## TASK 4. `/worker-check/submit` 보강

### 요구사항
- Authorization 검증 추가
- 각 item에 `photo_urls: string[]` 필드 수용

```json
{
  "phone": "...",
  "worker_id": "UUID",
  "factory_id": "UUID",
  "schedule_id": "UUID | null",
  "inspection_type": "BEFORE_WORK" | "BEFORE_WORK_CON",
  "items": [
    {
      "name": "...",
      "result": "ok" | "bad",
      "memo": "string",
      "photo_urls": ["https://...", ...]   // 신규 (bad일 때 의미)
    }
  ],
  "submitted_at": "ISO8601"
}
```

- `photo_count` 필드 deprecated. `photo_urls.length`로 계산
- 응답에 `inspection_id` 포함 (프론트 history 조회에 사용)
- 인증 실패 시 401 + `{error: "AUTH_EXPIRED"}` 식 명확한 메시지

### 현재 파일
- `routers/worker_check.py` (4.6KB) — 작고 단순. 직접 수정.

---

## TASK 5. `/tbm/sign` Authorization 검증

- 현재 `routers/tbm.py` (17.7KB)
- Authorization 검증만 추가, 다른 로직 변경 없음
- 순증 500B 이내 → 유지 OK. 20KB 초과 예상 시 별도 분리 오더

---

## TASK 6. `/notifications` 서버 엔드포인트 확인

- 프론트 `notifications.html`은 `GET /notifications?worker_id=&phone=&page=1&size=30` 호출
- `routers/notifications.py` (15KB)에 실존 여부 확인
- 없으면 신설 (작업자별 알림 페이징)
- 있으면 Authorization 검증만 추가

---

## TASK 7. `/workers/fcm-token` Authorization 검증

- 프론트 `index.html`이 `POST /workers/fcm-token` 호출
- `routers/fcm.py` (7.2KB)에 있을 것으로 추정
- Authorization 필수화

---

## 테스트 체크리스트

- [ ] `/uploads/inspection-photo` 5MB 초과 파일 → 413
- [ ] image/gif 업로드 → 415
- [ ] 정상 업로드 → Supabase `inspections` 버킷 경로대로 저장 + public URL 반환
- [ ] `/emergency/report` Authorization 없이 → 401
- [ ] `/emergency/report` 정상 호출 → `EMG-{날짜}-{seq}` 포맷 반환
- [ ] 안전관리자 FCM 수신 확인 (테스트 계정)
- [ ] `/safety-reports` `photo_urls` 정상 저장
- [ ] `/worker-check/submit` items[].photo_urls 정상 저장
- [ ] `/health` 200 유지

---

## 배포 순서

1. `dev` 브랜치에서 작업
2. 로컬/dev 환경에서 Postman/curl 스모크
3. PR → main merge → Railway 자동 배포
4. 프로덕션 `/health` 200 확인
5. **프론트 팀(Cursor)에 배포 완료 공유 — 이 단계가 끝나야 프론트 P0 착수 가능**

---

## 변경 요약

| 엔드포인트 | 변화 | 우선순위 |
|---|---|---|
| `POST /uploads/inspection-photo` | 신설 | P0 |
| `POST /emergency/report` | 보강/신설 | P0 |
| `POST /safety-reports` | 보강 (photos→photo_urls) | P0 |
| `POST /worker-check/submit` | 보강 (photo_urls 수용) | P0 |
| `POST /tbm/sign` | Auth 검증 | P0 |
| `GET /notifications` | 확인/보강 | P1 |
| `POST /workers/fcm-token` | Auth 검증 | P1 |

---

**작성**: Claude (기획창)  
**실행**: Claude Code (백엔드창)  
**검증**: 심태왕
