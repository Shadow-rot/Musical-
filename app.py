from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import yt_dlp
import os
import asyncio
import uvicorn

app = FastAPI(title="YouTube Download API")

# ---------------- CONFIG ---------------- #

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

VALID_API_KEY = os.getenv("API_KEY", "shadwo")

def validate_api_key(api_key: str):
    if api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ---------------- ROOT ---------------- #

@app.get("/")
async def root():
    return {
        "name": "My YouTube Download API",
        "status": "running",
        "version": "1.0",
        "endpoints": {
            "song": "/song/{video_id}?api=YOUR_KEY",
            "video": "/video/{video_id}?api=YOUR_KEY",
            "status": "/status/{video_id}",
            "download": "/download/{filename}"
        }
    }

# ---------------- SONG ---------------- #

@app.get("/song/{video_id}")
async def download_song(video_id: str, api: str):
    validate_api_key(api)

    url = f"https://www.youtube.com/watch?v={video_id}"
    output = DOWNLOAD_DIR / f"{video_id}.%(ext)s"

    ydl_opts = {
        "format": "bestaudio",
        "outtmpl": str(output),
        "quiet": True,
        "no_warnings": True,
    }

    try:
        await asyncio.to_thread(
            yt_dlp.YoutubeDL(ydl_opts).download, [url]
        )

        files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
        if not files:
            raise HTTPException(500, "Download failed")

        file = files[0]

        return {
            "status": "done",
            "video_id": video_id,
            "format": file.suffix[1:],
            "download": f"/download/{file.name}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------- VIDEO ---------------- #

@app.get("/video/{video_id}")
async def download_video(video_id: str, api: str):
    validate_api_key(api)

    url = f"https://www.youtube.com/watch?v={video_id}"
    output = DOWNLOAD_DIR / f"{video_id}.%(ext)s"

    ydl_opts = {
        "format": "best[height<=720]",
        "outtmpl": str(output),
        "quiet": True,
        "no_warnings": True,
    }

    try:
        await asyncio.to_thread(
            yt_dlp.YoutubeDL(ydl_opts).download, [url]
        )

        files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
        if not files:
            raise HTTPException(500, "Download failed")

        file = files[0]

        return {
            "status": "done",
            "video_id": video_id,
            "format": file.suffix[1:],
            "download": f"/download/{file.name}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------- STATUS ---------------- #

@app.get("/status/{video_id}")
async def check_status(video_id: str):
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))

    if files:
        file = files[0]
        return {
            "status": "done",
            "video_id": video_id,
            "format": file.suffix[1:],
            "filename": file.name
        }

    return {"status": "not_found", "video_id": video_id}

# ---------------- DOWNLOAD ---------------- #

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = DOWNLOAD_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )

# ---------------- START ---------------- #

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)