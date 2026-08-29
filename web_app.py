import os
import sys
import uuid
import json
import time
import logging
import asyncio
from typing import Optional
import httpx
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
    extract_direct_url,
    download_media,
    download_images,
    cleanup_file,
    cleanup_files,
    PROGRESS_STORE,
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

# In-memory storage for proxy stream tokens
# token -> { "direct_url": str, "headers": dict, "filename": str, "expires": float }
STREAM_TOKENS: dict = {}

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

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    """Ensure browser never caches outdated static assets during updates."""
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

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
    task_id: Optional[str] = None

class DirectRequest(BaseModel):
    url: str
    quality: str = "720"
    is_audio: bool = False
    task_id: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Serve the sleek Web Downloader UI."""
    debugPrint(f"GET / from {request.client.host if request.client else 'unknown'}")
    return templates.TemplateResponse(request=request, name="index.html", context={"v": int(time.time())})

@app.get("/health")
async def health_check():
    """Health check for uptime monitoring."""
    return {"status": "ok", "app": "Universal Media Downloader"}

@app.get("/api/progress/{task_id}")
async def get_progress(task_id: str):
    """Real-time progress reporting for downloading and processing media."""
    prog = PROGRESS_STORE.get(task_id, {
        'status': 'starting',
        'percent': 0,
        'downloaded_mb': 0,
        'total_mb': 0,
        'speed': '',
        'eta': '',
        'msg': 'Connecting to server...'
    })
    return JSONResponse(content=prog)

@app.post("/api/info")
async def get_media_info(req: InfoRequest):
    """Extract metadata (title, thumbnail, formats, platform) for instant preview."""
    debugPrint(f"API HIT: /api/info | URL: {req.url}")
    
    extracted_url = extract_url(req.url)
    if not extracted_url:
        debugPrint(f"API ERROR: Invalid URL '{req.url}'")
        raise HTTPException(status_code=400, detail="Please provide a valid media URL.")

    try:
        data = await extract_media_info(extracted_url)
        debugPrint(f"API RESPONSE: /api/info | Platform: {data.get('platform')} | Title: {str(data.get('title'))[:50]}")
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Error in /api/info: {e}", exc_info=True)
        debugPrint(f"API ERROR: /api/info exception: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch media metadata: {str(e)[:100]}")

@app.post("/api/download")
async def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    """Download the media onto VPS storage and prepare a direct download token."""
    debugPrint(f"API HIT: /api/download | URL: {req.url} | Quality: {req.quality} | is_audio: {req.is_audio}")
    
    extracted_url = extract_url(req.url)
    if not extracted_url:
        raise HTTPException(status_code=400, detail="Invalid media URL provided.")

    try:
        # Check if requested format is album or image
        if req.quality in ["album", "img_zip", "album_zip", "img"]:
            img_result = await download_images(extracted_url)
            paths = img_result.get('image_paths', [])
            if not paths:
                raise HTTPException(status_code=404, detail="No photos found in this post.")
            
            title = img_result.get('title', 'photos')
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).strip()[:80] or "photos"

            if req.quality in ["img_zip", "album_zip"] and len(paths) > 1:
                import zipfile
                zip_filename = f"{safe_title}_album_{uuid.uuid4().hex[:6]}.zip"
                zip_path = os.path.join(DOWNLOAD_DIR, zip_filename)
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for idx, ip in enumerate(paths):
                        if os.path.exists(ip):
                            ext_part = os.path.splitext(ip)[1] or '.jpg'
                            zf.write(ip, f"{safe_title}_{idx+1}{ext_part}")
                
                cleanup_files(paths)
                file_id = uuid.uuid4().hex[:12]
                zip_size = os.path.getsize(zip_path)
                ACTIVE_DOWNLOADS[file_id] = {
                    "file_path": zip_path,
                    "filename": f"{safe_title}.zip",
                    "filesize": zip_size
                }
                return {
                    "status": "ready",
                    "file_id": file_id,
                    "download_url": f"/api/file/{file_id}",
                    "filename": f"{safe_title}.zip",
                    "filesize": zip_size,
                    "filesize_mb": round(zip_size / (1024 * 1024), 2)
                }

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
                "filesize": os.path.getsize(file_path),
                "filesize_mb": round(os.path.getsize(file_path) / (1024 * 1024), 2)
            }

        # Download Video or Audio
        result = await download_media(extracted_url, is_audio=req.is_audio, quality=req.quality)
        file_path = result.get('file_path')
        title = result.get('title', 'Media')
        ext = result.get('ext', 'mp4')
        
        if not file_path or not os.path.exists(file_path):
            debugPrint(f"API ERROR: File not generated for {extracted_url}")
            raise HTTPException(status_code=500, detail="Media download failed. Please try again.")

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
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)[:150]}")

async def cleanup_after_download(file_path: str, file_id: str, delay_seconds: int = 180):
    """Wait for browser download to finish, then safely delete temporary file."""
    try:
        await asyncio.sleep(delay_seconds)
        cleanup_file(file_path)
        ACTIVE_DOWNLOADS.pop(file_id, None)
        debugPrint(f"CLEANUP: Deleted temporary file {file_path}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

@app.api_route("/api/file/{file_id}", methods=["GET", "HEAD"])
async def serve_file(file_id: str):
    """Direct stream/download endpoint with full support for browser download managers."""
    debugPrint(f"API HIT: /api/file/{file_id}")
    
    entry = ACTIVE_DOWNLOADS.get(file_id)
    if not entry or not os.path.exists(entry["file_path"]):
        debugPrint(f"API ERROR: file_id {file_id} not found or expired")
        raise HTTPException(status_code=404, detail="File has expired or was not found.")

    file_path = entry["file_path"]
    filename = entry["filename"]

    # Schedule background cleanup decoupled from FastAPI shutdown
    asyncio.create_task(cleanup_after_download(file_path, file_id, 180))

    debugPrint(f"STREAMING: Serving {filename} to client")
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )


# ===========================================================================
# NEW: Direct / Proxy-Stream endpoints (no VPS disk storage)
# ===========================================================================

@app.post("/api/direct")
async def get_direct_url(req: DirectRequest):
    """
    Extract the direct CDN URL for the requested media.

    Response modes:
      - redirect: { mode, direct_url, title, ext, filename }  — browser opens URL directly (IG, FB, TikTok, Twitter, Pinterest)
      - images:   { mode, image_urls, title, filename }        — direct image CDN URLs
      - download: { mode, download_url, title, ext, filename, filesize_mb } — reliable yt-dlp fetch with instant auto-cleanup (YouTube/Audio)
    """
    debugPrint(f"API HIT: /api/direct | URL: {req.url} | quality: {req.quality} | audio: {req.is_audio}")

    extracted_url = extract_url(req.url)
    if not extracted_url:
        raise HTTPException(status_code=400, detail="Invalid media URL provided.")

    try:
        result = await extract_direct_url(extracted_url, quality=req.quality, is_audio=req.is_audio)
    except Exception as e:
        logger.error(f"/api/direct error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to extract media URL: {str(e)[:150]}")

    mode = result.get('mode', 'stream')
    title = result.get('title', 'Media')
    ext   = result.get('ext', 'mp4')

    # Build a safe filename
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).strip()[:80] or "media"
    filename = f"{safe_title}.{ext}"

    # 1. Check for ZIP Album download
    if req.quality in ['img_zip', 'album_zip']:
        debugPrint(f"/api/direct → Creating ZIP archive of post images...")
        img_res = await download_images(extracted_url)
        img_paths = img_res.get('image_paths', [])
        if img_paths:
            import zipfile
            zip_filename = f"{safe_title}_album_{uuid.uuid4().hex[:6]}.zip"
            zip_path = os.path.join(DOWNLOAD_DIR, zip_filename)
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for idx, ip in enumerate(img_paths):
                    if os.path.exists(ip):
                        ext_part = os.path.splitext(ip)[1] or '.jpg'
                        zf.write(ip, f"{safe_title}_{idx+1}{ext_part}")
            
            # Clean individual images
            cleanup_files(img_paths)
            
            zip_size = os.path.getsize(zip_path)
            file_id = uuid.uuid4().hex[:12]
            ACTIVE_DOWNLOADS[file_id] = {
                "file_path": zip_path,
                "filename": f"{safe_title}.zip",
                "filesize": zip_size
            }
            asyncio.create_task(cleanup_after_download(zip_path, file_id, 180))
            return JSONResponse({
                'mode': 'download',
                'download_url': f"/api/file/{file_id}",
                'title': title,
                'ext': 'zip',
                'filename': f"{safe_title}.zip",
                'filesize': zip_size,
                'filesize_mb': round(zip_size / (1024 * 1024), 2)
            })

    # 2. Images mode
    if mode == 'images' or req.quality in ['album', 'img', 'images']:
        image_urls = result.get('image_urls') or []
        if not image_urls and result.get('direct_url') and result.get('ext') in ['jpg', 'jpeg', 'png', 'webp']:
            image_urls = [result.get('direct_url')]
        debugPrint(f"/api/direct → images ({len(image_urls)} URLs)")
        return JSONResponse({
            'mode': 'images',
            'image_urls': image_urls,
            'title': title,
            'filename': filename,
        })

    # 3. Redirect mode (Direct CDN for Instagram, Facebook, TikTok, Twitter, Pinterest)
    if mode == 'redirect' and result.get('direct_url'):
        debugPrint(f"/api/direct → redirect | URL: {str(result.get('direct_url'))[:80]}")
        return JSONResponse({
            'mode': 'redirect',
            'direct_url': result.get('direct_url'),
            'title': title,
            'ext': ext,
            'filename': filename,
        })

    # 3. For YouTube / Streams that require merging or token signing (Prevent 403 Forbidden 0-byte downloads)
    debugPrint(f"/api/direct → YouTube/Stream mode. Downloading via yt-dlp with auto-cleanup (task_id={req.task_id})...")
    try:
        dl_result = await download_media(extracted_url, is_audio=req.is_audio, quality=req.quality, task_id=req.task_id)
        file_path = dl_result.get('file_path')
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=500, detail="Failed to prepare video file.")

        file_size = os.path.getsize(file_path)
        file_id = uuid.uuid4().hex[:12]
        dl_ext = dl_result.get('ext', ext)
        download_filename = f"{safe_title}.{dl_ext}"

        ACTIVE_DOWNLOADS[file_id] = {
            "file_path": file_path,
            "filename": download_filename,
            "filesize": file_size
        }

        # Schedule auto-cleanup in 120s
        asyncio.create_task(cleanup_after_download(file_path, file_id, 120))

        debugPrint(f"/api/direct → download ready | file_id={file_id} | size={round(file_size/(1024*1024), 2)}MB")
        return JSONResponse({
            'mode': 'download',
            'download_url': f"/api/file/{file_id}",
            'title': title,
            'ext': dl_ext,
            'filename': download_filename,
            'filesize': file_size,
            'filesize_mb': round(file_size / (1024 * 1024), 2)
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download stream error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)[:150]}")


@app.get("/api/download_image")
async def download_image_proxy(url: str, filename: str = "photo.jpg"):
    """
    Stream image directly from CDN with Content-Disposition: attachment header.
    Forces browser to download the file into user's downloads folder instead of opening in a tab.
    Zero disk storage on VPS (pure memory streaming).
    """
    if not url or not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid image URL")
    
    # Clean filename
    safe_name = "".join(c for c in filename if c.isalnum() or c in (' ', '_', '-', '.')).strip() or "photo.jpg"
    if not any(safe_name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
        safe_name += ".jpg"
    
    img_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    }

    async def _image_stream_generator():
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=img_headers) as resp:
                if resp.status_code != 200:
                    yield b""
                    return
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk

    media_type = "image/jpeg"
    if safe_name.lower().endswith(".png"):
        media_type = "image/png"
    elif safe_name.lower().endswith(".webp"):
        media_type = "image/webp"

    return StreamingResponse(
        _image_stream_generator(),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Cache-Control": "no-cache",
        }
    )


@app.get("/api/stream/{token}")
async def proxy_stream(token: str, request: Request):
    """
    Proxy-stream endpoint for YouTube and other platforms that need special
    headers or signed URLs.  Pipes bytes from the CDN to the browser in
    real-time — nothing is written to disk on the VPS.
    """
    debugPrint(f"API HIT: /api/stream/{token}")

    entry = STREAM_TOKENS.get(token)
    if not entry:
        raise HTTPException(status_code=404, detail="Stream token not found or expired.")
    if time.time() > entry['expires']:
        STREAM_TOKENS.pop(token, None)
        raise HTTPException(status_code=410, detail="Stream token has expired.")

    direct_url = entry['direct_url']
    if not direct_url:
        raise HTTPException(status_code=500, detail="No direct URL available for streaming.")

    # Remove token after first use to avoid repeated requests
    STREAM_TOKENS.pop(token, None)

    filename = entry.get('filename', 'media.mp4')
    src_headers = {k: v for k, v in (entry.get('headers') or {}).items()
                   if k.lower() not in ('host', 'content-length')}

    # Forward Range header if client sent one (supports seek / resume)
    range_header = request.headers.get('range')
    if range_header:
        src_headers['Range'] = range_header

    debugPrint(f"PROXY STREAM: Piping {direct_url[:80]} → client")

    async def _stream_generator():
        async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
            async with client.stream("GET", direct_url, headers=src_headers) as resp:
                async for chunk in resp.aiter_bytes(chunk_size=65536):  # 64 KB chunks
                    yield chunk

    # Determine content type
    ext_lower = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'mp4'
    content_type_map = {
        'mp4': 'video/mp4', 'webm': 'video/webm', 'mkv': 'video/x-matroska',
        'mp3': 'audio/mpeg', 'm4a': 'audio/mp4', 'ogg': 'audio/ogg',
        'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp',
    }
    media_type = content_type_map.get(ext_lower, 'application/octet-stream')

    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Accept-Ranges': 'bytes',
    }

    return StreamingResponse(
        _stream_generator(),
        media_type=media_type,
        headers=headers,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=False)
