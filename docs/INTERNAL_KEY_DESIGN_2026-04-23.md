# 내부 키 체계 설계 (2026-04-23)

## 사용자 결정

> "의견대로 진행하시죠. 다만 안에서라도 키를 가지고 진행이 되어야 하니.
>  그방향으로 진행을 해주세요. 그리고 법제처와 연동을 하는것에 대해서는 고민을 좀 해봅시다."

→ **내부 키 체계 구축 진행 (이번 세션)**
→ **법제처 deep link/API/변경이력 연동 보류 (다음 논의)**

## 원칙

```
1. 내부에서만 유일하고 결정적
   - law_id 내 UNIQUE
   - 동일 raw_xml 재파싱 시 동일 값 생성

2. 외부와의 호환성 포기 (명시)
   - 법제처 deep link 불가 (NFPC/NFTC)
   - 법제처 API 파라미터 불가
   - 조문 단위 변경 이력 불가

3. 놓치지 않음 (사용자 최우선 원칙)
   - NFPC: 조문 1개도 놓치지 않음
   - NFTC: 세부 섹션(1.1.1, 1.7.1.11)까지 모두 캡처
```

## 체계별 키 형식

### 체계 A: 일반 법령 (현재 유지)
```
article_internal_key = "0038001"
형식:   법제처 공식 7자리 조문키
범위:   104개 법령 / 9,796 조문
상태:   재작업 불필요. 이미 완벽.
```

### 체계 B: NFPC (재파싱 후)
```
article_internal_key = "nfpc-art-{조문번호:03d}"
형식:
  일반 조문: "nfpc-art-038"       (제38조)
  제N조의M:  "nfpc-art-038-of-02" (제38조의2)
  부칙:      "nfpc-bu-001"
  기타:      "nfpc-misc-001"

파서 로직:
  <조문내용> 태그 전부 순회
  각 텍스트에서 "제N조(제목) 본문" 패턴 매칭
  → 조문번호, 제목, 본문 추출

범위: 38개 법령 × 약 15조 = 약 450 조문
```

### 체계 C: NFTC (재파싱 후)
```
article_internal_key = "nftc-sec-{섹션번호}"
형식:
  장:    "nftc-sec-1"        (1. 일반사항)
  절:    "nftc-sec-1.1"      (1.1 적용범위)
  조:    "nftc-sec-1.1.1"    (1.1.1 세부)
  항:    "nftc-sec-1.7.1.11" (깊이 무관)

파서 로직:
  모든 <조문내용> 병합 (첫 번째만 가져오는 실수 방지)
  라인별로 "N(.N)*" 패턴 매칭 (모든 깊이)
  각 섹션을 독립 article로 저장

범위: 40개 법령 × 약 125 섹션 = 약 5,000 항목
```

## 키 prefix로 체계 자명

```
article_internal_key 값만 보면 체계를 바로 알 수 있음:
  "0038001"           → 체계 A (법령)
  "nfpc-art-038"      → 체계 B (NFPC)
  "nftc-sec-1.7.1.11" → 체계 C (NFTC)
  "admrul-*"          → 구버전 폴백 (전기설비기술기준 등)
```

## 파서 v2.0 구조

```python
def parse_admrul_content_xml(xml_text):
    form_flag = root.find("행정규칙기본정보").findtext("조문형식여부")
    
    if form_flag == "Y":
        return _parse_nfpc_articles(root)  # NFPC
    elif form_flag == "N":
        return _parse_nftc_articles(root)  # NFTC
    else:
        return _parse_fallback(root)       # 전기설비기준 등
```

각 파서는 체계 특성에 맞게 최적화:
- NFPC: 다중 <조문내용> 순회 + "제N조" 정규식
- NFTC: 전체 병합 + 모든 깊이 섹션 패턴
- 폴백: 기존 v1.4 로직 유지

## 재파싱 전략 (API 호출 0)

```
재료: law_content_raw.raw_xml (이미 DB에 저장됨)
도구: scripts/reparse_admrul.py + 파서 v2.0
처리: 
  1. 기존 article 조회 → UUID 매핑 준비
  2. raw_xml 파싱 → 새 article 리스트
  3. UPSERT:
     - 같은 internal_key 있음 → UPDATE (UUID 유지)
     - 없음 → INSERT (신규 UUID)
     - 구 키가 신규에 없음 → article_status_code='DELETED'
```

## 법제처 연동 보류 결정 (사용자)

현재 키는 **내부 전용**. 다음은 법제처와 연동 불가:

```
❌ 원본 링크: NFPC/NFTC는 법제처가 조문 단위 URL 미제공
❌ API 파라미터: admrul API는 법령 단위만 호출 가능
❌ 변경 이력: 조문/섹션별 시행일자 태그 없음 (법령 단위만)
```

이것은 **법제처 시스템의 구조적 한계**. 우리 키 설계로는 해결 불가.

### 다음 논의 시 고려 사항

```
1. 타협: 법령 단위 deep link + 섹션 텍스트 앵커 (우리 UI에서)
2. 자체 구축: 변경 이력을 우리가 섹션 단위 diff 계산
3. 법제처와 협의 (중장기): 섹션 식별 체계 요청
4. 대안 데이터 소스: 소방청 NFTC 원본 XML 직접 확보?
```

→ 사용자님 고민 결과 기다림

## 실행 순서 (이번 세션)

```
1. ✅ 파서 v2.0 작성 (routers/law_collector_admrul.py)
2. ✅ 재파싱 스크립트 작성 (scripts/reparse_admrul.py)
3. ✅ 설계 문서 작성 (이 파일)
4. ⏳ 로컬 테스트 실행 (사용자):
     python3 scripts/reparse_admrul.py test "NFTC 102"
5. ⏳ 결과 검증:
     - article 수 증가 확인
     - internal_key 새 체계 적용 확인
6. ⏳ 전체 실행:
     python3 scripts/reparse_admrul.py all
7. ⏳ rule_article_mapping 재실행:
     새 NFPC/NFTC 조문으로 룰 매칭 추가
```

## 예상 결과

```
현재:
  NUMERIC_ONLY:    9,796 (법령)
  ADMRUL_SECTION:    855 (NFTC 중분류)
  OTHER:             323 (구 폴백)
  합계:           10,974 조문

재파싱 후:
  법제처 공식 키 (0038001):       9,796 (변화 없음)
  nfpc-art-*:                   ~450 (신규, 448개 복구)
  nftc-sec-*:                  ~5,000 (신규, 3,906개 복구)
  admrul-* (폴백):                ~10 (전기설비기술기준 등)
  DELETED (구버전 삭제):       ~1,178
  합계 (ACTIVE):              ~15,256 조문

→ 기존 대비 +4,282 조문 확보 (놓침 해소)
```

## 다음 작업

사용자님 테스트 실행 → 결과 보고 → 전체 실행 결정.
