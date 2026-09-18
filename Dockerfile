FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libcairo2-dev \
    pkg-config \
    python3-dev \
    libffi-dev \
    gcc \
    fonts-nanum \
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 지식인 승인(Playwright) — Railway/런타임에서 브라우저 사용
RUN playwright install chromium
RUN playwright install-deps
COPY . .

# WO-TAI-SHARED-SEARCH-001: build the deterministic runtime projection
# during image build (RC-A remediation: the artifact is not tracked in
# git and must be generated at build time — leaving it out reproduces
# HTTP 503 on /search-dict/*). The compiler has zero runtime deps
# beyond stdlib; expected SHA is pinned in
# tools/search_dict/artifacts/BUILD_SHA256SUMS.txt (line 15). Only the
# two runtime files are copied back — BUILD_SHA256SUMS.txt itself is
# left untouched so its richer manifest header is preserved.
RUN python3 scripts/build_search_dict_runtime.py \
        --outdir tools/search_dict/artifacts \
        --tmpdir /tmp/tai-search-dict-build \
        --seed seed_v2

# Railway 등은 $PORT 를 주입함 — 고정 8080만 쓰면 리슨 실패할 수 있음
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
