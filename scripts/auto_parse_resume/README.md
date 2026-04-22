# TAI 법령엔진 auto-parse 재개 패키지

**생성일:** 2026-04-22 09:00 KST  
**목적:** 멈춘 크롬 탭을 대체하여 로컬에서 법령 파싱을 재개합니다.

---

## 📦 패키지 내용

| 파일 | 설명 |
|---|---|
| `auto_parse_worker.py` | 재개용 Python worker (실행 스크립트) |
| `auto_parse_queue.csv` | 147개 우선순위 법령 목록 (partial 75 + fresh 72) |
| `README.md` | 이 파일 |

---

## 🚀 사용법

### 1단계: 준비

```bash
cd scripts/auto_parse_resume/

# INTERNAL_SECRET 설정 (Railway 환경변수)
export TAI_INTERNAL_SECRET="tai-internal-2026"
export TAI_API_URL="https://api.taieng.co.kr"
```

### 2단계: 테스트 실행 (드라이런)

```bash
python3 auto_parse_worker.py --dry-run --max-laws 5
```

### 3단계: 실전 실행

```bash
# 소량 테스트
python3 auto_parse_worker.py --max-laws 10

# 전체 실행 (147개)
python3 auto_parse_worker.py

# 백그라운드 + 로그 모니터링 (권장)
nohup python3 auto_parse_worker.py > worker.out 2>&1 &
tail -f auto_parse.log
```

---

## ⚙️ 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--max-per-law` | 50 | 법령당 최대 조문 수 |
| `--threshold` | 80 | auto_approve_threshold |
| `--sleep` | 5 | 법령 간 대기 (초) |
| `--max-laws` | 0 | 최대 N개만 처리 (0=전체) |
| `--laws-file` | auto_parse_queue.csv | CSV 경로 |
| `--dry-run` | — | 실제 호출 없이 계획만 출력 |

---

## 📊 예상 소요

- 147 법령 × 평균 100초/법령 ≈ **4시간**

---

## ⚠️ 주의사항

1. **중단**: Ctrl+C로 안전 중단 가능. 현재 법령 완료 후 종료.
2. **재개**: 재실행해도 DB가 `ai_parsed_at IS NULL` 조문만 처리.
3. **에러 복원**:
   - 502/503/504 → 60초 대기
   - 네트워크 오류 → 30초 대기
4. **Rate Limit**: Anthropic Console에서 Haiku 쿼터 확인.

---

## 🔄 완료 후

Worker 완료 후 APPROVED 미등록 드래프트를 master로:

```bash
curl -X POST "https://api.taieng.co.kr/law-rule-generator/bulk-approve-unregistered?secret=$TAI_INTERNAL_SECRET&limit=500"
```

또는 기획창(Claude)에서 SQL 직접 실행 (안전, 중복 자동 처리).

---

## 🐞 트러블슈팅

### "TAI_INTERNAL_SECRET 환경변수 필요"
`export TAI_INTERNAL_SECRET="실제값"` 후 재실행.

### HTTP 403 "내부 전용 엔드포인트"
SECRET 값이 Railway `INTERNAL_API_SECRET`과 일치해야 함.

### 진행률 확인
```bash
tail -f auto_parse.log
# 또는 Supabase SQL
SELECT COUNT(*) AS parsed
FROM law_article
WHERE ai_parsed_at >= NOW() - INTERVAL '1 hour';
```

---

## 💡 장기 개선안

이 스크립트는 **임시 해결책**입니다. 근본 해결:

1. **AUTO_PARSE_NEW cron 활성화** — `docs/WORK_ORDER_REPARSE_SANITIZE_FIX.md` STEP 4 참조
2. Railway Background Worker 분리
3. Supabase Edge Function 스케줄 실행
