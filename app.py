from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import yt_dlp
import os
import asyncio
from pathlib import Path
import uvicorn

app = FastAPI(title="YouTube Download API")

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# API Key validation
VALID_API_KEY = os.getenv("API_KEY", "shadwo")

def validate_api_key(api_key: str):
    if api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

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

@app.get("/song/{video_id}")
async def download_song(video_id: str, api: str):
    validate_api_key(api)

    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        output_path = DOWNLOAD_DIR / f"{video_id}.%(ext)s"

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(output_path),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
        }

        # Download in background
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, 
            lambda: yt_dlp.YoutubeDL(ydl_opts).download([url])
        )

        # Find the downloaded file
        downloaded_file = None
        for ext in ['mp3', 'm4a', 'webm']:
            file_path = DOWNLOAD_DIR / f"{video_id}.{ext}"
            if file_path.exists():
                downloaded_file = file_path
                break

        if not downloaded_file:
            return {"status": "downloading", "message": "Processing..."}

        # Return download link
        download_url = f"/download/{downloaded_file.name}"
        return {
            "status": "done",
            "link": download_url,
            "format": downloaded_file.suffix.replace('.', ''),
            "video_id": video_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/video/{video_id}")
async def download_video(video_id: str, api: str):
    validate_api_key(api)

    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        output_path = DOWNLOAD_DIR / f"{video_id}.%(ext)s"

        ydl_opts = {
            'format': 'best[height<=720][ext=mp4]',
            'outtmpl': str(output_path),
            'quiet': True,
            'no_warnings': True,
        }

        # Download in background
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, 
            lambda: yt_dlp.YoutubeDL(ydl_opts).download([url])
        )

        # Find the downloaded file
        downloaded_file = None
        for ext in ['mp4', 'webm', 'mkv']:
            file_path = DOWNLOAD_DIR / f"{video_id}.{ext}"
            if file_path.exists():
                downloaded_file = file_path
                break

        if not downloaded_file:
            return {"status": "downloading", "message": "Processing..."}

        # Return download link
        download_url = f"/download/{downloaded_file.name}"
        return {
            "status": "done",
            "link": download_url,
            "format": downloaded_file.suffix.replace('.', ''),
            "video_id": video_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/{video_id}")
async def check_status(video_id: str):
    # Check if file exists
    for ext in ['mp3', 'm4a', 'webm', 'mp4', 'mkv']:
        file_path = DOWNLOAD_DIR / f"{video_id}.{ext}"
        if file_path.exists():
            return {
                "status": "done",
                "video_id": video_id,
                "format": ext
            }

    return {"status": "not_found", "video_id": video_id}

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = DOWNLOAD_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)