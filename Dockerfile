FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Force latest yt-dlp at build time
RUN pip install --no-cache-dir --upgrade yt-dlp

COPY . .

RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"]
