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
        download_status[video_id] = {
            "status": "error", 
            "error": "No cookies available",
            "message": "No cookies available"
        }
        return

    ydl_opts = get_ydl_opts(video_id, format_str, cookie_file)

    try:
        download_status[video_id] = {"status": "downloading", "type": media_type}
        print(f"📥 Downloading {video_id} ({media_type})")

        await asyncio.to_thread(yt_dlp.YoutubeDL(ydl_opts).download, [url])

        files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
        if not files:
            raise Exception("File not found after download")

        file = files[0]
        print(f"✅ Done: {file.name}")
        download_status[video_id] = {
            "status": "done",
            "filename": file.name,
            "format": file.suffix[1:],
            "type": media_type,
            "link": f"{BASE_URL}/download/{file.name}"
        }
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error downloading {video_id}: {error_msg}")
        download_status[video_id] = {
            "status": "error", 
            "error": error_msg,
            "message": error_msg
        }

def get_response(video_id: str, status_info: dict):
    """Generate consistent response format"""
    response = {
        "video_id": video_id,
        "status": status_info.get("status", "unknown")
    }
    
    if status_info["status"] == "done":
        response.update({
            "format": status_info.get("format"),
            "link": status_info.get("link")
        })
    elif status_info["status"] == "error":
        response.update({
            "error": status_info.get("error", "Unknown error"),
            "message": status_info.get("message", status_info.get("error", "Unknown error"))
        })
    elif status_info["status"] == "downloading":
        response["message"] = "Download in progress"
    
    return response

@app.get("/")
async def root():
    cookies = list(COOKIES_DIR.glob("*.txt"))
    return {
        "name": "YouTube API",
        "version": "3.2",
        "status": "online",
        "cookies": len(cookies),
        "files": [c.name for c in cookies],
        "endpoints": {
            "test": "/test-cookies",
            "song": "/song/{id}?api=KEY",
            "video": "/video/{id}?api=KEY",
            "status": "/status/{id}"
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
    
    print(f"🎵 Song request for: {video_id}")

    # Check if file already exists
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        print(f"✅ File exists: {files[0].name}")
        return {
            "status": "done",
            "video_id": video_id,
            "format": files[0].suffix[1:],
            "link": f"{BASE_URL}/download/{files[0].name}"
        }

    # Check if download is in progress or completed
    if video_id in download_status:
        print(f"📊 Returning cached status: {download_status[video_id]['status']}")
        return get_response(video_id, download_status[video_id])

    # Start new download
    url = f"https://www.youtube.com/watch?v={video_id}"
    background_tasks.add_task(download_media, video_id, url, "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", "audio")
    print(f"🔄 Started background download for: {video_id}")
    return {"status": "downloading", "video_id": video_id, "message": "Download started"}

@app.get("/video/{video_id}")
async def download_video(video_id: str, api: str, background_tasks: BackgroundTasks):
    validate_api_key(api)
    
    print(f"🎬 Video request for: {video_id}")

    # Check if file already exists
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        print(f"✅ File exists: {files[0].name}")
        return {
            "status": "done",
            "video_id": video_id,
            "format": files[0].suffix[1:],
            "link": f"{BASE_URL}/download/{files[0].name}"
        }

    # Check if download is in progress or completed
    if video_id in download_status:
        print(f"📊 Returning cached status: {download_status[video_id]['status']}")
        return get_response(video_id, download_status[video_id])

    # Start new download
    url = f"https://www.youtube.com/watch?v={video_id}"
    background_tasks.add_task(download_media, video_id, url, "best[height<=720][ext=mp4]/best[height<=720]/best", "video")
    print(f"🔄 Started background download for: {video_id}")
    return {"status": "downloading", "video_id": video_id, "message": "Download started"}

@app.get("/status/{video_id}")
async def check_status(video_id: str):
    """Check download status - can be called without API key for polling"""
    print(f"📊 Status check for: {video_id}")
    
    # Check if file exists
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        print(f"✅ File found: {files[0].name}")
        return {
            "status": "done",
            "video_id": video_id,
            "format": files[0].suffix[1:],
            "link": f"{BASE_URL}/download/{files[0].name}"
        }
    
    # Check download status
    if video_id in download_status:
        status_info = download_status[video_id]
        print(f"📊 Status: {status_info['status']}")
        return get_response(video_id, status_info)
    
    print(f"❓ Not found: {video_id}")
    return {"status": "not_found", "video_id": video_id, "message": "Video ID not found"}

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        print(f"❌ File not found: {filename}")
        raise HTTPException(status_code=404, detail="File not found")
    
    print(f"📤 Serving file: {filename}")
    return FileResponse(
        path=file_path, 
        filename=filename,
        media_type="application/octet-stream"
    )

@app.delete("/clear/{video_id}")
async def clear_cache(video_id: str, api: str):
    """Clear cached download status and file"""
    validate_api_key(api)
    
    # Remove from status dict
    if video_id in download_status:
        del download_status[video_id]
    
    # Remove file
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    for file in files:
        file.unlink()
    
    return {"status": "cleared", "video_id": video_id}

@app.on_event("startup")
async def startup():
    cookies = list(COOKIES_DIR.glob("*.txt"))
    print("="*50)
    print(f"🚀 API Started")
    print(f"🍪 Cookies: {len(cookies)}")
    print(f"📁 Files: {[c.name for c in cookies]}")
    print(f"🔑 Key: {VALID_API_KEY}")
    print(f"🌐 Base URL: {BASE_URL}")
    print("="*50)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
