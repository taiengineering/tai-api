# 법령 파이프라인 소비자 전달 보강 기획

이슈 #24 참조. 상세 문서: /mnt/user-data/outputs/law_pipeline_consumer_delivery.md

## 핵심
현재 파이프라인은 수집·저장까지만 됨. 소비자에게 "무엇을, 어떻게, 언제" 전달하는 구조 부재.

## 보강: DB 7개 컬럼 추가
- compliance_guide (이행 방법)
- required_documents (필요 서류)
- submit_to (제출처)
- penalty_detail (과태료 상세)
- qualification (자격요건)
- deadline_description (기한)
- tai_feature_code (TAI 기능 연결)

## 실행: 3단계
1. DB 스키마 + 파이프라인 프롬프트 보강 (1일)
2. 기존 데이터 재파싱으로 새 컬럼 채우기 (1~2일)
3. PDF/웹 결과 UI에 반영 (1일)
