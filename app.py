from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import yt_dlp
import os
import asyncio
import uvicorn
from typing import Dict, Optional
import random
import time
import logging
import hashlib
from collections import defaultdict
from datetime import datetime
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Media Download API", version="4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
COOKIES_DIR = Path("cookies")
COOKIES_DIR.mkdir(exist_ok=True)

VALID_API_KEY = os.getenv("API_KEY", "shadwo")
BASE_URL = os.getenv("BASE_URL", "https://youtube-api-0qwc.onrender.com")
MAX_FILE_AGE = int(os.getenv("MAX_FILE_AGE", "3600"))
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "3"))

download_status: Dict[str, dict] = {}
cookie_cache = {"last_refresh": 0, "cookies": [], "index": 0}
request_tracker = defaultdict(list)
download_semaphore = asyncio.Semaphore(MAX_CONCURRENT)

def validate_api_key(api_key: str):
    if not api_key or api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

def check_rate_limit(api_key: str, limit: int = 20, window: int = 60):
    now = datetime.now().timestamp()
    key_hash = hashlib.md5(api_key.encode()).hexdigest()
    
    request_tracker[key_hash] = [
        t for t in request_tracker[key_hash] 
        if now - t < window
    ]
    
    if len(request_tracker[key_hash]) >= limit:
        raise HTTPException(
            status_code=429, 
            detail="Rate limit exceeded"
        )
    
    request_tracker[key_hash].append(now)

def validate_video_id(video_id: str):
    if not re.match(r'^[a-zA-Z0-9_-]{10,12}$', video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID")

def get_cookie_rotation():
    global cookie_cache
    
    if time.time() - cookie_cache["last_refresh"] > 300:
        cookie_files = list(COOKIES_DIR.glob("*.txt"))
        cookie_cache["cookies"] = cookie_files
        cookie_cache["last_refresh"] = time.time()
        cookie_cache["index"] = 0
        logger.info(f"Refreshed cookie cache: {len(cookie_files)} files")
    
    if not cookie_cache["cookies"]:
        logger.warning("No cookies available")
        return None
    
    cookie = cookie_cache["cookies"][cookie_cache["index"]]
    cookie_cache["index"] = (cookie_cache["index"] + 1) % len(cookie_cache["cookies"])
    
    return str(cookie)

def get_ydl_opts(video_id: str, quality: str, media_type: str):
    format_map = {
        "audio_high": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
        "audio_medium": "bestaudio[abr<=128]/bestaudio/best",
        "audio_low": "worstaudio/bestaudio",
        "video_1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
        "video_720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
        "video_480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
        "video_best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
    }
    
    format_str = format_map.get(quality, format_map["video_best"])
    
    cookie_file = get_cookie_rotation()
    
    opts = {
        "format": format_str,
        "outtmpl": str(DOWNLOAD_DIR / f"{video_id}.%(ext)s"),
        "merge_output_format": "mp4" if "video" in media_type else None,
        "quiet": True,
        "no_warnings": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 5,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "extractor_retries": 5,
        "socket_timeout": 45,
        "http_chunk_size": 10485760,
        "throttledratelimit": None,
        "noprogress": True,
        "prefer_ffmpeg": True,
        "keepvideo": False,
        "overwrites": True,
        "continuedl": True,
        "external_downloader_args": ["-x", "16", "-s", "16", "-k", "5M"],
    }
    
    if cookie_file:
        opts["cookiefile"] = cookie_file
    
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    
    opts["http_headers"] = {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-us,en;q=0.5",
        "Sec-Fetch-Mode": "navigate",
    }
    
    return opts

async def download_media(video_id: str, url: str, quality: str, media_type: str):
    async with download_semaphore:
        try:
            download_status[video_id] = {"status": "downloading", "type": media_type}
            logger.info(f"Starting download: {video_id} ({media_type} - {quality})")
            
            await asyncio.sleep(random.uniform(0.5, 2))
            
            ydl_opts = get_ydl_opts(video_id, quality, media_type)
            
            await asyncio.to_thread(
                yt_dlp.YoutubeDL(ydl_opts).download, 
                [url]
            )
            
            files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
            if not files:
                raise Exception("Download completed but file not found")
            
            file = files[0]
            file_size = round(file.stat().st_size / 1024 / 1024, 2)
            
            logger.info(f"Download complete: {file.name} ({file_size}MB)")
            
            download_status[video_id] = {
                "status": "completed",
                "filename": file.name,
                "format": file.suffix[1:],
                "type": media_type,
                "size_mb": file_size,
                "download_url": f"{BASE_URL}/download/{file.name}"
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Download failed for {video_id}: {error_msg}")
            
            if any(x in error_msg.lower() for x in ["sign in", "unavailable", "private", "deleted"]):
                error_msg = "Video unavailable or restricted"
            elif any(x in error_msg.lower() for x in ["copyright", "blocked"]):
                error_msg = "Video blocked due to copyright"
            else:
                error_msg = "Download failed, please try again"
            
            download_status[video_id] = {
                "status": "failed",
                "error": error_msg
            }

async def cleanup_old_files():
    while True:
        try:
            cutoff = time.time() - MAX_FILE_AGE
            cleaned = 0
            
            for file in DOWNLOAD_DIR.glob("*"):
                if file.stat().st_mtime < cutoff:
                    file.unlink()
                    video_id = file.stem
                    if video_id in download_status:
                        del download_status[video_id]
                    cleaned += 1
            
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} old files")
                
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")
        
        await asyncio.sleep(1800)

@app.on_event("startup")
async def startup():
    cookies = list(COOKIES_DIR.glob("*.txt"))
    logger.info(f"API started with {len(cookies)} cookie files")
    logger.info(f"Max concurrent downloads: {MAX_CONCURRENT}")
    logger.info(f"File retention: {MAX_FILE_AGE}s")
    asyncio.create_task(cleanup_old_files())

@app.get("/")
async def root():
    return {
        "service": "Media Download API",
        "version": "4.0",
        "status": "operational",
        "endpoints": {
            "download": "/download/{video_id}",
            "status": "/status/{video_id}",
            "file": "/download/{filename}",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    active_downloads = sum(
        1 for s in download_status.values() 
        if s.get("status") == "downloading"
    )
    
    cached_files = len(list(DOWNLOAD_DIR.glob("*")))
    
    return {
        "status": "healthy",
        "timestamp": int(time.time()),
        "active_downloads": active_downloads,
        "cached_files": cached_files,
        "cookies_available": len(cookie_cache.get("cookies", []))
    }

@app.post("/download/{video_id}")
async def create_download(
    video_id: str,
    background_tasks: BackgroundTasks,
    authorization: str = Header(...),
    quality: str = "video_best",
    media_type: str = "video"
):
    api_key = authorization.replace("Bearer ", "").strip()
    validate_api_key(api_key)
    check_rate_limit(api_key)
    validate_video_id(video_id)
    
    valid_qualities = [
        "audio_high", "audio_medium", "audio_low",
        "video_1080p", "video_720p", "video_480p", "video_best"
    ]
    
    if quality not in valid_qualities:
        quality = "video_best"
    
    if media_type not in ["audio", "video"]:
        media_type = "video"
    
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        file = files[0]
        return {
            "status": "completed",
            "video_id": video_id,
            "format": file.suffix[1:],
            "size_mb": round(file.stat().st_size / 1024 / 1024, 2),
            "download_url": f"{BASE_URL}/download/{file.name}"
        }
    
    if video_id in download_status:
        return {
            "status": download_status[video_id]["status"],
            "video_id": video_id,
            **download_status[video_id]
        }
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    background_tasks.add_task(
        download_media,
        video_id,
        url,
        quality,
        media_type
    )
    
    return {
        "status": "downloading",
        "video_id": video_id,
        "quality": quality,
        "type": media_type
    }

@app.get("/status/{video_id}")
async def check_status(video_id: str):
    validate_video_id(video_id)
    
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        file = files[0]
        return {
            "status": "completed",
            "video_id": video_id,
            "format": file.suffix[1:],
            "size_mb": round(file.stat().st_size / 1024 / 1024, 2),
            "download_url": f"{BASE_URL}/download/{file.name}"
        }
    
    if video_id in download_status:
        return {
            "status": download_status[video_id]["status"],
            "video_id": video_id,
            **download_status[video_id]
        }
    
    return {
        "status": "not_found",
        "video_id": video_id
    }

@app.get("/download/{filename}")
async def serve_file(filename: str):
    file_path = DOWNLOAD_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )

@app.delete("/clear/{video_id}")
async def clear_cache(
    video_id: str,
    authorization: str = Header(...)
):
    api_key = authorization.replace("Bearer ", "").strip()
    validate_api_key(api_key)
    validate_video_id(video_id)
    
    if video_id in download_status:
        del download_status[video_id]
    
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    for file in files:
        file.unlink()
    
    return {
        "status": "cleared",
        "video_id": video_id
    }

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        workers=1,
        log_level="info"
    )
