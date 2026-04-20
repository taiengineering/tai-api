# TAI Safe 법령 데이터 파이프라인 방법론

이슈 #24 참조. 상세 문서: /mnt/user-data/outputs/law_data_pipeline_methodology.md

## 핵심 결론
수동 GPT 37회 투입이 아닌 **법제처 Open API + Claude API 자동 파이프라인** 구축.

## 흐름
```
법제처 API → 법령 전문 수집 → Claude API 파싱 → 구조화 검증 → DB INSERT
```

## 예상
- 소요: 2~3일
- 비용: ~$5
- 결과: 1,133건 → 3,000건+
- 지속성: 법령 개정 시 자동 재수집·재파싱 가능

## 필요 스크립트
- scripts/law_collector.py (법제처 API → staging)
- scripts/law_parser.py (Claude API → 의무 추출)
- scripts/law_inserter.py (staging → master_building_legal_rules)
