import os
import re
import uuid
import time
import shutil
import asyncio
import logging
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List, Tuple
import yt_dlp

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# URL matching regex
URL_REGEX = re.compile(
    r'(https?://(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|'
    r'www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|'
    r'https?://[^\s]+)'
)

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,bn;q=0.8',
}

IG_GRAPHQL_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    'Accept': '*/*',
    'X-IG-App-ID': '936619743392459',
    'X-ASBD-ID': '129477',
    'X-Requested-With': 'XMLHttpRequest',
}

def extract_url(text: str) -> Optional[str]:
    match = URL_REGEX.search(text)
    return match.group(0) if match else None

def clean_url(url: str) -> str:
    """Strip unnecessary tracking parameters while keeping essential video ids."""
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    # Remove tracking query parameters (igsh, igsi, utm_*, mibextid, fbclid, sfnsn, etc.)
    url = re.sub(r'([?&])(igsh|igsi|utm_[a-zA-Z0-9_]+|mibextid|fbclid|sfnsn|feature)=[^&#]*', '', url)
    # Clean up dangling ? or &
    url = re.sub(r'[?&]+$', '', url)
    url = re.sub(r'\?&', '?', url)
    return url

def check_profile_link(url: str) -> Optional[Tuple[str, str]]:
    """Check if the URL is a user profile link rather than a post/video link.
    Returns (platform_name, username) if it is a profile link, else None.
    """
    cleaned = clean_url(url).lower()
    
    # Instagram profile check
    if "instagram.com" in cleaned:
        path = re.sub(r'^https?://(www\.)?instagram\.com/', '', cleaned).strip('/')
        path_parts = path.split('/')
        if path_parts and path_parts[0]:
            first_segment = path_parts[0].split('?')[0]
            if first_segment not in ['p', 'reel', 'reels', 'tv', 'stories', 'explore', 'direct', 'accounts']:
                return ("Instagram", first_segment)

    # TikTok profile check
    if "tiktok.com" in cleaned:
        path = re.sub(r'^https?://(www\.)?tiktok\.com/', '', cleaned).strip('/')
        if path.startswith('@') and '/video/' not in path:
            return ("TikTok", path.split('?')[0])

    return None

def get_platform_name(url: str) -> str:
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "YouTube 🔴"
    elif "instagram.com" in url_lower:
        return "Instagram 📸"
    elif "facebook.com" in url_lower or "fb.watch" in url_lower or "fb.me" in url_lower or "fb.com" in url_lower:
        return "Facebook 🔵"
    elif "tiktok.com" in url_lower:
        return "TikTok 🎵"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "Twitter / X 🐦"
    elif "pinterest.com" in url_lower or "pin.it" in url_lower:
        return "Pinterest 📌"
    return "Social Media 🌐"

def extract_instagram_graphql(shortcode: str) -> Optional[Dict[str, Any]]:
    """Fetch Instagram media directly via GraphQL API (supports photos, carousels, videos)."""
    try:
        api_url = f'https://www.instagram.com/graphql/query/?doc_id=10015901848480474&variables={{"shortcode":"{shortcode}"}}'
        resp = requests.get(api_url, headers=IG_GRAPHQL_HEADERS, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            media = data.get('data', {}).get('xdt_shortcode_media')
            return media
    except Exception as e:
        logger.error(f"Instagram GraphQL query error for shortcode {shortcode}: {e}")
    return None

def download_media_sync(url: str, is_audio: bool = False, quality: str = "720") -> Dict[str, Any]:
    """Download video with selected quality (1080, 720, 480, 360) or audio using yt-dlp / direct API."""
    target_url = clean_url(url)
    
    # 1. Try Instagram Direct Video API if applicable
    ig_match = re.search(r'instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)', target_url)
    if ig_match:
        shortcode = ig_match.group(1)
        ig_data = extract_instagram_graphql(shortcode)
        if ig_data:
            is_video = ig_data.get('is_video', False)
            video_url = ig_data.get('video_url')
            caption_edges = ig_data.get('edge_media_to_caption', {}).get('edges', [])
            title = caption_edges[0].get('node', {}).get('text', 'Instagram Video') if caption_edges else 'Instagram Video'
            
            if is_video and video_url and not is_audio:
                # Direct download MP4
                unique_name = f"ig_vid_{uuid.uuid4().hex[:8]}.mp4"
                file_path = os.path.join(DOWNLOAD_DIR, unique_name)
                v_resp = requests.get(video_url, headers=DEFAULT_HEADERS, timeout=30)
                if v_resp.status_code == 200:
                    with open(file_path, "wb") as f:
                        f.write(v_resp.content)
                    return {
                        'file_path': file_path,
                        'title': title[:150],
                        'duration': ig_data.get('video_duration', 0),
                        'thumbnail': ig_data.get('display_url'),
                        'filesize': len(v_resp.content),
                        'is_audio': False,
                        'quality': 'HD',
                        'ext': 'mp4'
                    }

    COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
    temp_cookie = None
    
    # 2. General yt-dlp extraction
    file_prefix = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex[:8]}_%(epoch)s")
    if is_audio:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{file_prefix}.%(ext)s',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
    else:
        height = quality if quality in ["1080", "720", "480", "360"] else "720"
        ydl_opts = {
            'format': (
                f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/'
                f'bestvideo[height<={height}]+bestaudio/'
                f'best[height<={height}][ext=mp4]/'
                f'best[height<={height}]/'
                f'best'
            ),
            'outtmpl': f'{file_prefix}.%(ext)s',
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }

    if os.path.exists(COOKIE_FILE):
        temp_cookie = os.path.join(DOWNLOAD_DIR, f"cookie_{uuid.uuid4().hex[:8]}.txt")
        shutil.copyfile(COOKIE_FILE, temp_cookie)
        ydl_opts['cookiefile'] = temp_cookie

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=True)
            filename = ydl.prepare_filename(info)
            
            if is_audio:
                base_name, _ = os.path.splitext(filename)
                filename = f"{base_name}.mp3"
            elif not os.path.exists(filename):
                base_name, _ = os.path.splitext(filename)
                if os.path.exists(f"{base_name}.mp4"):
                    filename = f"{base_name}.mp4"

            # Check if actual file exists
            if not os.path.exists(filename):
                prefix_match = os.path.basename(file_prefix).split("%")[0]
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(prefix_match):
                        filename = os.path.join(DOWNLOAD_DIR, f)
                        break

            file_size = os.path.getsize(filename) if os.path.exists(filename) else 0

            return {
                'file_path': filename,
                'title': info.get('title', 'Media'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', None),
                'filesize': file_size,
                'is_audio': is_audio,
                'quality': quality if not is_audio else 'MP3',
                'ext': os.path.splitext(filename)[1].replace('.', '').lower() if filename else 'mp4'
            }
    finally:
        if temp_cookie and os.path.exists(temp_cookie):
            try:
                os.remove(temp_cookie)
            except Exception:
                pass

def download_images_sync(url: str) -> Dict[str, Any]:
    """Download images/photos from Instagram, Facebook, Pinterest, Twitter, etc."""
    target_url = clean_url(url)
    downloaded_files: List[str] = []
    title = "Post Images"
    
    # 1. Direct Instagram GraphQL API (handles carousel albums and single photos in Full HD!)
    ig_match = re.search(r'instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)', target_url)
    if ig_match:
        shortcode = ig_match.group(1)
        ig_data = extract_instagram_graphql(shortcode)
        if ig_data:
            caption_edges = ig_data.get('edge_media_to_caption', {}).get('edges', [])
            if caption_edges:
                title = caption_edges[0].get('node', {}).get('text', title)
            
            # Check for carousel children
            children = ig_data.get('edge_sidecar_to_children', {}).get('edges', [])
            image_urls = []
            if children:
                for c in children:
                    node = c.get('node', {})
                    display_url = node.get('display_url')
                    if display_url:
                        image_urls.append(display_url)
            else:
                # Single photo
                display_url = ig_data.get('display_url')
                if display_url:
                    image_urls.append(display_url)

            # Download all Instagram images without restriction
            for i, img_url in enumerate(image_urls):
                try:
                    img_resp = requests.get(img_url, headers=DEFAULT_HEADERS, timeout=15)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1024:
                        filename = os.path.join(DOWNLOAD_DIR, f"ig_img_{shortcode}_{i}.jpg")
                        with open(filename, "wb") as f:
                            f.write(img_resp.content)
                        downloaded_files.append(filename)
                except Exception as e:
                    logger.error(f"Error downloading IG image {img_url}: {e}")

            if downloaded_files:
                return {
                    'image_paths': downloaded_files,
                    'title': title[:150],
                    'count': len(downloaded_files)
                }

    # 2. Try with yt-dlp
    try:
        unique_id = uuid.uuid4().hex[:8]
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, f"img_{unique_id}_%(autonumber)s.%(ext)s"),
            'noplaylist': False,
            'quiet': True,
            'no_warnings': True,
            'http_headers': DEFAULT_HEADERS,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=True)
            if info:
                title = info.get('title') or info.get('description') or title
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(f"img_{unique_id}"):
                        full_path = os.path.join(DOWNLOAD_DIR, f)
                        ext = os.path.splitext(f)[1].lower()
                        if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                            downloaded_files.append(full_path)
    except Exception as e:
        logger.warning(f"yt-dlp image download fallback: {e}")

    # 3. Web scraper fallback (Facebook, Pinterest, Twitter, etc.)
    if not downloaded_files:
        try:
            session = requests.Session()
            session.headers.update(DEFAULT_HEADERS)
            resp = session.get(target_url, timeout=15, allow_redirects=True)
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content"):
                    title = og_title["content"]
                elif soup.title:
                    title = soup.title.string or title

                image_urls = set()
                for meta in soup.find_all("meta"):
                    prop = meta.get("property", "") or meta.get("name", "")
                    content = meta.get("content", "")
                    if prop in ["og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"] and content:
                        if content.startswith("http"):
                            image_urls.add(content)

                for img in soup.find_all("img"):
                    src = img.get("src") or img.get("data-src")
                    if src and src.startswith("http"):
                        if any(x in src.lower() for x in ['fbcdn.net', 'cdninstagram.com', 'pinimg.com', 'twimg.com', 'redd.it']):
                            image_urls.add(src)

                for i, img_url in enumerate(list(image_urls)[:10]):
                    try:
                        img_resp = session.get(img_url, timeout=10)
                        if img_resp.status_code == 200 and len(img_resp.content) > 10240:
                            ext = ".jpg"
                            if "png" in img_resp.headers.get("Content-Type", ""):
                                ext = ".png"
                            elif "webp" in img_resp.headers.get("Content-Type", ""):
                                ext = ".webp"
                            
                            filename = os.path.join(DOWNLOAD_DIR, f"post_img_{uuid.uuid4().hex[:8]}_{i}{ext}")
                            with open(filename, "wb") as f:
                                f.write(img_resp.content)
                            downloaded_files.append(filename)
                    except Exception as err:
                        logger.error(f"Failed to download image URL {img_url}: {err}")

        except Exception as e:
            logger.error(f"Fallback scraper failed for {target_url}: {e}")

    return {
        'image_paths': downloaded_files,
        'title': title[:150],
        'count': len(downloaded_files)
    }

async def download_media(url: str, is_audio: bool = False, quality: str = "720") -> Dict[str, Any]:
    """Async wrapper around download_media_sync."""
    return await asyncio.to_thread(download_media_sync, url, is_audio, quality)

async def download_images(url: str) -> Dict[str, Any]:
    """Async wrapper around download_images_sync."""
    return await asyncio.to_thread(download_images_sync, url)

def cleanup_file(filepath: str):
    """Safely delete temporary downloaded file."""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Cleaned up file: {filepath}")
    except Exception as e:
        logger.error(f"Error removing file {filepath}: {e}")

def cleanup_files(filepaths: List[str]):
    """Safely delete multiple temporary files."""
    for p in filepaths:
        cleanup_file(p)
