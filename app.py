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
    if not cookie_files:
        print("⚠️ No cookies found!")
        return None
    cookie = random.choice(cookie_files)
    print(f"🍪 Using: {cookie.name}")
    return str(cookie)

def get_ydl_opts(video_id: str, format_str: str, cookie_file: str = None):
    opts = {
        "format": format_str,
        "outtmpl": str(DOWNLOAD_DIR / f"{video_id}.%(ext)s"),
        "quiet": False,
        "no_warnings": False,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 5,
        "nocheckcertificate": True,
        "geo_bypass": True,
    }
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts

async def download_media(video_id: str, url: str, format_str: str, media_type: str):
    cookie_file = get_cookie_file()
    
    if not cookie_file:
        download_status[video_id] = {"status": "error", "error": "No cookies"}
        return
    
    ydl_opts = get_ydl_opts(video_id, format_str, cookie_file)

    try:
        download_status[video_id] = {"status": "downloading", "type": media_type}
        print(f"📥 Downloading {video_id}")
        
        await asyncio.to_thread(yt_dlp.YoutubeDL(ydl_opts).download, [url])

        files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
        if not files:
            raise Exception("File not found")

        file = files[0]
        print(f"✅ Done: {file.name}")
        download_status[video_id] = {
            "status": "done",
            "filename": file.name,
            "format": file.suffix[1:],
            "type": media_type
        }
    except Exception as e:
        print(f"❌ Error: {e}")
        download_status[video_id] = {"status": "error", "error": str(e)}

def get_response(video_id: str, status_info: dict):
    if status_info["status"] == "done":
        return {
            "status": "done",
            "video_id": video_id,
            "format": status_info["format"],
            "link": f"{BASE_URL}/download/{status_info['filename']}"
        }
    return {**status_info, "video_id": video_id}

@app.get("/")
async def root():
    cookies = list(COOKIES_DIR.glob("*.txt"))
    return {
        "name": "YouTube API",
        "version": "3.1",
        "cookies": len(cookies),
        "files": [c.name for c in cookies],
        "endpoints": {
            "test": "/test-cookies",
            "song": "/song/{id}?api=KEY",
            "video": "/video/{id}?api=KEY"
        }
    }

@app.get("/test-cookies")
async def test_cookies():
    cookies = list(COOKIES_DIR.glob("*.txt"))
    
    if not cookies:
        return {"error": "No cookies", "dir": str(COOKIES_DIR.absolute())}
    
    results = {}
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    for cookie in cookies:
        try:
            opts = {"quiet": True, "cookiefile": str(cookie), "skip_download": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            results[cookie.name] = {"status": "✅", "title": info.get("title")}
        except Exception as e:
            results[cookie.name] = {"status": "❌", "error": str(e)[:80]}
    
    working = sum(1 for r in results.values() if r["status"] == "✅")
    return {"total": len(cookies), "working": working, "results": results}

@app.get("/song/{video_id}")
async def download_song(video_id: str, api: str, background_tasks: BackgroundTasks):
    validate_api_key(api)

    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        return {
            "status": "done",
            "video_id": video_id,
            "format": files[0].suffix[1:],
            "link": f"{BASE_URL}/download/{files[0].name}"
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
        return {
            "status": "done",
            "video_id": video_id,
            "format": files[0].suffix[1:],
            "link": f"{BASE_URL}/download/{files[0].name}"
        }

    if video_id in download_status:
        return get_response(video_id, download_status[video_id])

    url = f"https://www.youtube.com/watch?v={video_id}"
    background_tasks.add_task(download_media, video_id, url, "best[height<=720]/best", "video")
    return {"status": "downloading", "video_id": video_id}

@app.get("/status/{video_id}")
async def check_status(video_id: str):
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        return {
            "status": "done",
            "video_id": video_id,
            "link": f"{BASE_URL}/download/{files[0].name}"
        }
    if video_id in download_status:
        return {**download_status[video_id], "video_id": video_id}
    return {"status": "not_found", "video_id": video_id}

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path=file_path, filename=filename)

@app.on_event("startup")
async def startup():
    cookies = list(COOKIES_DIR.glob("*.txt"))
    print("="*50)
    print(f"🚀 API Started")
    print(f"🍪 Cookies: {len(cookies)}")
    print(f"📁 Files: {[c.name for c in cookies]}")
    print(f"🔑 Key: {VALID_API_KEY}")
    print("="*50)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
