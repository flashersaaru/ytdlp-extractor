import os
import json
import subprocess
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="YT-DLP Extractor")

# ---------- CONFIG ----------
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")  # optional security
COOKIES_PATH = os.getenv("COOKIES_PATH", "/app/cookies.txt")
# ----------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExtractRequest(BaseModel):
    url: str


def yt_dlp_version():
    try:
        out = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except Exception as e:
        return f"error: {e}"


@app.get("/")
def health():
    return {"status": "ok", "yt_dlp_version": yt_dlp_version()}


@app.post("/api/update")
def update_ytdlp():
    """Manually trigger yt-dlp upgrade."""
    try:
        out = subprocess.run(
            ["pip", "install", "--no-cache-dir", "--upgrade", "yt-dlp"],
            capture_output=True, text=True, timeout=180
        )
        return {
            "success": out.returncode == 0,
            "new_version": yt_dlp_version(),
            "log_tail": out.stdout[-300:]
        }
    except Exception as e:
        raise HTTPException(500, f"update failed: {e}")


@app.post("/api/extract")
def extract(req: ExtractRequest, authorization: str = Header(None)):
    # --- Auth check ---
    if AUTH_TOKEN:
        if not authorization or authorization != f"Bearer {AUTH_TOKEN}":
            raise HTTPException(401, "unauthorized")

    url = req.url.strip()
    if "youtube.com" not in url and "youtu.be" not in url:
        raise HTTPException(400, "Only YouTube URLs allowed")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b",
        "-j",  # dump single JSON
        url,
    ]

    if os.path.exists(COOKIES_PATH):
        cmd[1:1] = ["--cookies", COOKIES_PATH]

    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "yt-dlp timed out")

    if out.returncode != 0:
        raise HTTPException(500, f"yt-dlp error: {out.stderr[-400:]}")

    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        raise HTTPException(500, "Invalid JSON from yt-dlp")

    formats = data.get("formats", [])

    # Pick best video (<=720p, video only) and best audio (audio only)
    video_fmt = None
    audio_fmt = None

    for f in formats:
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        height = f.get("height") or 0

        # video-only, <=720p, prefer mp4
        if vcodec != "none" and acodec == "none" and height <= 720:
            if video_fmt is None:
                video_fmt = f
            else:
                # prefer higher resolution but not above 720
                if (f.get("height") or 0) > (video_fmt.get("height") or 0):
                    video_fmt = f

        # audio-only, prefer m4a
        if acodec != "none" and vcodec == "none":
            if audio_fmt is None:
                audio_fmt = f
            else:
                # prefer m4a over webm
                if "m4a" in (f.get("ext") or "") and "m4a" not in (audio_fmt.get("ext") or ""):
                    audio_fmt = f

    if not video_fmt or not audio_fmt:
        raise HTTPException(500, "Could not find suitable video/audio streams")

    return {
        "title": data.get("title"),
        "duration": data.get("duration"),
        "thumbnail": data.get("thumbnail"),
        "video_url": video_fmt.get("url"),
        "video_headers": video_fmt.get("http_headers", {}),
        "audio_url": audio_fmt.get("url"),
        "audio_headers": audio_fmt.get("http_headers", {}),
        "yt_dlp_version": yt_dlp_version(),
}
