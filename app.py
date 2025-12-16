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

# ---------------- CONFIG ---------------- #

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

COOKIES_DIR = Path("cookies")
COOKIES_DIR.mkdir(exist_ok=True)

VALID_API_KEY = os.getenv("API_KEY", "shadwo")

# Track download status
download_status: Dict[str, dict] = {}

def validate_api_key(api_key: str):
    if api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ---------------- COOKIE HELPER ---------------- #

def get_random_cookie():
    """Get a random cookie file from the cookies directory"""
    cookie_files = list(COOKIES_DIR.glob("*.txt"))
    if not cookie_files:
        print("⚠️ No cookie files found in cookies/ directory")
        return None
    
    cookie_file = random.choice(cookie_files)
    print(f"🍪 Using cookie file: {cookie_file.name}")
    return str(cookie_file)

# ---------------- HELPERS ---------------- #

async def download_youtube_audio(video_id: str, url: str):
    """Background task to download audio"""
    output = DOWNLOAD_DIR / f"{video_id}.%(ext)s"
    
    cookie_file = get_random_cookie()
    
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output),
        "quiet": False,  # Changed to see errors
        "no_warnings": False,
        "extract_flat": False,
        "ignoreerrors": False,
    }
    
    # Add cookies if available
    if cookie_file:
        ydl_opts["cookiefile"] = cookie_file
    
    try:
        download_status[video_id] = {"status": "downloading", "type": "audio"}
        print(f"🎵 Starting audio download for {video_id}")
        
        await asyncio.to_thread(
            yt_dlp.YoutubeDL(ydl_opts).download, [url]
        )
        
        files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
        if not files:
            error_msg = "Download completed but file not found"
            print(f"❌ {error_msg}")
            download_status[video_id] = {"status": "error", "error": error_msg}
            return
        
        file = files[0]
        print(f"✅ Audio download complete: {file.name}")
        download_status[video_id] = {
            "status": "done",
            "filename": file.name,
            "format": file.suffix[1:],
            "type": "audio"
        }
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Audio download error for {video_id}: {error_msg}")
        download_status[video_id] = {"status": "error", "error": error_msg}

async def download_youtube_video(video_id: str, url: str):
    """Background task to download video"""
    output = DOWNLOAD_DIR / f"{video_id}.%(ext)s"
    
    cookie_file = get_random_cookie()
    
    ydl_opts = {
        "format": "best[height<=720][width<=1280]/best",
        "outtmpl": str(output),
        "quiet": False,
        "no_warnings": False,
        "extract_flat": False,
        "ignoreerrors": False,
    }
    
    # Add cookies if available
    if cookie_file:
        ydl_opts["cookiefile"] = cookie_file
    
    try:
        download_status[video_id] = {"status": "downloading", "type": "video"}
        print(f"🎥 Starting video download for {video_id}")
        
        await asyncio.to_thread(
            yt_dlp.YoutubeDL(ydl_opts).download, [url]
        )
        
        files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
        if not files:
            error_msg = "Download completed but file not found"
            print(f"❌ {error_msg}")
            download_status[video_id] = {"status": "error", "error": error_msg}
            return
        
        file = files[0]
        print(f"✅ Video download complete: {file.name}")
        download_status[video_id] = {
            "status": "done",
            "filename": file.name,
            "format": file.suffix[1:],
            "type": "video"
        }
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Video download error for {video_id}: {error_msg}")
        download_status[video_id] = {"status": "error", "error": error_msg}

# ---------------- ROOT ---------------- #

@app.get("/")
async def root():
    cookie_files = list(COOKIES_DIR.glob("*.txt"))
    return {
        "name": "My YouTube Download API",
        "status": "running",
        "version": "2.1",
        "cookies_loaded": len(cookie_files),
        "endpoints": {
            "song": "/song/{video_id}?api=YOUR_KEY",
            "video": "/video/{video_id}?api=YOUR_KEY",
            "status": "/status/{video_id}",
            "download": "/download/{filename}"
        },
        "info": "API now uses async downloads with cookie support. Check /status/{video_id} or poll the same endpoint until status=done"
    }

# ---------------- SONG ---------------- #

@app.get("/song/{video_id}")
async def download_song(video_id: str, api: str, background_tasks: BackgroundTasks):
    validate_api_key(api)
    
    # Check if file already exists
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        file = files[0]
        base_url = os.getenv("BASE_URL", "https://youtube-api-0qwc.onrender.com")
        return {
            "status": "done",
            "video_id": video_id,
            "format": file.suffix[1:],
            "link": f"{base_url}/download/{file.name}",
            "download": f"/download/{file.name}"
        }
    
    # Check if already downloading
    if video_id in download_status:
        status_info = download_status[video_id]
        if status_info["status"] == "done":
            base_url = os.getenv("BASE_URL", "https://youtube-api-0qwc.onrender.com")
            return {
                "status": "done",
                "video_id": video_id,
                "format": status_info["format"],
                "link": f"{base_url}/download/{status_info['filename']}",
                "download": f"/download/{status_info['filename']}"
            }
        elif status_info["status"] == "downloading":
            return {
                "status": "downloading",
                "video_id": video_id,
                "message": "Download in progress, please check again"
            }
        elif status_info["status"] == "error":
            # Clear error status and retry
            del download_status[video_id]
    
    # Start download in background
    url = f"https://www.youtube.com/watch?v={video_id}"
    background_tasks.add_task(download_youtube_audio, video_id, url)
    
    return {
        "status": "downloading",
        "video_id": video_id,
        "message": "Download started, check status or poll this endpoint"
    }

# ---------------- VIDEO ---------------- #

@app.get("/video/{video_id}")
async def download_video(video_id: str, api: str, background_tasks: BackgroundTasks):
    validate_api_key(api)
    
    # Check if file already exists
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        file = files[0]
        base_url = os.getenv("BASE_URL", "https://youtube-api-0qwc.onrender.com")
        return {
            "status": "done",
            "video_id": video_id,
            "format": file.suffix[1:],
            "link": f"{base_url}/download/{file.name}",
            "download": f"/download/{file.name}"
        }
    
    # Check if already downloading
    if video_id in download_status:
        status_info = download_status[video_id]
        if status_info["status"] == "done":
            base_url = os.getenv("BASE_URL", "https://youtube-api-0qwc.onrender.com")
            return {
                "status": "done",
                "video_id": video_id,
                "format": status_info["format"],
                "link": f"{base_url}/download/{status_info['filename']}",
                "download": f"/download/{status_info['filename']}"
            }
        elif status_info["status"] == "downloading":
            return {
                "status": "downloading",
                "video_id": video_id,
                "message": "Download in progress, please check again"
            }
        elif status_info["status"] == "error":
            # Clear error status and retry
            del download_status[video_id]
    
    # Start download in background
    url = f"https://www.youtube.com/watch?v={video_id}"
    background_tasks.add_task(download_youtube_video, video_id, url)
    
    return {
        "status": "downloading",
        "video_id": video_id,
        "message": "Download started, check status or poll this endpoint"
    }

# ---------------- STATUS ---------------- #

@app.get("/status/{video_id}")
async def check_status(video_id: str):
    # Check if file exists on disk
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    
    if files:
        file = files[0]
        base_url = os.getenv("BASE_URL", "https://youtube-api-0qwc.onrender.com")
        return {
            "status": "done",
            "video_id": video_id,
            "format": file.suffix[1:],
            "filename": file.name,
            "link": f"{base_url}/download/{file.name}"
        }
    
    # Check in-memory status
    if video_id in download_status:
        return {**download_status[video_id], "video_id": video_id}
    
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

# ---------------- CLEANUP ---------------- #

@app.on_event("startup")
async def startup_event():
    """Clean up old downloads on startup"""
    cookie_files = list(COOKIES_DIR.glob("*.txt"))
    print(f"✅ API Started - Download directory: {DOWNLOAD_DIR.absolute()}")
    print(f"✅ Cookies directory: {COOKIES_DIR.absolute()}")
    print(f"✅ Found {len(cookie_files)} cookie file(s)")
    print(f"✅ API Key: {VALID_API_KEY}")

# ---------------- START ---------------- #

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
