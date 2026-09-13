"""OBJ-CSI official file contract — CSI-01 probe + GPT review.

Source-native ID is unavailable. Do not invent source_key.
"""
from __future__ import annotations

DATASET_ID = "15108262"
DATASET_EFFECTIVE_DATE = "2025-06-30"
DATASET_URL = "https://www.data.go.kr/data/15108262/fileData.do"
DOWNLOAD_URL = (
    "https://www.data.go.kr/cmm/cmm/fileDownload.do"
    "?atchFileId=FILE_000000003574744&fileDetailSn=1&insertDataPrcus=N"
)
ATCH_FILE_ID = "FILE_000000003574744"
OFFICIAL_FILENAME = "건설안전사고사례(_25.6.30)csv.csv"
OFFICIAL_BYTES = 36_318_137
OFFICIAL_SHA256 = "080618b19adc9973ee347600f2ca8211a601695ea4660a8dd520f9f55cacac4c"
SOURCE_ENCODING = "cp949"
DECLARED_ROWS = 14_289
PARSED_ROWS_PROBE = 37_196
HEADER_COUNT = 74
SOURCE_ID = "CSI"
SOURCE_KEY_AVAILABLE = False
FINGERPRINT_VERSION = "CSI_EVENT_FINGERPRINT_V1"
CONTENT_ID_PREFIX = "CSI:"
MISSING_TOKEN = "<<MISSING>>"
MISSING_SOURCE_VALUES = frozenset({"", "미입력"})
APPLY_ENABLE_ENV = "CSI_ACCIDENT_SYNC_ENABLE"
LICENSE = "이용허락범위 제한 없음"
MANAGING_DEPT = "AI전략실"

# Exact official/CSV header order. Implementation contract = file, not portal prose.
OFFICIAL_HEADERS: tuple[str, ...] = (
    "사고명",
    "사고일시",
    "공공민간구분",
    "날씨",
    "온도",
    "습도",
    "시설물 대분류",
    "시설물 중분류",
    "시설물 소분류",
    "연면적",
    "지상층수",
    "지하층수",
    "공사종류",
    "인적사고종류(대분류)",
    "인적사고종류",
    "안전방호조치여부",
    "개인보호조치여부",
    "물적사고종류",
    "공종(대분류)",
    "공종(소분류)",
    "사고객체(대분류)",
    "사고객체(소분류)",
    "작업프로세스",
    "사고위치 장소",
    "사고위치 장소(직접입력)",
    "사고위치 부위",
    "사고위치 부위(직접입력)",
    "사고원인-대분류",
    "사고원인-중분류",
    "사고원인-소분류",
    "사고원인(보조원인1)",
    "사고원인(보조원인2)",
    "구체적사고원인",
    "사망자",
    "내국인 사망자",
    "외국인 사망자",
    "남성 사망자",
    "여성 사망자",
    "10이상20미만 사망자",
    "20이상30미만 사망자",
    "30이상40미만 사망자",
    "40이상50미만 사망자",
    "50이상60미만 사망자",
    "60이상 사망자",
    "부상자",
    "내국인 부상자",
    "외국인 부상자",
    "남성 부상자",
    "여성 부상자",
    "10이상20미만 부상자",
    "20이상30미만 부상자",
    "30이상40미만 부상자",
    "40이상50미만 부상자",
    "50이상60미만 부상자",
    "60이상 부상자",
    "피해금액",
    "피해내용",
    "사고신고사유",
    "공사비",
    "해당공종 공사비",
    "공사시작일",
    "공사종료일",
    "해당공종 공사시작일",
    "해당공종 공사종료일",
    "낙찰율",
    "공정율",
    "작업자수",
    "안전관리계획",
    "설계안정성검토",
    "사고조사방법",
    "향후조치계획",
    "사고경위",
    "사고발생후 조치사항",
    "재발방지대책",
)

assert len(OFFICIAL_HEADERS) == HEADER_COUNT

# CSI-01 C5: exclude mutable narrative, casualty counts, loss amounts.
FINGERPRINT_EXCLUDED: frozenset[str] = frozenset(
    {
        "구체적사고원인",
        "사망자",
        "내국인 사망자",
        "외국인 사망자",
        "남성 사망자",
        "여성 사망자",
        "10이상20미만 사망자",
        "20이상30미만 사망자",
        "30이상40미만 사망자",
        "40이상50미만 사망자",
        "50이상60미만 사망자",
        "60이상 사망자",
        "부상자",
        "내국인 부상자",
        "외국인 부상자",
        "남성 부상자",
        "여성 부상자",
        "10이상20미만 부상자",
        "20이상30미만 부상자",
        "30이상40미만 부상자",
        "40이상50미만 부상자",
        "50이상60미만 부상자",
        "60이상 부상자",
        "피해금액",
        "피해내용",
        "사고조사방법",
        "향후조치계획",
        "사고경위",
        "사고발생후 조치사항",
        "재발방지대책",
    }
)

FINGERPRINT_HEADERS: tuple[str, ...] = tuple(
    h for h in OFFICIAL_HEADERS if h not in FINGERPRINT_EXCLUDED
)

NORM_TITLE = "사고명"
NORM_OCCURRED = "사고일시"
NORM_CONSTRUCTION = "공사종류"
NORM_PROCESS_MAJOR = "공종(대분류)"
NORM_PROCESS_MINOR = "공종(소분류)"
NORM_OBJECT_MAJOR = "사고객체(대분류)"
NORM_OBJECT_MINOR = "사고객체(소분류)"
NORM_WORK_PROCESS = "작업프로세스"
NORM_ACCIDENT_MAJOR = "인적사고종류(대분류)"
NORM_ACCIDENT_TYPE = "인적사고종류"
NORM_CAUSE_MAJOR = "사고원인-대분류"
NORM_CAUSE_MID = "사고원인-중분류"
NORM_CAUSE_MINOR = "사고원인-소분류"
NORM_CAUSE_DETAIL = "구체적사고원인"
NORM_SUMMARY = "사고경위"
NORM_DEATH = "사망자"
NORM_INJURY = "부상자"
