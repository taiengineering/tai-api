# 세션 작업내역 — 2026-04-19 인프라·진단

**작성일:** 2026-04-19  
**담당:** 기획·인프라 창

---

## 1. Railway 참조 전수 조사 및 제거

### 조사 대상
- `taiengineering/tai-admin` (admin·safe 프론트)
- `taiengineering/taieng` (마케팅 사이트)
- `taiengineering/tai-api` (백엔드)

### 결과
- 실제 동작 코드(.js/.html/.py)에는 Railway URL 참조 **전혀 없음**
- 문서(.md) 파일에만 히스토리로 존재 → 수정 불필요
- `taiengineering/taieng` `package.json` description에만 "Railway entry" 문구 존재

### 수정
- `package.json` description: "Railway entry" → "Cloudflare Pages" 변경
- 커밋: `358fdd15` (taiengineering/taieng main)

---

## 2. Cloudflare Zero Trust 플랜 해지 ($7 → $0)

### 배경
- Zero Trust Pay-as-you-go 플랜 활성화 상태 (1 seat, 미사용)
- $7/월 과금 중

### 조치
- Cloudflare Zero Trust → Settings → Subscriptions → Free 플랜 전환
- 결과: **Zero Trust Free, 0 of 50 seats, $0/월** 확인

### 현재 인프라 구조
| 서비스 | 플랫폼 |
|---|---|
| 프론트 4개 사이트 | Cloudflare Pages |
| DNS | Cloudflare DNS |
| 백엔드 API | Fly.io Tokyo |
| DB | Supabase |

---

## 3. 메세지미 SMS·알림톡 발송 미작동 원인 파악

### 진단 결과
- `notification_logs`: 3건 모두 PUSH(FCM), SMS 0건
- `notification_queue`: 완전히 비어있음
- `/messaging/debug` 응답:
  ```json
  {
    "mode": "Vultr 고정 IP 프록시 경유",
    "proxy": "http://158.247.224.158:3128",
    "api_key": "설정됨",
    "sender": "070-8080-1858"
  }
  ```
- 테스트 발송 결과: **502 Bad Gateway**

### 원인
**Vultr 프록시 서버(158.247.224.158) 삭제됨**

`messaging.py` v5.0.0 구조:
```
Fly.io → Vultr Squid 프록시(고정 IP) → 메세지미
                  ↑
          ❌ 서버 삭제 → 502
```

메세지미는 고정 IP 화이트리스트 방식이라 Fly.io 유동 IP 직접 발송 불가.

### 해결 방안
1. **방법 1 (권장):** `fly ips allocate-v4 -a tai-api-prod` → 고정 IPv4 발급 ($2/월) → 메세지미 IP 등록
2. **방법 2:** `fly secrets unset OUTBOUND_PROXY -a tai-api-prod` 후 직접 발송 테스트

### 관련 이슈
- tai-api #13 (메세지미 SMS 발송 미작동)

---

## 4. PENDING 사항

| 항목 | 내용 |
|---|---|
| 메세지미 SMS 복구 | Fly.io 고정 IP 발급 또는 OUTBOUND_PROXY unset 후 테스트 |
| wrangler.toml 삭제 | taiengineering/taieng main (Pages 전환 완료, Workers용 불필요) |
| PR #10 머지 | 기안 PDF v2.0.0 — 프론트 템플릿 창과 동시 머지 필요 |
