# P1 긴급 작업 지시서 — 2026-03-30

## 담당: Claude Code

---

## 작업 배경

법령 수집·매핑 전수 점검 결과 아래 5개 항목이 긴급 처리 필요:
1. Railway 빌드 실패 (pycairo → libcairo 시스템 라이브러리 없음)
2. 산안법 시행령 중복 등록 (조문 없는 버전이 is_current=true)
3. 중대재해처벌법 + 시행령 조문 0개
4. 산안법 시행규칙 조문 0개
5. 화재예방법 조문 0개
6. 소음·진동관리법 / 장애인편의법 미수집

---

## STEP 1. Railway 빌드 복구 (Dockerfile)

현재 `nixpacks.toml`이 있지만 빌드 실패 중.
`Dockerfile`로 전환하여 `libcairo2-dev` 시스템 패키지 설치.

```bash
# 로컬에서
git pull origin main
```

아래 내용으로 `Dockerfile` 생성 (루트에):

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libcairo2-dev \
    pkg-config \
    python3-dev \
    libffi-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

`nixpacks.toml` 삭제:
```bash
git rm nixpacks.toml 2>/dev/null || true
git add Dockerfile
git commit -m "fix: Dockerfile 전환 — libcairo2-dev 설치로 Railway 빌드 복구"
git push origin main
```

Railway 빌드 성공 확인 후 다음 단계 진행.

---

## STEP 2. DB 정리 — 산안법 시행령 중복 제거

현재 `산업안전보건법 시행령`이 2개 등록됨:
- ID `714c67b3-...`: 조문 135개 (정상)
- ID `6ebf849e-...`: 조문 0개 (삭제 대상)

Supabase MCP로 실행:

```sql
-- 조문 없는 버전 확인
SELECT lm.id, lm.law_name, lv.id as version_id, COUNT(la.id) as 조문수
FROM law_master lm
LEFT JOIN law_version lv ON lv.law_id = lm.id
LEFT JOIN law_article la ON la.law_version_id = lv.id
WHERE lm.law_name = '산업안전보건법 시행령'
GROUP BY lm.id, lm.law_name, lv.id
ORDER BY COUNT(la.id) DESC;

-- 조문 0개인 law_master 행 삭제 (버전도 cascade 삭제)
-- law_key가 다른 두 행이므로 조문 없는 ID를 찾아 삭제
DELETE FROM law_version 
WHERE law_id = '6ebf849e-05d1-4ab5-a8f3-a00bbad631fa';

DELETE FROM law_master 
WHERE id = '6ebf849e-05d1-4ab5-a8f3-a00bbad631fa';
```

---

## STEP 3. 빌드 성공 후 — 법령 재수집 (API 호출)

빌드 완료 확인 후 아래 법령들을 API로 재수집:

```bash
# 중대재해처벌법
curl -s -X POST "https://api.taieng.co.kr/law-collector/collect/$(python3 -c "import urllib.parse; print(urllib.parse.quote('중대재해 처벌 등에 관한 법률'))")" | python3 -m json.tool
sleep 3

# 중대재해처벌법 시행령
curl -s -X POST "https://api.taieng.co.kr/law-collector/collect/$(python3 -c "import urllib.parse; print(urllib.parse.quote('중대재해 처벌 등에 관한 법률 시행령'))")" | python3 -m json.tool
sleep 3

# 산안법 시행규칙
curl -s -X POST "https://api.taieng.co.kr/law-collector/collect/$(python3 -c "import urllib.parse; print(urllib.parse.quote('산업안전보건법 시행규칙'))")" | python3 -m json.tool
sleep 3

# 화재예방법
curl -s -X POST "https://api.taieng.co.kr/law-collector/collect/$(python3 -c "import urllib.parse; print(urllib.parse.quote('화재의 예방 및 안전관리에 관한 법률'))")" | python3 -m json.tool
sleep 3

# 소음·진동관리법
curl -s -X POST "https://api.taieng.co.kr/law-collector/collect/$(python3 -c "import urllib.parse; print(urllib.parse.quote('소음·진동관리법'))")" | python3 -m json.tool
sleep 3

# 장애인·노인·임산부 편의증진법
curl -s -X POST "https://api.taieng.co.kr/law-collector/collect/$(python3 -c "import urllib.parse; print(urllib.parse.quote('장애인·노인·임산부 등의 편의증진 보장에 관한 법률'))")" | python3 -m json.tool
sleep 3
```

---

## STEP 4. 수집 결과 검증 (Supabase MCP)

```sql
-- 재수집 후 조문수 확인
SELECT lm.law_name, lm.law_type_code, COUNT(la.id) as 조문수
FROM law_master lm
LEFT JOIN law_version lv ON lv.law_id = lm.id AND lv.is_current = true
LEFT JOIN law_article la ON la.law_version_id = lv.id
WHERE lm.law_name IN (
  '중대재해 처벌 등에 관한 법률',
  '중대재해 처벌 등에 관한 법률 시행령',
  '산업안전보건법 시행규칙',
  '화재의 예방 및 안전관리에 관한 법률',
  '소음·진동관리법',
  '장애인·노인·임산부 등의 편의증진 보장에 관한 법률'
)
GROUP BY lm.law_name, lm.law_type_code
ORDER BY lm.law_name;

-- 전체 매핑 미매핑 재확인
SELECT COUNT(*) as 전체, 
  COUNT(CASE WHEN lm.id IS NOT NULL THEN 1 END) as 매핑,
  COUNT(CASE WHEN lm.id IS NULL THEN 1 END) as 미매핑
FROM master_building_legal_rules r
LEFT JOIN law_master lm ON lm.law_name = r.law_name
WHERE r.is_active = true;
```

---

## 완료 기준

- [ ] Railway 빌드 성공 (버전 v4.2.1 또는 이상)
- [ ] 산안법 시행령 중복 제거 (1개만 남음)
- [ ] 중대재해처벌법 본법 + 시행령 조문 > 0
- [ ] 산안법 시행규칙 조문 > 0
- [ ] 화재예방법 조문 > 0
- [ ] 소음·진동관리법 + 장애인편의법 수집 완료
- [ ] 전체 미매핑 룰 0개 달성

완료 후 회의실 창에 결과 보고.
