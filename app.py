from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pathlib import Path
import yt_dlp
import os
import asyncio
import uvicorn
from typing import Dict
import random
import time

app = FastAPI(title="YouTube Download API")

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
COOKIES_DIR = Path("cookies")
COOKIES_DIR.mkdir(exist_ok=True)

VALID_API_KEY = os.getenv("API_KEY", "shadwo")
BASE_URL = os.getenv("BASE_URL", "https://youtube-api-0qwc.onrender.com")

download_status: Dict[str, dict] = {}
cookie_test_cache = {"last_test": 0, "working_cookies": []}

def validate_api_key(api_key: str):
    if api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

def get_cookie_file():
    """Get a working cookie file with caching"""
    global cookie_test_cache
    
    # Refresh cache every 5 minutes
    if time.time() - cookie_test_cache["last_test"] > 300:
        cookie_test_cache["working_cookies"] = []
        cookie_test_cache["last_test"] = time.time()
    
    # If we have working cookies cached, use them
    if cookie_test_cache["working_cookies"]:
        cookie = random.choice(cookie_test_cache["working_cookies"])
        print(f"🍪 Using cached working cookie: {cookie.name}")
        return str(cookie)
    
    # Otherwise test all cookies
    cookie_files = list(COOKIES_DIR.glob("*.txt"))
    if not cookie_files:
        print("⚠️ No cookies found!")
        return None
    
    # Try to find a working cookie
    for cookie_file in cookie_files:
        try:
            # Quick test with yt-dlp using actual format we'll use for downloads
            test_opts = {
                "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "cookiefile": str(cookie_file),
                "skip_download": True,
                "ignoreerrors": True,
            }
            with yt_dlp.YoutubeDL(test_opts) as ydl:
                # Test with a simple video
                info = ydl.extract_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ", download=False)
                # Check if we got valid formats
                if info and info.get("formats"):
                    cookie_test_cache["working_cookies"].append(cookie_file)
                    print(f"✅ Working cookie: {cookie_file.name}")
        except Exception as e:
            error_msg = str(e)
            # If it's just a format issue, the cookie might still work
            if "format" in error_msg.lower() and "not available" in error_msg.lower():
                print(f"⚠️ Cookie may work: {cookie_file.name} (format restrictions)")
                # Still add it as it might work for some videos
                cookie_test_cache["working_cookies"].append(cookie_file)
            else:
                print(f"❌ Cookie failed: {cookie_file.name} - {str(e)[:50]}")
            continue
    
    if cookie_test_cache["working_cookies"]:
        cookie = cookie_test_cache["working_cookies"][0]
        print(f"🍪 Using: {cookie.name}")
        return str(cookie)
    
    # If no fully working cookies, just use any cookie file as fallback
    print("⚠️ No fully tested working cookies, trying any available cookie...")
    if cookie_files:
        return str(cookie_files[0])
    
    print("⚠️ No cookies found at all!")
    return None

def get_ydl_opts(video_id: str, format_str: str, cookie_file: str = None):
    opts = {
        "format": format_str,
        "outtmpl": str(DOWNLOAD_DIR / f"{video_id}.%(ext)s"),
        "merge_output_format": "mp4",
        "prefer_ffmpeg": True,
        "quiet": False,
        "no_warnings": False,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 3,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "extractor_retries": 3,
        "socket_timeout": 30,
    }
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts


async def download_media(video_id: str, url: str, format_str: str, media_type: str):
    cookie_file = get_cookie_file()

    if not cookie_file:
        download_status[video_id] = {
            "status": "error",
            "error": "No working cookies available. Please refresh your YouTube cookies.",
            "message": "No working cookies available. Please refresh your YouTube cookies."
        }
        return

    ydl_opts = get_ydl_opts(video_id, format_str, cookie_file)

    try:
        download_status[video_id] = {"status": "downloading", "type": media_type}
        print(f"📥 Downloading {video_id} ({media_type})")

        # Try download
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
        
        # Check if it's a cookie/signature issue
        if any(x in error_msg.lower() for x in ["signature", "invalid argument", "400", "only images"]):
            error_msg = "Cookie expired or invalid. Please refresh your YouTube cookies. Visit: chrome://settings/cookies or use cookie extension."
            # Clear cookie cache to force retest
            global cookie_test_cache
            cookie_test_cache["working_cookies"] = []
        
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
    working = len(cookie_test_cache.get("working_cookies", []))
    return {
        "name": "YouTube API",
        "version": "3.3",
        "status": "online",
        "cookies": {
            "total": len(cookies),
            "working": working if working > 0 else "untested",
            "files": [c.name for c in cookies]
        },
        "endpoints": {
            "test": "/test-cookies",
            "song": "/song/{id}?api=KEY",
            "video": "/video/{id}?api=KEY",
            "status": "/status/{id}",
            "clear": "DELETE /clear/{id}?api=KEY"
        },
        "note": "If downloads fail with 'signature' or '400' errors, refresh your cookies!"
    }

@app.get("/test-cookies")
async def test_cookies():
    """Test all cookies and return results"""
    cookies = list(COOKIES_DIR.glob("*.txt"))

    if not cookies:
        return {"error": "No cookies", "dir": str(COOKIES_DIR.absolute())}

    results = {}
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    for cookie in cookies:
        try:
            opts = {
                "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "cookiefile": str(cookie),
                "skip_download": True,
                "ignoreerrors": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            
            # Check if we got valid formats
            if info and info.get("formats"):
                results[cookie.name] = {
                    "status": "✅ Working",
                    "title": info.get("title", "Unknown")[:50]
                }
            else:
                results[cookie.name] = {
                    "status": "⚠️ Limited",
                    "error": "Cookie works but may have format restrictions"
                }
        except Exception as e:
            error = str(e)
            if "signature" in error.lower() or "400" in error:
                status = "❌ Expired/Invalid"
            elif "format" in error.lower() or "not available" in error.lower():
                status = "⚠️ Limited"
                error = "Cookie works but has format restrictions - may still work for downloads"
            else:
                status = "❌ Failed"
            results[cookie.name] = {
                "status": status,
                "error": error[:80]
            }

    working = sum(1 for r in results.values() if "✅" in r["status"])
    limited = sum(1 for r in results.values() if "⚠️" in r["status"])
    
    # Clear cache to force retest next time
    global cookie_test_cache
    cookie_test_cache["working_cookies"] = []
    
    return {
        "total": len(cookies),
        "working": working,
        "limited": limited,
        "results": results,
        "note": "✅ = Fully working, ⚠️ = May have restrictions, ❌ = Not working"
    }

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

        url = f"https://www.youtube.com/watch?v={video_id}"

    background_tasks.add_task(
        download_media,
        video_id,
        url,
        "bv*+ba/best",
        "video"
    )

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
   background_tasks.add_task(
    download_media,
    video_id,
    url,
    "bv*+ba/best",
    "video"
)
    print(f"🔄 Started background download for: {video_id}")
    return {"status": "downloading", "video_id": video_id, "message": "Download started"}

@app.get("/status/{video_id}")
async def check_status(video_id: str):
    """Check download status"""
    print(f"📊 Status check for: {video_id}")
    
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    if files:
        print(f"✅ File found: {files[0].name}")
        return {
            "status": "done",
            "video_id": video_id,
            "format": files[0].suffix[1:],
            "link": f"{BASE_URL}/download/{files[0].name}"
        }
    
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
    
    if video_id in download_status:
        del download_status[video_id]
    
    files = list(DOWNLOAD_DIR.glob(f"{video_id}.*"))
    for file in files:
        file.unlink()
    
    return {"status": "cleared", "video_id": video_id}

@app.get("/refresh-cookies")
async def refresh_cookies(api: str):
    """Force refresh cookie cache"""
    validate_api_key(api)
    
    global cookie_test_cache
    cookie_test_cache["working_cookies"] = []
    cookie_test_cache["last_test"] = 0
    
    # Test cookies immediately
    get_cookie_file()
    
    return {
        "status": "refreshed",
        "working_cookies": len(cookie_test_cache["working_cookies"]),
        "message": "Cookie cache refreshed"
    }

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
    print("⚠️ If downloads fail, check /test-cookies endpoint")
    print("="*50)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
