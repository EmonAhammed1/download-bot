import os
import sys
import uuid
import json
import logging
import asyncio
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure UTF-8 console output
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from downloader import (
    extract_url,
    clean_url,
    get_platform_name,
    extract_media_info,
    download_media,
    download_images,
    cleanup_file,
    cleanup_files,
    DOWNLOAD_DIR
)

# Logging
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("WebDownloader")

def debugPrint(msg: str):
    """User rule #11: Debug print in terminal for every API hit and response."""
    print(f"\n[DEBUG 🚀] {msg}", flush=True)

# In-memory storage for active download files
# file_id -> { "file_path": str, "filename": str, "filesize": int }
ACTIVE_DOWNLOADS = {}

app = FastAPI(
    title="Universal Media Downloader Web",
    description="Download videos, photos & music from YouTube, Facebook, Instagram, TikTok, Twitter, Pinterest in Full HD without limits.",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Request Models
class InfoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    quality: str = "720"
    is_audio: bool = False

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Serve the sleek Web Downloader UI."""
    debugPrint(f"GET / from {request.client.host if request.client else 'unknown'}")
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/health")
async def health_check():
    """Health check for uptime monitoring."""
    return {"status": "ok", "app": "Universal Media Downloader"}

@app.post("/api/info")
async def get_media_info(req: InfoRequest):
    """Extract metadata (title, thumbnail, formats, platform) for instant preview."""
    debugPrint(f"API HIT: /api/info | URL: {req.url}")
    
    extracted_url = extract_url(req.url)
    if not extracted_url:
        debugPrint(f"API ERROR: Invalid URL '{req.url}'")
        raise HTTPException(status_code=400, detail="দয়া করে একটি সঠিক মিডিয়া লিঙ্ক প্রদান করুন।")

    try:
        data = await extract_media_info(extracted_url)
        debugPrint(f"API RESPONSE: /api/info | Platform: {data.get('platform')} | Title: {str(data.get('title'))[:50]}")
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Error in /api/info: {e}", exc_info=True)
        debugPrint(f"API ERROR: /api/info exception: {str(e)}")
        raise HTTPException(status_code=500, detail=f"মেটাডেটা লোড করতে ব্যর্থ হয়েছে: {str(e)[:100]}")

@app.post("/api/download")
async def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    """Download the media onto VPS storage and prepare a direct download token."""
    debugPrint(f"API HIT: /api/download | URL: {req.url} | Quality: {req.quality} | is_audio: {req.is_audio}")
    
    extracted_url = extract_url(req.url)
    if not extracted_url:
        raise HTTPException(status_code=400, detail="সঠিক লিঙ্ক পাওয়া যায়নি।")

    try:
        # Check if requested format is album
        if req.quality == "album":
            img_result = await download_images(extracted_url)
            paths = img_result.get('image_paths', [])
            if not paths:
                raise HTTPException(status_code=404, detail="ছবি পাওয়া যায়নি।")
            
            # Return image URLs
            # For multiple images, we can package or return first
            file_path = paths[0]
            file_id = uuid.uuid4().hex[:12]
            ACTIVE_DOWNLOADS[file_id] = {
                "file_path": file_path,
                "filename": os.path.basename(file_path),
                "filesize": os.path.getsize(file_path),
                "extra_files": paths[1:]
            }
            return {
                "status": "ready",
                "file_id": file_id,
                "download_url": f"/api/file/{file_id}",
                "filename": os.path.basename(file_path),
                "filesize": os.path.getsize(file_path)
            }

        # Download Video or Audio
        result = await download_media(extracted_url, is_audio=req.is_audio, quality=req.quality)
        file_path = result.get('file_path')
        title = result.get('title', 'Media')
        ext = result.get('ext', 'mp4')
        
        if not file_path or not os.path.exists(file_path):
            debugPrint(f"API ERROR: File not generated for {extracted_url}")
            raise HTTPException(status_code=500, detail="মিডিয়া ডাউনলোড ব্যর্থ হয়েছে।")

        file_size = os.path.getsize(file_path)
        file_id = uuid.uuid4().hex[:12]
        
        # Clean filename for browser download
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).strip()
        safe_title = safe_title[:80] if safe_title else "video"
        download_filename = f"{safe_title}.{ext}"

        ACTIVE_DOWNLOADS[file_id] = {
            "file_path": file_path,
            "filename": download_filename,
            "filesize": file_size
        }

        debugPrint(f"API SUCCESS: /api/download | file_id={file_id} | size={round(file_size/(1024*1024), 2)}MB")

        return {
            "status": "ready",
            "file_id": file_id,
            "download_url": f"/api/file/{file_id}",
            "filename": download_filename,
            "filesize": file_size,
            "filesize_mb": round(file_size / (1024 * 1024), 2)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        debugPrint(f"API ERROR: /api/download failed: {e}")
        raise HTTPException(status_code=500, detail=f"ডাউনলোডে সমস্যা হয়েছে: {str(e)[:150]}")

async def cleanup_after_download(file_path: str, file_id: str, delay_seconds: int = 180):
    """Wait for browser download to finish, then safely delete temporary file."""
    await asyncio.sleep(delay_seconds)
    cleanup_file(file_path)
    ACTIVE_DOWNLOADS.pop(file_id, None)
    debugPrint(f"CLEANUP: Deleted temporary file {file_path}")

@app.api_route("/api/file/{file_id}", methods=["GET", "HEAD"])
async def serve_file(file_id: str, background_tasks: BackgroundTasks):
    """Direct stream/download endpoint with full support for browser download managers."""
    debugPrint(f"API HIT: /api/file/{file_id}")
    
    entry = ACTIVE_DOWNLOADS.get(file_id)
    if not entry or not os.path.exists(entry["file_path"]):
        debugPrint(f"API ERROR: file_id {file_id} not found or expired")
        raise HTTPException(status_code=404, detail="ফাইলটির মেয়াদ শেষ হয়ে গেছে বা পাওয়া যায়নি।")

    file_path = entry["file_path"]
    filename = entry["filename"]

    # Schedule background cleanup after 3 minutes so multiple browser threads / IDM can complete
    background_tasks.add_task(cleanup_after_download, file_path, file_id, 180)

    debugPrint(f"STREAMING: Serving {filename} to client")
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=False)
