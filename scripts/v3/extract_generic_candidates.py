"""scripts/v3/extract_generic_candidates.py — Track C GENERIC 명사 후보 추출.

목적:
  law_article_part.part_text (143,549 rows) 전체를 Kiwi로 형태소 분석하여
  NNG/NNP/NF 명사를 추출, 이미 dict_legal_terms에 등록된 어휘를 제외한
  GENERIC 후보를 dedupe/빈도 집계 후 룰베이스 자동 검증으로 등록.

설계 원칙 (MASTER_HANDOFF §2):
  ① LLM X — Kiwi 형태소 + 명시적 임계값만
  ② 법령 보전 — source_text 그대로 분석, 어휘 변형 0
  ③ 누락 0 — 미달 후보도 verified=false로 등록 (절대원칙 3)
  ④ 100% 매핑 — source 컬럼 명시
  ⑤ 오염=폐기 — dry-run + 임계값 cross-check

룰베이스 자동 검증 (의미 판단 0):
  - len(term) < 2          → too_short
  - main_pos not in 명사    → non_noun
  - df_ratio > 0.30         → df_too_high (일반어 의심)
  - df_ratio < 0.001        → df_too_low (노이즈 의심)
  - frequency < 10          → low_freq (희귀)
  - pos_consistency < 0.90  → pos_inconsistent (다의어 의심)
  - 통과 → verified=true / 미달 → verified=false (절대원칙 3 보전)

실행:
  python3 scripts/v3/extract_generic_candidates.py --dry-run         # INSERT 없이 통계만
  python3 scripts/v3/extract_generic_candidates.py --limit 5000      # 5000 row만 처리
  python3 scripts/v3/extract_generic_candidates.py --chunk 500       # chunk size 조정
  python3 scripts/v3/extract_generic_candidates.py                   # 전체 실행

종료 코드:
  0: 정상 완료
  1: 환경 점검 실패 (DB 연결 / dict 비어있음)
  2: chunk 처리 실패
  3: INSERT 실패
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
import time
from collections import Counter

from db.supabase_client import get_supabase
from engine.morpheme import MorphemeEngine

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ----- 룰베이스 임계값 -----
NOUN_TAGS = frozenset({"NNG", "NNP", "NF"})

# 2026-05-09 점검값 (law_article_part 전체)
TOTAL_DOCS = 143_549

# 자동 검증 임계
TH_MIN_LEN = 2
TH_DF_HIGH = 0.30
TH_DF_LOW = 0.001
TH_MIN_FREQ = 10
TH_POS_CONSISTENCY = 0.90

# INSERT batch size
INSERT_BATCH = 500


# ----- 유틸 -----

def auto_verify_generic(
    term: str,
    pos_distribution: Counter,
    frequency: int,
    doc_freq: int,
) -> tuple[bool, str, str]:
    """룰베이스 자동 검증.

    Returns:
        (verified, reason, main_pos)
    """
    total_pos = sum(pos_distribution.values())
    if total_pos == 0:
        return False, "no_pos_data", ""
    main_pos = pos_distribution.most_common(1)[0][0]
    pos_consistency = pos_distribution[main_pos] / total_pos
    df_ratio = doc_freq / TOTAL_DOCS

    if len(term) < TH_MIN_LEN:
        return False, "too_short", main_pos
    if main_pos not in NOUN_TAGS:
        return False, f"non_noun({main_pos})", main_pos
    if df_ratio > TH_DF_HIGH:
        return False, f"df_too_high({df_ratio:.3f})", main_pos
    if df_ratio < TH_DF_LOW:
        return False, f"df_too_low({df_ratio:.5f})", main_pos
    if frequency < TH_MIN_FREQ:
        return False, f"low_freq({frequency})", main_pos
    if pos_consistency < TH_POS_CONSISTENCY:
        return False, f"pos_inconsistent({pos_consistency:.2f})", main_pos

    return True, "auto_verified", main_pos


def tfidf(freq: int, df: int) -> float:
    """log-normalized TF * IDF."""
    if df <= 0:
        return 0.0
    return round(math.log(1 + freq) * math.log(TOTAL_DOCS / df), 4)


# ----- DB I/O -----

def fetch_existing_terms(sb) -> set[str]:
    """dict_legal_terms에 이미 등록된 모든 term (verified 무관)."""
    # supabase-py는 select에 limit 1000 기본. 전체 fetch는 페이지네이션.
    out: set[str] = set()
    page = 0
    PAGE = 1000
    while True:
        res = (
            sb.table("dict_legal_terms")
            .select("term")
            .range(page * PAGE, (page + 1) * PAGE - 1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            break
        out.update(r["term"] for r in rows if r.get("term"))
        if len(rows) < PAGE:
            break
        page += 1
    return out


def fetch_part_chunk(sb, offset: int, chunk_size: int) -> list[dict]:
    """law_article_part chunk fetch. id 정렬로 안정적 페이지네이션."""
    res = (
        sb.table("law_article_part")
        .select("id, part_text")
        .order("id")
        .range(offset, offset + chunk_size - 1)
        .execute()
    )
    return res.data or []


# ----- 핵심 처리 -----

def process_chunk(
    rows: list[dict],
    engine: MorphemeEngine,
    existing: set[str],
    freq: Counter,
    pos: dict[str, Counter],
    doc_seen: dict[str, set],
) -> int:
    """청크 처리 — Counter/dict 누적. Returns: 처리된 row 수."""
    pairs = [(r["id"], r["part_text"]) for r in rows if r.get("part_text")]
    if not pairs:
        return 0

    ids = [p[0] for p in pairs]
    texts = [p[1] for p in pairs]
    batch_results = engine.tokenize_batch(texts)

    for part_id, tokens in zip(ids, batch_results):
        seen_in_part: set[str] = set()
        for t in tokens:
            if t.tag not in NOUN_TAGS:
                continue
            term = t.form
            if len(term) < TH_MIN_LEN:
                continue
            if term in existing:
                continue
            freq[term] += 1
            pos.setdefault(term, Counter())[t.tag] += 1
            if term not in seen_in_part:
                doc_seen.setdefault(term, set()).add(part_id)
                seen_in_part.add(term)
    return len(rows)


def build_insert_rows(
    freq: Counter,
    pos: dict[str, Counter],
    doc_seen: dict[str, set],
) -> tuple[list[dict], Counter]:
    """후보별 자동 검증 + INSERT row 빌드. Returns: (rows, stats)."""
    rows = []
    stats: Counter = Counter()
    for term, f in freq.items():
        df = len(doc_seen.get(term, ()))
        verified, reason, main_pos = auto_verify_generic(term, pos[term], f, df)
        rows.append({
            "term": term,
            "pos_tag": main_pos or "NNG",
            "term_type": "GENERIC",
            "frequency": f,
            "score": tfidf(f, df),
            "source": "law_article_part.part_text:kiwi-extraction",
            "verified": verified,
            "notes": reason,
        })
        stats[reason] += 1
    return rows, stats


def insert_batches(sb, rows: list[dict], dry_run: bool = False) -> int:
    """일괄 INSERT. ON CONFLICT (term) DO NOTHING.

    이미 process_chunk에서 existing 필터링했으므로 정상적으로 모두 신규.
    race-safety 위해 ignore_duplicates=True 사용.
    """
    if dry_run:
        verified_count = sum(1 for r in rows if r["verified"])
        print(f"  [DRY-RUN] 총 {len(rows)}건 (verified=true {verified_count}, "
              f"verified=false {len(rows) - verified_count})")
        return len(rows)

    inserted = 0
    n_batches = (len(rows) + INSERT_BATCH - 1) // INSERT_BATCH
    for i in range(0, len(rows), INSERT_BATCH):
        batch = rows[i:i + INSERT_BATCH]
        try:
            res = (
                sb.table("dict_legal_terms")
                .upsert(batch, on_conflict="term", ignore_duplicates=True)
                .execute()
            )
            inserted += len(res.data or [])
        except Exception as e:
            logger.error("Batch INSERT 실패 (offset=%d): %s", i, e)
            raise
        batch_idx = i // INSERT_BATCH + 1
        if batch_idx % 5 == 0 or batch_idx == n_batches:
            print(f"  INSERT 진행: {batch_idx}/{n_batches} batches")
    return inserted


# ----- main -----

def main() -> int:
    parser = argparse.ArgumentParser(description="Track C GENERIC 명사 후보 추출")
    parser.add_argument("--dry-run", action="store_true", help="INSERT 없이 통계만 출력")
    parser.add_argument("--chunk", type=int, default=1000, help="chunk size (default 1000)")
    parser.add_argument("--limit", type=int, default=0, help="처리할 row 수 제한 (0=전체)")
    args = parser.parse_args()

    print("=" * 70)
    print(f"Track C GENERIC 추출 (dry_run={args.dry_run}, chunk={args.chunk}, "
          f"limit={args.limit or 'ALL'})")
    print("=" * 70)

    sb = get_supabase()

    # [1] 환경 점검
    print("\n[1] 환경 점검")
    existing = fetch_existing_terms(sb)
    print(f"  기존 dict_legal_terms term: {len(existing)}건 (제외 대상)")
    if len(existing) < 100:
        print(f"  ❌ dict_legal_terms 크기 의심 ({len(existing)} < 100, "
              f"v1.1 464건 + QUARANTINE 4건 기대)")
        return 1

    engine = MorphemeEngine(supabase=sb)
    print(f"  MorphemeEngine 자동 로드: {engine.user_dict_size}건")

    # [2] chunk 단위 처리
    target = args.limit if args.limit else TOTAL_DOCS
    print(f"\n[2] chunk 단위 추출 (대상 {target}건, chunk_size={args.chunk})")

    freq: Counter = Counter()
    pos: dict[str, Counter] = {}
    doc_seen: dict[str, set] = {}

    processed = 0
    offset = 0
    chunk_idx = 0
    t0 = time.time()
    last_log = t0

    while processed < target:
        remaining = target - processed
        chunk_size = min(args.chunk, remaining)
        rows = fetch_part_chunk(sb, offset, chunk_size)
        if not rows:
            break
        try:
            n = process_chunk(rows, engine, existing, freq, pos, doc_seen)
        except Exception as e:
            logger.error("chunk 실패 (offset=%d): %s", offset, e)
            return 2
        processed += n
        offset += len(rows)
        chunk_idx += 1

        now = time.time()
        if now - last_log >= 10 or processed >= target:
            rate = processed / (now - t0) if (now - t0) > 0 else 0
            eta = (target - processed) / rate if rate > 0 else 0
            print(f"  chunk {chunk_idx}: processed={processed}/{target} "
                  f"({100 * processed / target:.1f}%) "
                  f"unique={len(freq)} rate={rate:.0f}/s eta={eta:.0f}s")
            last_log = now

    elapsed = time.time() - t0
    print(f"\n  처리 완료: {processed}건 ({elapsed:.1f}s)")
    print(f"  unique 명사 후보: {len(freq)}건")

    # [3] 자동 검증
    print("\n[3] 룰베이스 자동 검증")
    insert_rows, stats = build_insert_rows(freq, pos, doc_seen)
    verified_count = sum(1 for r in insert_rows if r["verified"])
    print(f"  verified=true:  {verified_count}")
    print(f"  verified=false: {len(insert_rows) - verified_count}")
    print("  사유별 분포 (top 10):")
    for reason, cnt in stats.most_common(10):
        print(f"    {reason}: {cnt}")

    # [4] INSERT
    print("\n[4] INSERT")
    try:
        inserted = insert_batches(sb, insert_rows, dry_run=args.dry_run)
    except Exception as e:
        logger.error("INSERT 실패: %s", e)
        return 3
    print(f"  완료: {inserted}건")

    print("\n" + "=" * 70)
    tag = "[DRY-RUN] " if args.dry_run else ""
    print(f"{tag}Track C GENERIC 추출 완료 (verified=true {verified_count})")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
