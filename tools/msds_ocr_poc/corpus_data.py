"""Static fixture definitions for MSDS OCR PoC corpus.

30 fixtures: K01-K10 (Korean), E01-E10 (English), M01-M10 (Mixed).
All CAS numbers have been checksum-verified.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MsdsFixture:
    id: str
    language: str           # "korean" | "english" | "mixed"
    product_name: str
    manufacturer_name: str
    supplier_name: Optional[str]
    product_code: Optional[str]
    cas_numbers: list[str]
    variant: str            # "clean" | "low_contrast" | "rotated" | "noise" | "small_text"
    cas_page: int = 2       # page number where CAS section appears (for page-strategy test)
    total_pages: int = 10


# ---------------------------------------------------------------------------
# Korean-primary fixtures (K01-K10)
# ---------------------------------------------------------------------------
KOREAN = [
    MsdsFixture("K01", "korean", "염산 36% 수용액", "케미칼코리아(주)", None,
                "HCL-36", ["7647-01-0"], "clean", cas_page=2),
    MsdsFixture("K02", "korean", "황산 98%", "한국화학(주)", "대한시약(주)",
                "H2SO4-98", ["7664-93-9"], "clean", cas_page=2),
    MsdsFixture("K03", "korean", "수산화나트륨 (가성소다)", "케이엠화학",
                None, "NAOH-99", ["1310-73-2"], "clean", cas_page=3),
    MsdsFixture("K04", "korean", "아세톤 (99.5% 이상)", "덕산화학(주)",
                None, "ACE-99", ["67-64-1"], "clean", cas_page=2),
    MsdsFixture("K05", "korean", "에탄올 99.9%", "SK케미칼(주)",
                None, "EtOH-99", ["64-17-5"], "clean", cas_page=2),
    MsdsFixture("K06", "korean", "벤젠", "한국바스프(주)",
                "한국시약(주)", "BNZ-99", ["71-43-2"], "clean", cas_page=4),
    MsdsFixture("K07", "korean", "톨루엔 (공업용)", "OCI(주)",
                None, "TOL-IND", ["108-88-3"], "low_contrast", cas_page=3),
    MsdsFixture("K08", "korean", "이염화메틸렌 (메틸렌클로라이드)", "한화케미칼",
                None, "DCM-99", ["75-09-2"], "small_text", cas_page=2),
    MsdsFixture("K09", "korean", "암모니아수 28%", "덕산화학(주)",
                None, "NH3-28", ["7664-41-7"], "rotated", cas_page=2),
    MsdsFixture("K10", "korean", "과산화수소 30%", "한국화학(주)",
                "한국과학(주)", "H2O2-30", ["7722-84-1"], "noise", cas_page=3),
]

# ---------------------------------------------------------------------------
# English-primary fixtures (E01-E10)
# ---------------------------------------------------------------------------
ENGLISH = [
    MsdsFixture("E01", "english", "Acetonitrile HPLC Grade", "Sigma-Aldrich Korea",
                None, "ACN-HPLC", ["75-05-8"], "clean", cas_page=2),
    MsdsFixture("E02", "english", "Chloroform Reagent Grade", "Thermo Fisher Scientific",
                None, "CHCl3-RG", ["67-66-3"], "clean", cas_page=2),
    MsdsFixture("E03", "english", "Methanol 99.9%", "Duksan Reagents",
                None, "MeOH-99", ["67-56-1"], "clean", cas_page=2),
    MsdsFixture("E04", "english", "Formaldehyde Solution 37%", "Junsei Chemical",
                None, "FORM-37", ["50-00-0"], "clean", cas_page=3),
    MsdsFixture("E05", "english", "Phenol Crystal", "Samchun Chemicals",
                None, "PHE-CR", ["108-95-2"], "clean", cas_page=2),
    MsdsFixture("E06", "english", "Xylene Mixed Isomers", "SK Innovation",
                "Seojin Chem", "XYL-MX", ["1330-20-7"], "clean", cas_page=3),
    MsdsFixture("E07", "english", "Isopropyl Alcohol 99.5%", "OCI Company Ltd.",
                None, "IPA-99", ["67-63-0"], "low_contrast", cas_page=2),
    MsdsFixture("E08", "english", "n-Hexane Technical Grade", "Dongwoo Fine-Chem",
                None, "HEX-TG", ["110-54-3"], "small_text", cas_page=4),
    MsdsFixture("E09", "english", "Dimethyl Sulfoxide (DMSO)", "Biosolution Co.",
                None, "DMSO-99", ["67-68-5"], "rotated", cas_page=2),
    MsdsFixture("E10", "english", "8-Hydroxyquinoline", "TCI Korea",
                None, "8HQ-98", ["148-24-3"], "noise", cas_page=3),
]

# ---------------------------------------------------------------------------
# Mixed Korean/English fixtures (M01-M10)
# ---------------------------------------------------------------------------
MIXED = [
    MsdsFixture("M01", "mixed", "혼합용제 / Mixed Solvent A", "한국용제(주)",
                None, "MIX-SOL-A", ["108-88-3", "1330-20-7"], "clean", cas_page=3),
    MsdsFixture("M02", "mixed", "세정제 / Cleaning Agent B", "클린켐(주)",
                None, "CLN-AGT-B", ["67-63-0", "67-64-1"], "clean", cas_page=2),
    MsdsFixture("M03", "mixed", "실험실 혼합산 / Lab Mixed Acid", "케미칼코리아(주)",
                "한국과학(주)", "LAB-ACD-M", ["7647-01-0", "7664-93-9"], "clean", cas_page=2),
    MsdsFixture("M04", "mixed", "유기용제혼합물 / Organic Solvent Mix", "한화케미칼",
                None, "ORG-MIX-3",
                ["71-43-2", "108-88-3", "1330-20-7"], "clean", cas_page=4),
    MsdsFixture("M05", "mixed", "산화성세정제 / Oxidizing Cleaner", "한국화학(주)",
                None, "OX-CLN-1", ["7722-84-1", "7664-93-9"], "clean", cas_page=3),
    MsdsFixture("M06", "mixed", "단순혼합용제 / Simple Blend", "OCI(주)",
                None, "SMPL-BLD", ["64-17-5"], "clean", cas_page=5),
    MsdsFixture("M07", "mixed", "고농도 혼합물 / High Conc Blend", "덕산화학(주)",
                None, "HC-BLD-2", ["67-56-1", "67-63-0", "64-17-5"], "clean", cas_page=4),
    MsdsFixture("M08", "mixed", "산업용 세척제 / Industrial Cleaner", "케이엠화학",
                "클린켐(주)", "IND-CLN-3", ["67-56-1", "67-63-0", "64-17-5"], "clean", cas_page=3),
    MsdsFixture("M09", "mixed", "도료희석제 / Paint Thinner", "SK케미칼(주)",
                None, "PAINT-THN",
                ["108-88-3", "110-54-3", "1330-20-7"], "clean", cas_page=5),
    MsdsFixture("M10", "mixed", "특수처리액 / Special Treatment Fluid", "한국바스프(주)",
                "Basell Korea", "SPEC-TRT-1", ["75-09-2"], "clean", cas_page=6),
]

ALL_FIXTURES: list[MsdsFixture] = KOREAN + ENGLISH + MIXED


# ---------------------------------------------------------------------------
# Invalid CAS test cases for validator unit tests
# ---------------------------------------------------------------------------
@dataclass
class CasTestCase:
    raw: str
    description: str
    expect_format: bool
    expect_checksum: bool
    ocr_correctable: bool = False
    corrected: str = ""


CAS_TEST_CASES: list[CasTestCase] = [
    # Valid
    CasTestCase("7647-01-0",  "HCl — valid",                      True,  True),
    CasTestCase("7664-93-9",  "H2SO4 — valid",                    True,  True),
    CasTestCase("1310-73-2",  "NaOH — valid",                     True,  True),
    CasTestCase("67-64-1",    "Acetone — valid",                   True,  True),
    CasTestCase("64-17-5",    "Ethanol — valid",                   True,  True),
    CasTestCase("71-43-2",    "Benzene — valid",                   True,  True),
    CasTestCase("108-88-3",   "Toluene — valid",                   True,  True),
    CasTestCase("75-09-2",    "DCM — valid",                       True,  True),
    CasTestCase("7664-41-7",  "NH3 — valid",                       True,  True),
    CasTestCase("7722-84-1",  "H2O2 — valid",                      True,  True),
    CasTestCase("75-05-8",    "Acetonitrile — valid",              True,  True),
    CasTestCase("67-66-3",    "Chloroform — valid",                True,  True),
    CasTestCase("67-56-1",    "Methanol — valid",                  True,  True),
    CasTestCase("50-00-0",    "Formaldehyde — valid",              True,  True),
    CasTestCase("108-95-2",   "Phenol — valid",                    True,  True),
    CasTestCase("1330-20-7",  "Xylene — valid",                    True,  True),
    CasTestCase("67-63-0",    "IPA — valid",                       True,  True),
    CasTestCase("110-54-3",   "n-Hexane — valid",                  True,  True),
    CasTestCase("67-68-5",    "DMSO — valid",                      True,  True),
    CasTestCase("148-24-3",   "8-HQ — valid",                      True,  True),
    # Wrong checksum (format OK, checksum FAIL)
    CasTestCase("7647-01-1",  "HCl wrong check digit",            True,  False),
    CasTestCase("7664-93-0",  "H2SO4 wrong check digit",          True,  False),
    CasTestCase("67-64-9",    "Acetone wrong check digit",         True,  False),
    CasTestCase("1234-56-7",  "made-up wrong checksum",            True,  False),
    # Bad format (cannot be CAS)
    CasTestCase("7647-01",    "missing check digit",               False, False),
    CasTestCase("7647-1-0",   "short second segment",              False, False),
    CasTestCase("ABCD-12-3",  "non-digit first segment",           False, False),
    CasTestCase("76470100",   "no hyphens",                        False, False),
    # OCR confusion — correctable
    # "764O-01-0" → O→0 → "7640-01-0": digits=764001, sum=89, 89%10=9 ≠ 0 → NOT correctable
    CasTestCase("764O-01-0",  "O→0 but result checksum invalid",  False, False, False, ""),
    # "7647-O1-0" → O→0 → "7647-01-0" (HCl, valid)
    CasTestCase("7647-O1-0",  "O→0 in second segment (HCl)",      False, False, True,  "7647-01-0"),
    CasTestCase("7647-0I-0",  "I→1 in second segment (HCl)",      False, False, True,  "7647-01-0"),
    CasTestCase("6S-64-1",    "S→5 OCR error (Acetone partial)",   False, False, False, ""),
]
