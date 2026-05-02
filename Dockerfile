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
# playwright 패키지는 포함하되, Chromium 바이너리는 이미지에서 생략(RAM/빌드 안정).
# 지식인 자동입력 사용 시: 배포 후 한 번 `playwright install chromium` 또는 전용 워커 이미지에서 설치.
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Railway 등은 $PORT 를 주입함 — 고정 8080만 쓰면 리슨 실패할 수 있음
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
