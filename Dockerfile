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

# Railway 등은 $PORT 를 주입함 — 고정 8080만 쓰면 리슨 실패할 수 있음
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
