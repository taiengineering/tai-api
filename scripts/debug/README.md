# scripts/debug

SESSION 1 등에서 사용하는 **로컬 진단 산출물**입니다.

## 법령 본문 XML 샘플 (건축법 / 산업안전보건법)

용량이 커서 `*.xml` 은 git에 올리지 않습니다. 아래로 재생성하세요.

```bash
cd tai-api
python3 scripts/debug/fetch_law_raw_xml.py
```

생성 파일:

- `geonchuk_raw.xml` — 건축법 (MST는 검색 API로 조회)
- `sanbohoeon_raw.xml` — 산업안전보건법

`LAW_API_OC` 환경변수는 `routers/law_collector.py` 와 동일하게 쓰입니다 (미설정 시 `taieng`).
