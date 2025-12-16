from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pathlib import Path
import yt_dlp
import os
import asyncio
import uvicorn
from typing import Dict

app = FastAPI(title="YouTube Download API")

# ---------------- CONFIG ---------------- #

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

VALID_API_KEY = os.getenv("API_KEY", "shadwo")

# Track download status
download_status: Dict[str, dict] = {}

def validate_api_key(api_key: str):
    if api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ---------------- HELPERS ---------------- #

async def download_youtube_audio(video_id: str, url: str):
    """Background task to download audio"""
    output = DOWNLOAD_DIR / f"{video_id}.%(ext)s"
    
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output),
        "quiet": True,
        "no_warnings": True,
    }
    
    try:
        download_status[video_id] = {"status": "downloading", "type": "audio"}
        
        await asyncio.to_thread(
            yt_dlp.YoutubeDL(ydl_opts).download, [url]
        )
        
        files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
        if not files:
            download_status[video_id] = {"status": "error", "error": "Download failed"}
            return
        
        file = files[0]
        download_status[video_id] = {
            "status": "done",
            "filename": file.name,
            "format": file.suffix[1:],
            "type": "audio"
        }
        
    except Exception as e:
        download_status[video_id] = {"status": "error", "error": str(e)}

async def download_youtube_video(video_id: str, url: str):
    """Background task to download video"""
    output = DOWNLOAD_DIR / f"{video_id}.%(ext)s"
    
    ydl_opts = {
        "format": "best[height<=720][width<=1280]/best",
        "outtmpl": str(output),
        "quiet": True,
        "no_warnings": True,
    }
    
    try:
        download_status[video_id] = {"status": "downloading", "type": "video"}
        
        await asyncio.to_thread(
            yt_dlp.YoutubeDL(ydl_opts).download, [url]
        )
        
        files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
        if not files:
            download_status[video_id] = {"status": "error", "error": "Download failed"}
            return
        
        file = files[0]
        download_status[video_id] = {
            "status": "done",
            "filename": file.name,
            "format": file.suffix[1:],
            "type": "video"
        }
        
    except Exception as e:
        download_status[video_id] = {"status": "error", "error": str(e)}

# ---------------- ROOT ---------------- #

@app.get("/")
async def root():
    return {
        "name": "My YouTube Download API",
        "status": "running",
        "version": "2.0",
        "endpoints": {
            "song": "/song/{video_id}?api=YOUR_KEY",
            "video": "/video/{video_id}?api=YOUR_KEY",
            "status": "/status/{video_id}",
            "download": "/download/{filename}"
        },
        "info": "API now uses async downloads. Check /status/{video_id} or poll the same endpoint until status=done"
    }

# ---------------- SONG ---------------- #

@app.get("/song/{video_id}")
async def download_song(video_id: str, api: str, background_tasks: BackgroundTasks):
    validate_api_key(api)
    
    # Check if file already exists
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        file = files[0]
        # Get the full URL (use request.base_url in production)
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
            return {
                "status": "error",
                "video_id": video_id,
                "error": status_info.get("error", "Unknown error")
            }
    
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
            return {
                "status": "error",
                "video_id": video_id,
                "error": status_info.get("error", "Unknown error")
            }
    
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
    print(f"✅ API Started - Download directory: {DOWNLOAD_DIR.absolute()}")
    print(f"✅ API Key: {VALID_API_KEY}")

# ---------------- START ---------------- #

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
