from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pathlib import Path
import yt_dlp
import os
import asyncio
import uvicorn
from typing import Dict
import random

app = FastAPI(title="YouTube Download API")

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
COOKIES_DIR = Path("cookies")
COOKIES_DIR.mkdir(exist_ok=True)

VALID_API_KEY = os.getenv("API_KEY", "shadwo")
BASE_URL = os.getenv("BASE_URL", "https://youtube-api-0qwc.onrender.com")

download_status: Dict[str, dict] = {}

def validate_api_key(api_key: str):
    if api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

def get_cookie_file():
    cookie_files = list(COOKIES_DIR.glob("*.txt"))
    return str(random.choice(cookie_files)) if cookie_files else None

def get_ydl_opts(video_id: str, format_str: str, cookie_file: str = None):
    opts = {
        "format": format_str,
        "outtmpl": str(DOWNLOAD_DIR / f"{video_id}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 5,
    }
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts

async def download_media(video_id: str, url: str, format_str: str, media_type: str):
    cookie_file = get_cookie_file()
    ydl_opts = get_ydl_opts(video_id, format_str, cookie_file)
    
    try:
        download_status[video_id] = {"status": "downloading", "type": media_type}
        await asyncio.to_thread(yt_dlp.YoutubeDL(ydl_opts).download, [url])
        
        files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
        if not files:
            raise Exception("File not found after download")
        
        file = files[0]
        download_status[video_id] = {
            "status": "done",
            "filename": file.name,
            "format": file.suffix[1:],
            "type": media_type
        }
    except Exception as e:
        download_status[video_id] = {"status": "error", "error": str(e)}

def get_response(video_id: str, status_info: dict):
    if status_info["status"] == "done":
        return {
            "status": "done",
            "video_id": video_id,
            "format": status_info["format"],
            "link": f"{BASE_URL}/download/{status_info['filename']}",
            "download": f"/download/{status_info['filename']}"
        }
    return {**status_info, "video_id": video_id}

@app.get("/")
async def root():
    cookie_count = len(list(COOKIES_DIR.glob("*.txt")))
    return {
        "name": "YouTube Download API",
        "status": "running",
        "version": "3.0",
        "cookies_loaded": cookie_count,
        "endpoints": {
            "song": "/song/{video_id}?api=YOUR_KEY",
            "video": "/video/{video_id}?api=YOUR_KEY",
            "status": "/status/{video_id}",
            "download": "/download/{filename}"
        }
    }

@app.get("/song/{video_id}")
async def download_song(video_id: str, api: str, background_tasks: BackgroundTasks):
    validate_api_key(api)
    
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        file = files[0]
        return {
            "status": "done",
            "video_id": video_id,
            "format": file.suffix[1:],
            "link": f"{BASE_URL}/download/{file.name}",
            "download": f"/download/{file.name}"
        }
    
    if video_id in download_status:
        return get_response(video_id, download_status[video_id])
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    background_tasks.add_task(download_media, video_id, url, "bestaudio/best", "audio")
    
    return {"status": "downloading", "video_id": video_id}

@app.get("/video/{video_id}")
async def download_video(video_id: str, api: str, background_tasks: BackgroundTasks):
    validate_api_key(api)
    
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        file = files[0]
        return {
            "status": "done",
            "video_id": video_id,
            "format": file.suffix[1:],
            "link": f"{BASE_URL}/download/{file.name}",
            "download": f"/download/{file.name}"
        }
    
    if video_id in download_status:
        return get_response(video_id, download_status[video_id])
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    background_tasks.add_task(download_media, video_id, url, "best[height<=720][width<=1280]/best", "video")
    
    return {"status": "downloading", "video_id": video_id}

@app.get("/status/{video_id}")
async def check_status(video_id: str):
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    
    if files:
        file = files[0]
        return {
            "status": "done",
            "video_id": video_id,
            "format": file.suffix[1:],
            "filename": file.name,
            "link": f"{BASE_URL}/download/{file.name}"
        }
    
    if video_id in download_status:
        return {**download_status[video_id], "video_id": video_id}
    
    return {"status": "not_found", "video_id": video_id}

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

@app.on_event("startup")
async def startup_event():
    cookie_count = len(list(COOKIES_DIR.glob("*.txt")))
    print(f"API Started | Downloads: {DOWNLOAD_DIR.absolute()}")
    print(f"Cookies: {cookie_count} file(s) | API Key: {VALID_API_KEY}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)