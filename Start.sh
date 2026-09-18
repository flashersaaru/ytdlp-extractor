#!/bin/sh
set -e

echo "==> Upgrading yt-dlp to latest..."
pip install --no-cache-dir --upgrade yt-dlp || echo "Upgrade failed, using existing version"

echo "==> yt-dlp version: $(yt-dlp --version)"

echo "==> Starting server..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
