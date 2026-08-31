import os
import re
import uuid
import time
import shutil
import asyncio
import subprocess
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

def clean_media_title(title: str) -> str:
    """Sanitize title: remove hashtags, view/reaction statistics, and extra separators."""
    if not title:
        return "Media"
    t = str(title)
    # 1. Remove hashtags (#reels, #viral, #bangla, #tiktok, etc.)
    t = re.sub(r'#[\w\d_\u0980-\u09FF\u00C0-\u017F]+', '', t)
    # 2. Remove view / reaction count prefix if present (e.g. 8.9M views • 234K reactions |)
    t = re.sub(r'^\s*\d+(?:\.\d+)?[MKmk]?\s*views?\s*[•|·\s]*\d*(?:\.\d+)?[MKmk]?\s*(?:reactions?|likes?)?\s*[|•·-]\s*', '', t, flags=re.IGNORECASE)
    # 3. Clean up redundant separators
    t = re.sub(r'\s*[|•·-]\s*[|•·-]+\s*', ' | ', t)
    # 4. Collapse spaces and trim
    t = re.sub(r'\s+', ' ', t).strip(' \t\n\r|•·-')
    return t or "Media"

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
        if path.startswith('@') and '/video/' not in path and '/photo/' not in path:
            return ("TikTok", path.split('?')[0])

    return None

def extract_tiktok_info(url: str) -> Optional[Dict[str, Any]]:
    """Extract TikTok media info (video, photo slideshows, audio) without watermark using TikWM API & redirect resolver."""
    target_url = clean_url(url)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
    }
    
    # 1. Resolve redirect if short link (vm.tiktok.com, vt.tiktok.com, /t/)
    final_url = target_url
    if any(s in target_url.lower() for s in ['vm.tiktok.com', 'vt.tiktok.com', '/t/']):
        try:
            s = requests.Session()
            s.headers.update(headers)
            r = s.get(target_url, allow_redirects=True, timeout=8)
            if r.status_code == 200:
                final_url = r.url.split('?')[0]
        except Exception as e:
            logger.warning(f"TikTok short URL redirect resolution: {e}")

    # 2. Try TikWM API
    for test_u in [target_url, final_url]:
        try:
            api_resp = requests.post(
                'https://www.tikwm.com/api/',
                data={'url': test_u, 'hd': 1},
                headers=headers,
                timeout=12
            )
            if api_resp.status_code == 200:
                data = api_resp.json()
                if data.get('code') == 0:
                    d = data.get('data', {})
                    raw_title = d.get('title') or 'TikTok Media'
                    title = clean_media_title(raw_title)
                    thumb = d.get('cover') or d.get('origin_cover')
                    duration = d.get('duration', 0)
                    images = d.get('images', [])
                    play_url = d.get('hdplay') or d.get('play')
                    music_url = d.get('music')
                    
                    if images and len(images) > 0:
                        return {
                            'status': 'success',
                            'platform': 'TikTok',
                            'title': title[:120],
                            'thumbnail': images[0],
                            'is_album': True,
                            'photo_count': len(images),
                            'photos': images,
                            'audio_url': music_url,
                            'formats': [
                                {'id': 'album', 'label': f'🖼️ Download All ({len(images)} Photos)', 'type': 'album', 'badge': f'{len(images)}P', 'size': f'~ {round(len(images) * 0.8, 1)} MB'},
                                {'id': 'img_zip', 'label': '📦 Download as ZIP Album', 'type': 'album', 'badge': 'ZIP', 'size': f'~ {round(len(images) * 0.8, 1)} MB'},
                                {'id': 'MP3', 'label': '🎵 Background Music (MP3)', 'type': 'audio', 'badge': 'Audio', 'size': '~ 3.0 MB'}
                            ]
                        }
                    
                    if play_url:
                        vid_sz = d.get('hd_size') or d.get('size') or 0
                        sz_str = f'~ {round(vid_sz / (1024 * 1024), 1)} MB' if vid_sz else '~ 8.5 MB'
                        return {
                            'status': 'success',
                            'platform': 'TikTok',
                            'title': title[:120],
                            'thumbnail': thumb,
                            'duration': int(duration),
                            'is_album': False,
                            'video_url': play_url,
                            'audio_url': music_url,
                            'formats': [
                                {'id': '1080', 'label': '🎬 Full HD (No Watermark)', 'type': 'video', 'badge': 'FHD', 'size': sz_str},
                                {'id': '720', 'label': '🎬 720p HD (No Watermark)', 'type': 'video', 'badge': 'HD', 'size': '~ 4.5 MB'},
                                {'id': 'MP3', 'label': '🎵 MP3 Audio (320kbps)', 'type': 'audio', 'badge': 'Audio', 'size': '~ 2.5 MB'}
                            ]
                        }
        except Exception as err:
            logger.warning(f"TikWM query error for {test_u}: {err}")

    return None

def extract_facebook_info(url: str) -> Optional[Dict[str, Any]]:
    """Extract Facebook media info (HD/SD videos, Reels, multi-photo posts) using direct HTML extraction & redirect resolution."""
    target_url = clean_url(url)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Sec-Fetch-Mode': 'navigate',
    }
    
    # 1. Resolve redirect for share links, fb.watch, fb.me, etc.
    resolved_url = target_url
    raw_html = ""
    try:
        s = requests.Session()
        s.headers.update(headers)
        r = s.get(target_url, allow_redirects=True, timeout=12)
        if r.status_code == 200:
            resolved_url = r.url
            raw_html = r.text
    except Exception as e:
        logger.warning(f"Facebook request error: {e}")

    hd_url = None
    sd_url = None
    title = "Facebook Video"
    thumb = None
    duration = 0
    fb_images = []

    if raw_html:
        unescaped = raw_html.replace(r'\/', '/').replace(r'\u0026', '&').replace('&amp;', '&')

        # Title
        soup = BeautifulSoup(raw_html, 'html.parser')
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content']
        elif soup.title:
            title = soup.title.string or title

        # Thumbnail
        og_img = soup.find('meta', property='og:image')
        if og_img and og_img.get('content') and og_img['content'].startswith('http'):
            thumb = og_img['content']

        # Video regexes
        hd_patterns = [
            r'"browser_native_hd_url"\s*:\s*"([^"]+)"',
            r'"playable_url_quality_hd"\s*:\s*"([^"]+)"',
            r'hd_src_no_ratelimit\s*:\s*"([^"]+)"',
            r'hd_src\s*:\s*"([^"]+)"',
            r'"hd_src"\s*:\s*"([^"]+)"',
        ]
        sd_patterns = [
            r'"browser_native_sd_url"\s*:\s*"([^"]+)"',
            r'"playable_url"\s*:\s*"([^"]+)"',
            r'sd_src_no_ratelimit\s*:\s*"([^"]+)"',
            r'sd_src\s*:\s*"([^"]+)"',
            r'"sd_src"\s*:\s*"([^"]+)"',
        ]

        for p in hd_patterns:
            m = re.search(p, unescaped)
            if m:
                hd_url = m.group(1).replace(r'\/', '/').replace(r'\u0026', '&')
                break

        for p in sd_patterns:
            m = re.search(p, unescaped)
            if m:
                sd_url = m.group(1).replace(r'\/', '/').replace(r'\u0026', '&')
                break

        # Check for photo post images if no video found
        if not (hd_url or sd_url):
            og_type = soup.find('meta', property='og:type')
            og_type_val = og_type.get('content', '') if og_type else ''
            if 'video' not in og_type_val.lower():
                if thumb and thumb.startswith('http'):
                    fb_images.append(thumb)
                for img in soup.find_all('img'):
                    src = img.get('src') or img.get('data-src')
                    if src and 'fbcdn.net' in src and not any(x in src for x in ['static.', 'rsrc.', 'emoji', 'icon', 'p50x50', 'p100x100']):
                        if src not in fb_images:
                            fb_images.append(src)

    # 2. If direct HTML didn't get video, try yt-dlp on resolved_url
    if not (hd_url or sd_url) and not fb_images:
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(resolved_url, download=False)
                if info:
                    title = info.get('title', title)
                    thumb = info.get('thumbnail', thumb)
                    duration = info.get('duration', 0)
                    formats = info.get('formats', [])
                    for f in formats:
                        u = f.get('url')
                        fid = str(f.get('format_id', '')).lower()
                        if 'hd' in fid and not hd_url:
                            hd_url = u
                        elif not sd_url:
                            sd_url = u
        except Exception as yt_err:
            logger.warning(f"Facebook yt-dlp fallback: {yt_err}")

    # Build result
    best_vid = hd_url or sd_url
    if best_vid:
        return {
            'status': 'success',
            'platform': 'Facebook',
            'title': clean_media_title(title)[:120],
            'thumbnail': thumb,
            'duration': int(duration) if duration else 0,
            'is_album': False,
            'video_url': best_vid,
            'hd_url': hd_url or sd_url,
            'sd_url': sd_url or hd_url,
            'formats': [
                {'id': '1080', 'label': '🎬 HD Video (1080p/720p)', 'type': 'video', 'badge': 'HD', 'size': '~ 15.0 MB'},
                {'id': '720', 'label': '🎬 SD Video (Standard)', 'type': 'video', 'badge': 'SD', 'size': '~ 8.0 MB'},
                {'id': 'MP3', 'label': '🎵 MP3 Audio (320kbps)', 'type': 'audio', 'badge': 'Audio', 'size': '~ 3.0 MB'},
            ]
        }
    elif fb_images:
        if len(fb_images) > 1:
            return {
                'status': 'success',
                'platform': 'Facebook',
                'title': clean_media_title(title)[:120],
                'thumbnail': fb_images[0],
                'is_album': True,
                'photo_count': len(fb_images),
                'photos': fb_images,
                'formats': [
                    {'id': 'album', 'label': f'🖼️ Download All ({len(fb_images)} Photos)', 'type': 'album', 'badge': f'{len(fb_images)}P', 'size': f'~ {round(len(fb_images) * 1.5, 1)} MB'},
                    {'id': 'img_zip', 'label': '📦 Download as ZIP Album', 'type': 'album', 'badge': 'ZIP', 'size': f'~ {round(len(fb_images) * 1.5, 1)} MB'},
                ]
            }
        else:
            return {
                'status': 'success',
                'platform': 'Facebook',
                'title': clean_media_title(title)[:120],
                'thumbnail': fb_images[0],
                'is_album': False,
                'photos': fb_images,
                'formats': [
                    {'id': 'img', 'label': '🖼️ Download HD Photo', 'type': 'image', 'badge': 'HD', 'size': '~ 1.5 MB'},
                ]
            }

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

def get_highest_res_ig_node_url(node: Dict[str, Any]) -> str:
    """Extract the highest resolution image URL from an Instagram node."""
    display_resources = node.get('display_resources') or []
    if display_resources:
        sorted_res = sorted(display_resources, key=lambda x: (x.get('config_width', 0) * x.get('config_height', 0)), reverse=True)
        if sorted_res and sorted_res[0].get('src'):
            return sorted_res[0]['src']
    
    candidates = node.get('image_versions2', {}).get('candidates', [])
    if candidates:
        sorted_cands = sorted(candidates, key=lambda x: (x.get('width', 0) * x.get('height', 0)), reverse=True)
        if sorted_cands and sorted_cands[0].get('url'):
            return sorted_cands[0]['url']
            
    return node.get('display_url') or ''

def select_highest_quality_photos(urls: List[str]) -> List[str]:
    """
    Given a list of candidate image URLs, deduplicate by photo ID and pick the
    highest resolution / unconstrained quality URL for each unique image.
    """
    by_photo_id: Dict[str, List[str]] = {}
    for u in urls:
        m = re.search(r'/(\d+_\d+_\d+_[a-z0-9]+)', u)
        key = m.group(1) if m else u.split('?')[0]
        if key not in by_photo_id:
            by_photo_id[key] = []
        by_photo_id[key].append(u)

    highest_res_urls = []
    for key, cand_urls in by_photo_id.items():
        if len(cand_urls) == 1:
            highest_res_urls.append(cand_urls[0])
            continue

        def _score(url: str) -> int:
            score = 0
            if 'instagram.f' in url or 'scontent.f' in url:
                score += 10
            if '_s640x640' not in url and '_s480x480' not in url and '_s320x320' not in url:
                score += 50
            if 'dst-jpg_e35_s' not in url:
                score += 30
            return score

        best_cand = max(cand_urls, key=_score)
        highest_res_urls.append(best_cand)

    return highest_res_urls

IG_MOBILE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

def extract_instagram_post_info(target_url: str, shortcode: str) -> Optional[Dict[str, Any]]:
    """Extract Instagram metadata, videos, single photos, and carousel multi-photo albums at maximum quality."""
    # 1. Try GraphQL API first
    ig_data = extract_instagram_graphql(shortcode)
    if ig_data:
        is_video = ig_data.get('is_video', False)
        caption_edges = ig_data.get('edge_media_to_caption', {}).get('edges', [])
        title = caption_edges[0].get('node', {}).get('text', 'Instagram Post') if caption_edges else 'Instagram Post'
        thumb = get_highest_res_ig_node_url(ig_data) or ig_data.get('display_url')
        duration = ig_data.get('video_duration', 0)
        
        children = ig_data.get('edge_sidecar_to_children', {}).get('edges', [])
        if children:
            photos = []
            for c in children:
                node = c.get('node', {})
                best_photo_url = get_highest_res_ig_node_url(node)
                if best_photo_url:
                    photos.append(best_photo_url)
                elif node.get('video_url'):
                    photos.append(node['video_url'])
            if photos:
                return {
                    'status': 'success',
                    'platform': 'Instagram',
                    'title': clean_media_title(title)[:120],
                    'thumbnail': photos[0],
                    'is_album': True,
                    'photo_count': len(photos),
                    'photos': photos,
                    'formats': [
                        {'id': 'album', 'label': f'🖼️ Download All ({len(photos)} Photos)', 'type': 'album', 'badge': f'{len(photos)}P', 'size': f'~ {round(len(photos) * 1.5, 1)} MB'},
                        {'id': 'img_zip', 'label': '📦 Download as ZIP Album', 'type': 'album', 'badge': 'ZIP', 'size': f'~ {round(len(photos) * 1.5, 1)} MB'}
                    ]
                }
        
        if is_video:
            return {
                'status': 'success',
                'platform': 'Instagram',
                'title': clean_media_title(title)[:120],
                'thumbnail': thumb,
                'duration': int(duration),
                'is_album': False,
                'formats': [
                    {'id': '1080', 'label': '🎬 1080p Full HD', 'type': 'video', 'badge': 'FHD', 'size': '~ 12.5 MB'},
                    {'id': '720', 'label': '🎬 720p HD', 'type': 'video', 'badge': 'HD', 'size': '~ 6.5 MB'},
                    {'id': 'MP3', 'label': '🎵 MP3 Audio (320kbps)', 'type': 'audio', 'badge': 'Audio', 'size': '~ 2.0 MB'}
                ]
            }
        else:
            return {
                'status': 'success',
                'platform': 'Instagram',
                'title': clean_media_title(title)[:120],
                'thumbnail': thumb,
                'is_album': False,
                'formats': [
                    {'id': 'img', 'label': '🖼️ Download HD Photo', 'type': 'image', 'badge': 'HD', 'size': '~ 1.5 MB'}
                ]
            }

    # 2. Direct Mobile SSR Webpage HTML Extraction (Extracts full carousel images & videos without login)
    try:
        session = requests.Session()
        html_resp = session.get(f"https://www.instagram.com/p/{shortcode}/", headers=IG_MOBILE_HEADERS, timeout=12)
        if html_resp.status_code == 200:
            raw_html = html_resp.text
            unescaped = raw_html.replace(r'\/', '/').replace(r'\u0026', '&').replace(r'\u003C', '<').replace(r'\u003E', '>').replace('&amp;', '&')
            
            # Title extraction
            soup = BeautifulSoup(raw_html, 'html.parser')
            og_title = soup.find('meta', property='og:title')
            title = og_title['content'] if og_title and og_title.get('content') else (soup.title.string if soup.title else "Instagram Post")

            # Check if there is a video in the post
            video_matches = set(re.findall(r'https://[^\s"\'<>]*(?:cdninstagram\.com|fbcdn\.net)[^\s"\'<>]*\.mp4[^\s"\'<>]*', unescaped))
            if video_matches:
                vid_url = list(video_matches)[0]
                og_img = soup.find('meta', property='og:image')
                thumb_url = og_img['content'] if og_img and og_img.get('content') else None
                return {
                    'status': 'success',
                    'platform': 'Instagram',
                    'title': clean_media_title(title)[:120],
                    'thumbnail': thumb_url,
                    'duration': 0,
                    'is_album': False,
                    'video_url': vid_url,
                    'formats': [
                        {'id': '1080', 'label': '🎬 1080p Full HD', 'type': 'video', 'badge': 'FHD', 'size': '~ 12.5 MB'},
                        {'id': '720', 'label': '🎬 720p HD', 'type': 'video', 'badge': 'HD', 'size': '~ 6.5 MB'},
                        {'id': 'MP3', 'label': '🎵 MP3 Audio (320kbps)', 'type': 'audio', 'badge': 'Audio', 'size': '~ 2.0 MB'}
                    ]
                }

            # Extract photos
            all_scontent = set(re.findall(r'https://[^\s"\'<>]*(?:cdninstagram\.com|fbcdn\.net)[^\s"\'<>]*', unescaped))
            post_cands = []
            for u in all_scontent:
                if ('/v/t51.82787-15/' in u or '/v/t51.' in u or '/v/t50.' in u) and not any(x in u for x in ['s150x150', 's320x320', 'p50x50', 's240x240', '-19/']):
                    post_cands.append(u)

            post_images = select_highest_quality_photos(post_cands)
            
            # If no regex matches, check og:image
            if not post_images:
                og_img = soup.find('meta', property='og:image')
                if og_img and og_img.get('content') and og_img['content'].startswith('http'):
                    post_images = [og_img['content']]
            
            if post_images:
                if len(post_images) > 1:
                    return {
                        'status': 'success',
                        'platform': 'Instagram',
                        'title': title[:120],
                        'thumbnail': post_images[0],
                        'is_album': True,
                        'photo_count': len(post_images),
                        'photos': post_images,
                        'formats': [
                            {'id': 'album', 'label': f'🖼️ Download All ({len(post_images)} Photos)', 'type': 'album', 'badge': f'{len(post_images)}P', 'size': f'~ {round(len(post_images) * 1.5, 1)} MB'},
                            {'id': 'img_zip', 'label': '📦 Download as ZIP Album', 'type': 'album', 'badge': 'ZIP', 'size': f'~ {round(len(post_images) * 1.5, 1)} MB'}
                        ]
                    }
                else:
                    return {
                        'status': 'success',
                        'platform': 'Instagram',
                        'title': title[:120],
                        'thumbnail': post_images[0],
                        'is_album': False,
                        'photos': post_images,
                        'formats': [
                            {'id': 'img', 'label': '🖼️ Download HD Photo', 'type': 'image', 'badge': 'HD', 'size': '~ 1.5 MB'}
                        ]
                    }
    except Exception as ig_err:
        logger.warning(f"Instagram mobile SSR fallback failed: {ig_err}")

    return None

def extract_media_info_sync(url: str) -> Dict[str, Any]:
    """Extract media metadata (title, thumbnail, duration, available qualities) without downloading."""
    target_url = clean_url(url)
    platform = get_platform_name(target_url)
    
    # 1. Instagram extraction
    ig_match = re.search(r'instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)', target_url)
    if ig_match:
        shortcode = ig_match.group(1)
        ig_res = extract_instagram_post_info(target_url, shortcode)
        if ig_res:
            return ig_res

    # 2. TikTok extraction
    if any(x in target_url.lower() for x in ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com"]):
        tt_res = extract_tiktok_info(target_url)
        if tt_res:
            return tt_res

    # 3. Facebook extraction
    if any(x in target_url.lower() for x in ["facebook.com", "fb.watch", "fb.me", "fb.com"]):
        fb_res = extract_facebook_info(target_url)
        if fb_res:
            return fb_res

    # 2. General yt-dlp metadata extraction
    COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
    temp_cookie = None
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'js_runtimes': {'node': {}},
        'remote_components': ['ejs:github', 'ejs:npm'],
    }
    if os.path.exists(COOKIE_FILE):
        temp_cookie = os.path.join(DOWNLOAD_DIR, f"info_cookie_{uuid.uuid4().hex[:8]}.txt")
        shutil.copyfile(COOKIE_FILE, temp_cookie)
        ydl_opts['cookiefile'] = temp_cookie

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
            title = info.get('title', 'Media')
            thumb = info.get('thumbnail')
            duration = info.get('duration') or 0
            raw_formats = info.get('formats') or []

            # -------------------------------------------------------------
            # Compute exact / estimated file size for each resolution & MP3
            # -------------------------------------------------------------
            audio_fmts = [f for f in raw_formats if f.get('vcodec') == 'none' and f.get('acodec') not in ('none', None)]
            best_audio_sz = 0
            if audio_fmts:
                a_sizes = []
                for f in audio_fmts:
                    sz = f.get('filesize') or f.get('filesize_approx')
                    if not sz and f.get('tbr') and duration:
                        sz = (f['tbr'] * 1000 / 8) * duration
                    if sz:
                        a_sizes.append(sz)
                if a_sizes:
                    best_audio_sz = max(a_sizes)
            if not best_audio_sz and duration:
                best_audio_sz = (128 * 1000 / 8) * duration

            def get_format_size_str(target_h: int) -> str:
                try:
                    fmt_str = f'bestvideo[height<={target_h}]+bestaudio/best[height<={target_h}]/best'
                    selector = ydl.build_format_selector(fmt_str)
                    selected = list(selector({'formats': raw_formats, 'incomplete_formats': False}))
                    if selected:
                        sel = selected[0]
                        req_fmts = sel.get('requested_formats', [sel])
                        total_sz = 0
                        for rf in req_fmts:
                            sz = rf.get('filesize') or rf.get('filesize_approx')
                            if not sz and rf.get('tbr') and duration:
                                sz = (rf['tbr'] * 1000 / 8) * duration
                            total_sz += (sz or 0)
                        if total_sz > 0:
                            mb = total_sz / (1024 * 1024)
                            return f"{round(mb, 1)} MB" if mb < 1000 else f"{round(mb / 1024, 2)} GB"
                except Exception as err:
                    logger.warning(f"Format size calculation fallback for {target_h}p: {err}")

                if duration:
                    bitrates = {1080: 800, 720: 500, 480: 350, 360: 250}
                    br = bitrates.get(target_h, 400)
                    est_bytes = ((br + 128) * 1000 / 8) * duration
                    mb = est_bytes / (1024 * 1024)
                    return f"{round(mb, 1)} MB"
                return ""

            mp3_mb = round(best_audio_sz / (1024 * 1024), 1) if best_audio_sz > 0 else (round((320 * 1000 / 8 * duration) / (1024 * 1024), 1) if duration else 0)
            mp3_sz_str = f"{mp3_mb} MB" if mp3_mb > 0 else ""
            
            # Format list with exact matching sizes
            formats = [
                {'id': '1080', 'label': '🎬 1080p Full HD', 'type': 'video', 'badge': 'FHD', 'size': get_format_size_str(1080)},
                {'id': '720', 'label': '🎬 720p HD', 'type': 'video', 'badge': 'HD', 'size': get_format_size_str(720)},
                {'id': '480', 'label': '🎬 480p SD', 'type': 'video', 'badge': 'SD', 'size': get_format_size_str(480)},
                {'id': '360', 'label': '🎬 360p Fast', 'type': 'video', 'badge': 'Fast', 'size': get_format_size_str(360)},
                {'id': 'MP3', 'label': '🎵 MP3 Audio (320kbps)', 'type': 'audio', 'badge': 'Audio', 'size': mp3_sz_str},
            ]
            
            return {
                'status': 'success',
                'platform': platform.replace(' 🔴', '').replace(' 📸', '').replace(' 🔵', '').replace(' 🎵', '').replace(' 🐦', '').replace(' 📌', '').replace(' 🌐', ''),
                'title': clean_media_title(title),
                'thumbnail': thumb,
                'duration': int(duration) if duration else 0,
                'formats': formats
            }
    except Exception as e:
        err_msg = str(e)
        logger.warning(f"Metadata extraction fallback triggered for {target_url}: {err_msg}")
        
        # If yt-dlp fails with "No video formats found", check if it's an image post or photo carousel
        if "no video formats found" in err_msg.lower() or "there's no video in this" in err_msg.lower() or "instagram" in target_url.lower() or "facebook" in target_url.lower():
            if ig_match:
                ig_res = extract_instagram_post_info(target_url, ig_match.group(1))
                if ig_res:
                    return ig_res

        # Format a clean, human-friendly error message
        friendly_error = "Could not fetch media. Please make sure the post is public and the link is valid."
        if "private" in err_msg.lower():
            friendly_error = "This post is private or requires login to view."
        elif "not found" in err_msg.lower() or "404" in err_msg:
            friendly_error = "Post not found. Please check if the URL is correct."
        elif "no video formats found" in err_msg.lower():
            friendly_error = "No downloadable media found in this post."

        return {
            'status': 'error',
            'error': friendly_error,
            'platform': platform,
            'title': 'Media',
            'formats': [
                {'id': '720', 'label': '🎬 720p HD', 'type': 'video', 'badge': 'HD', 'size': ''},
                {'id': '480', 'label': '🎬 480p SD', 'type': 'video', 'badge': 'SD', 'size': ''},
                {'id': 'MP3', 'label': '🎵 MP3 Audio', 'type': 'audio', 'badge': 'Audio', 'size': ''}
            ]
        }
    finally:
        if temp_cookie and os.path.exists(temp_cookie):
            try:
                os.remove(temp_cookie)
            except Exception:
                pass

# Real-time progress store: task_id -> { status, percent, downloaded_mb, total_mb, speed, eta, msg }
PROGRESS_STORE: Dict[str, Any] = {}

def download_media_sync(url: str, is_audio: bool = False, quality: str = "720", task_id: Optional[str] = None) -> Dict[str, Any]:
    """Download video with selected quality (1080, 720, 480, 360) or audio using yt-dlp / direct API."""
    target_url = clean_url(url)
    
    if task_id:
        PROGRESS_STORE[task_id] = {
            'status': 'starting',
            'percent': 0,
            'downloaded_mb': 0,
            'total_mb': 0,
            'speed': '',
            'eta': '',
            'msg': 'Connecting to media server...'
        }

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
                    if task_id:
                        PROGRESS_STORE[task_id] = {'status': 'completed', 'percent': 100, 'msg': 'Download Complete!'}
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

    # 2. Try TikTok Direct Video/Audio API if applicable
    if any(x in target_url.lower() for x in ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com"]):
        tt_info = extract_tiktok_info(target_url)
        if tt_info:
            title = tt_info.get('title', 'TikTok Video')
            thumb = tt_info.get('thumbnail')
            duration = tt_info.get('duration', 0)
            
            if is_audio:
                audio_url = tt_info.get('audio_url')
                if audio_url:
                    unique_name = f"tt_audio_{uuid.uuid4().hex[:8]}.mp3"
                    file_path = os.path.join(DOWNLOAD_DIR, unique_name)
                    a_resp = requests.get(audio_url, headers=DEFAULT_HEADERS, timeout=30, stream=True)
                    if a_resp.status_code == 200:
                        total_bytes = int(a_resp.headers.get('content-length', 0))
                        downloaded = 0
                        with open(file_path, "wb") as f:
                            for chunk in a_resp.iter_content(chunk_size=65536):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if task_id and total_bytes > 0:
                                        pct = round((downloaded / total_bytes * 100), 1)
                                        PROGRESS_STORE[task_id] = {
                                            'status': 'downloading',
                                            'percent': pct,
                                            'downloaded_mb': round(downloaded / (1024*1024), 2),
                                            'total_mb': round(total_bytes / (1024*1024), 2),
                                            'msg': f"Downloading audio {pct}%..."
                                        }
                        if task_id:
                            PROGRESS_STORE[task_id] = {'status': 'completed', 'percent': 100, 'msg': 'Download Complete!'}
                        file_sz = os.path.getsize(file_path)
                        return {
                            'file_path': file_path,
                            'title': title[:150],
                            'duration': duration,
                            'thumbnail': thumb,
                            'filesize': file_sz,
                            'is_audio': True,
                            'quality': '320kbps',
                            'ext': 'mp3'
                        }
            else:
                video_url = tt_info.get('video_url')
                if video_url:
                    unique_name = f"tt_vid_{uuid.uuid4().hex[:8]}.mp4"
                    file_path = os.path.join(DOWNLOAD_DIR, unique_name)
                    v_resp = requests.get(video_url, headers=DEFAULT_HEADERS, timeout=35, stream=True)
                    if v_resp.status_code == 200:
                        total_bytes = int(v_resp.headers.get('content-length', 0))
                        downloaded = 0
                        with open(file_path, "wb") as f:
                            for chunk in v_resp.iter_content(chunk_size=65536):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if task_id and total_bytes > 0:
                                        pct = round((downloaded / total_bytes * 100), 1)
                                        PROGRESS_STORE[task_id] = {
                                            'status': 'downloading',
                                            'percent': pct,
                                            'downloaded_mb': round(downloaded / (1024*1024), 2),
                                            'total_mb': round(total_bytes / (1024*1024), 2),
                                            'msg': f"Downloading video {pct}% ({round(downloaded/(1024*1024), 1)} MB)..."
                                        }
                        if task_id:
                            PROGRESS_STORE[task_id] = {'status': 'completed', 'percent': 100, 'msg': 'Download Complete!'}
                        file_sz = os.path.getsize(file_path)
                        return {
                            'file_path': file_path,
                            'title': title[:150],
                            'duration': duration,
                            'thumbnail': thumb,
                            'filesize': file_sz,
                            'is_audio': False,
                            'quality': 'HD',
                            'ext': 'mp4'
                        }

    # 3. Try Facebook Direct Video/Audio API if applicable
    if any(x in target_url.lower() for x in ["facebook.com", "fb.watch", "fb.me", "fb.com"]):
        fb_info = extract_facebook_info(target_url)
        if fb_info and fb_info.get('video_url'):
            title = fb_info.get('title', 'Facebook Video')
            thumb = fb_info.get('thumbnail')
            duration = fb_info.get('duration', 0)
            vid_target = fb_info.get('hd_url') if quality in ['1080', 'HD'] else fb_info.get('sd_url') or fb_info.get('video_url')
            
            if is_audio:
                temp_vid = os.path.join(DOWNLOAD_DIR, f"fb_tmp_{uuid.uuid4().hex[:8]}.mp4")
                out_mp3 = os.path.join(DOWNLOAD_DIR, f"fb_audio_{uuid.uuid4().hex[:8]}.mp3")
                v_resp = requests.get(vid_target, headers=DEFAULT_HEADERS, timeout=35, stream=True)
                if v_resp.status_code == 200:
                    with open(temp_vid, "wb") as f:
                        for chunk in v_resp.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                    # Convert MP4 to MP3 via ffmpeg
                    subprocess.run(['ffmpeg', '-y', '-i', temp_vid, '-vn', '-ab', '320k', out_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if os.path.exists(temp_vid):
                        os.remove(temp_vid)
                    if os.path.exists(out_mp3):
                        if task_id:
                            PROGRESS_STORE[task_id] = {'status': 'completed', 'percent': 100, 'msg': 'Download Complete!'}
                        return {
                            'file_path': out_mp3,
                            'title': title[:150],
                            'duration': duration,
                            'thumbnail': thumb,
                            'filesize': os.path.getsize(out_mp3),
                            'is_audio': True,
                            'quality': '320kbps',
                            'ext': 'mp3'
                        }
            else:
                unique_name = f"fb_vid_{uuid.uuid4().hex[:8]}.mp4"
                file_path = os.path.join(DOWNLOAD_DIR, unique_name)
                v_resp = requests.get(vid_target, headers=DEFAULT_HEADERS, timeout=35, stream=True)
                if v_resp.status_code == 200:
                    total_bytes = int(v_resp.headers.get('content-length', 0))
                    downloaded = 0
                    with open(file_path, "wb") as f:
                        for chunk in v_resp.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if task_id and total_bytes > 0:
                                    pct = round((downloaded / total_bytes * 100), 1)
                                    PROGRESS_STORE[task_id] = {
                                        'status': 'downloading',
                                        'percent': pct,
                                        'downloaded_mb': round(downloaded / (1024*1024), 2),
                                        'total_mb': round(total_bytes / (1024*1024), 2),
                                        'msg': f"Downloading Facebook video {pct}%..."
                                    }
                    if task_id:
                        PROGRESS_STORE[task_id] = {'status': 'completed', 'percent': 100, 'msg': 'Download Complete!'}
                    return {
                        'file_path': file_path,
                        'title': title[:150],
                        'duration': duration,
                        'thumbnail': thumb,
                        'filesize': os.path.getsize(file_path),
                        'is_audio': False,
                        'quality': 'HD' if quality in ['1080', 'HD'] else 'SD',
                        'ext': 'mp4'
                    }

    COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
    temp_cookie = None
    
    # Progress hook callback
    def _progress_hook(d):
        if not task_id:
            return
        if d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes') or 0
            pct = round((downloaded / total * 100), 1) if total > 0 else 0
            spd = d.get('speed') or 0
            spd_str = f"{round(spd / (1024 * 1024), 2)} MB/s" if spd else ""
            eta = d.get('eta')
            eta_str = f"{eta}s" if eta else ""
            PROGRESS_STORE[task_id] = {
                'status': 'downloading',
                'percent': pct,
                'downloaded_mb': round(downloaded / (1024 * 1024), 2),
                'total_mb': round(total / (1024 * 1024), 2),
                'speed': spd_str,
                'eta': eta_str,
                'msg': f"Downloading {pct}% ({round(downloaded/(1024*1024), 1)} MB / {round(total/(1024*1024), 1)} MB)"
            }
        elif d.get('status') == 'finished':
            PROGRESS_STORE[task_id] = {
                'status': 'merging',
                'percent': 99,
                'downloaded_mb': round((d.get('total_bytes') or 0) / (1024 * 1024), 2),
                'total_mb': round((d.get('total_bytes') or 0) / (1024 * 1024), 2),
                'speed': '',
                'eta': '',
                'msg': 'Merging video & audio with FFmpeg...'
            }

    # 2. General yt-dlp extraction with Node.js and challenge solver for crisp 1080p
    file_prefix = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex[:8]}_%(epoch)s")
    if is_audio:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{file_prefix}.%(ext)s',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'js_runtimes': {'node': {}},
            'remote_components': ['ejs:github', 'ejs:npm'],
            'progress_hooks': [_progress_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
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
            'js_runtimes': {'node': {}},
            'remote_components': ['ejs:github', 'ejs:npm'],
            'progress_hooks': [_progress_hook],
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

            if task_id:
                PROGRESS_STORE[task_id] = {
                    'status': 'completed',
                    'percent': 100,
                    'downloaded_mb': round(file_size / (1024 * 1024), 2),
                    'total_mb': round(file_size / (1024 * 1024), 2),
                    'speed': '',
                    'eta': '',
                    'msg': '✅ Download Complete!'
                }

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
    
    # 1. Instagram extraction (GraphQL + HTML scraper)
    ig_match = re.search(r'instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)', target_url)
    if ig_match:
        shortcode = ig_match.group(1)
        ig_info = extract_instagram_post_info(target_url, shortcode)
        if ig_info:
            title = ig_info.get('title', title)
            photos = ig_info.get('photos') or ([ig_info.get('thumbnail')] if ig_info.get('thumbnail') else [])
            for i, img_url in enumerate(photos):
                try:
                    img_resp = requests.get(img_url, headers=DEFAULT_HEADERS, timeout=15)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1024:
                        filename = os.path.join(DOWNLOAD_DIR, f"ig_img_{shortcode}_{i+1}.jpg")
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

    # 2. TikTok Photo Album extraction
    if any(x in target_url.lower() for x in ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com"]):
        tt_info = extract_tiktok_info(target_url)
        if tt_info and tt_info.get('is_album') and tt_info.get('photos'):
            title = tt_info.get('title', title)
            photos = tt_info['photos']
            for i, img_url in enumerate(photos):
                try:
                    img_resp = requests.get(img_url, headers=DEFAULT_HEADERS, timeout=15)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1024:
                        filename = os.path.join(DOWNLOAD_DIR, f"tt_img_{uuid.uuid4().hex[:8]}_{i+1}.jpg")
                        with open(filename, "wb") as f:
                            f.write(img_resp.content)
                        downloaded_files.append(filename)
                except Exception as e:
                    logger.error(f"Error downloading TikTok photo {img_url}: {e}")
            if downloaded_files:
                return {
                    'image_paths': downloaded_files,
                    'title': title[:150],
                    'count': len(downloaded_files)
                }

    # 3. Facebook extraction using crawler User-Agent
    if any(x in target_url.lower() for x in ["facebook.com", "fb.watch", "fb.me", "fb.com"]):
        try:
            s = requests.Session()
            s.headers.update({
                'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            })
            r = s.get(target_url, allow_redirects=True, timeout=12)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                fb_images = []
                og_img = soup.find('meta', property='og:image')
                if og_img and og_img.get('content') and og_img['content'].startswith('http'):
                    fb_images.append(og_img['content'])
                
                for img in soup.find_all('img'):
                    src = img.get('src') or img.get('data-src')
                    if src and 'fbcdn.net' in src and not any(x in src for x in ['static.', 'rsrc.', 'emoji', 'icon', 'p50x50', 'p100x100']):
                        if src not in fb_images:
                            fb_images.append(src)
                
                if fb_images:
                    og_title = soup.find('meta', property='og:title')
                    if og_title and og_title.get('content'):
                        title = og_title['content']
                    elif soup.title:
                        title = soup.title.string or title
                    
                    for i, img_url in enumerate(fb_images[:20]):
                        try:
                            img_resp = s.get(img_url, timeout=12)
                            if img_resp.status_code == 200 and len(img_resp.content) > 10240:
                                ext = ".jpg"
                                if "png" in img_resp.headers.get("Content-Type", ""):
                                    ext = ".png"
                                elif "webp" in img_resp.headers.get("Content-Type", ""):
                                    ext = ".webp"
                                filename = os.path.join(DOWNLOAD_DIR, f"fb_img_{uuid.uuid4().hex[:8]}_{i+1}{ext}")
                                with open(filename, "wb") as f:
                                    f.write(img_resp.content)
                                downloaded_files.append(filename)
                        except Exception as e:
                            logger.error(f"Failed to download Facebook image: {e}")
                    
                    if downloaded_files:
                        return {
                            'image_paths': downloaded_files,
                            'title': title[:150],
                            'count': len(downloaded_files)
                        }
        except Exception as fb_err:
            logger.warning(f"Facebook direct image download error: {fb_err}")

    # 3. Try with yt-dlp
    try:
        unique_id = uuid.uuid4().hex[:8]
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, f"img_{unique_id}_%(autonumber)s.%(ext)s"),
            'noplaylist': False,
            'quiet': True,
            'no_warnings': True,
            'http_headers': DEFAULT_HEADERS,
            'js_runtimes': {'node': {}},
            'remote_components': ['ejs:github', 'ejs:npm'],
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

async def extract_media_info(url: str) -> Dict[str, Any]:
    """Async wrapper around extract_media_info_sync."""
    return await asyncio.to_thread(extract_media_info_sync, url)

async def download_media(url: str, is_audio: bool = False, quality: str = "720", task_id: Optional[str] = None) -> Dict[str, Any]:
    """Async wrapper around download_media_sync."""
    return await asyncio.to_thread(download_media_sync, url, is_audio, quality, task_id)

async def download_images(url: str) -> Dict[str, Any]:
    """Async wrapper around download_images_sync."""
    return await asyncio.to_thread(download_images_sync, url)

# ---------------------------------------------------------------------------
# Direct URL Extraction — No disk storage, browser downloads from CDN directly
# ---------------------------------------------------------------------------

# Platforms where a plain browser / Telegram can fetch the CDN URL directly without extra headers
DIRECT_REDIRECT_PLATFORMS = (
    "instagram.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "pinterest.com",
    "pin.it",
    "facebook.com",
    "fb.watch",
    "fb.me",
    "fb.com",
    "threads.net",
    "reddit.com",
    "vimeo.com",
)

def extract_direct_url_sync(url: str, quality: str = "720", is_audio: bool = False) -> Dict[str, Any]:
    """
    Extract the direct CDN media URL without downloading anything to disk.

    Returns a dict:
      {
        'mode':        'redirect' | 'stream' | 'images',
        'direct_url':  str | None,          # single video/audio URL
        'image_urls':  List[str] | None,    # for photo carousels
        'title':       str,
        'ext':         str,
        'filesize':    int | None,          # may be None if unknown
        'duration':    int | None,
        'headers':     dict,               # headers browser should send (empty for redirect)
        'error':       str | None,
      }
    """
    target_url = clean_url(url)
    url_lower = target_url.lower()

    # ------------------------------------------------------------------
    # 1. Instagram — GraphQL & HTML fallback (multi-photo carousel support)
    # ------------------------------------------------------------------
    ig_match = re.search(r'instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)', target_url)
    if ig_match:
        shortcode = ig_match.group(1)
        ig_info = extract_instagram_post_info(target_url, shortcode)
        if ig_info:
            title = ig_info.get('title', 'Instagram Post')
            if ig_info.get('is_album') and ig_info.get('photos'):
                return {
                    'mode': 'images',
                    'direct_url': None,
                    'image_urls': ig_info['photos'],
                    'title': title[:150],
                    'ext': 'jpg',
                    'filesize': None,
                    'duration': None,
                    'headers': {},
                    'error': None,
                }
            elif ig_info.get('thumbnail') and not ig_info.get('duration') and not is_audio:
                return {
                    'mode': 'redirect',
                    'direct_url': ig_info['thumbnail'],
                    'image_urls': [ig_info['thumbnail']],
                    'title': title[:150],
                    'ext': 'jpg',
                    'filesize': None,
                    'duration': None,
                    'headers': {},
                    'error': None,
                }

    # ------------------------------------------------------------------
    # 2. TikTok — Direct TikWM API (HD video, MP3 audio, Photo slideshow)
    # ------------------------------------------------------------------
    if any(x in url_lower for x in ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com"]):
        tt_info = extract_tiktok_info(target_url)
        if tt_info:
            title = tt_info.get('title', 'TikTok Media')
            if tt_info.get('is_album') and tt_info.get('photos'):
                return {
                    'mode': 'images',
                    'direct_url': None,
                    'image_urls': tt_info['photos'],
                    'title': title[:150],
                    'ext': 'jpg',
                    'filesize': None,
                    'duration': None,
                    'headers': {},
                    'error': None,
                }
            elif is_audio and tt_info.get('audio_url'):
                return {
                    'mode': 'redirect',
                    'direct_url': tt_info['audio_url'],
                    'image_urls': None,
                    'title': title[:150],
                    'ext': 'mp3',
                    'filesize': None,
                    'duration': tt_info.get('duration'),
                    'headers': {},
                    'error': None,
                }
            elif tt_info.get('video_url'):
                return {
                    'mode': 'redirect',
                    'direct_url': tt_info['video_url'],
                    'image_urls': None,
                    'title': title[:150],
                    'ext': 'mp4',
                    'filesize': None,
                    'duration': tt_info.get('duration'),
                    'headers': {},
                    'error': None,
                }

    # ------------------------------------------------------------------
    # 3. Facebook — Direct HD/SD Video & Photo extraction
    # ------------------------------------------------------------------
    if any(x in url_lower for x in ["facebook.com", "fb.watch", "fb.me", "fb.com"]):
        fb_info = extract_facebook_info(target_url)
        if fb_info:
            title = fb_info.get('title', 'Facebook Media')
            if fb_info.get('is_album') and fb_info.get('photos'):
                return {
                    'mode': 'images',
                    'direct_url': None,
                    'image_urls': fb_info['photos'],
                    'title': title[:150],
                    'ext': 'jpg',
                    'filesize': None,
                    'duration': None,
                    'headers': {},
                    'error': None,
                }
            elif fb_info.get('video_url'):
                vid_url = fb_info.get('hd_url') if quality in ['1080', 'HD'] else fb_info.get('sd_url') or fb_info.get('video_url')
                return {
                    'mode': 'redirect',
                    'direct_url': vid_url,
                    'image_urls': None,
                    'title': title[:150],
                    'ext': 'mp4',
                    'filesize': None,
                    'duration': fb_info.get('duration'),
                    'headers': {},
                    'error': None,
                }
            elif fb_info.get('photos'):
                return {
                    'mode': 'redirect',
                    'direct_url': fb_info['photos'][0],
                    'image_urls': fb_info['photos'],
                    'title': title[:150],
                    'ext': 'jpg',
                    'filesize': None,
                    'duration': None,
                    'headers': {},
                    'error': None,
                }

    # ------------------------------------------------------------------
    # 2. yt-dlp metadata extraction (no download) for all platforms
    # ------------------------------------------------------------------
    COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
    temp_cookie = None

    height = quality if quality in ["1080", "720", "480", "360"] else "720"
    if is_audio:
        fmt = "bestaudio/best"
    else:
        fmt = (
            f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/'
            f'bestvideo[height<={height}]+bestaudio/'
            f'best[height<={height}][ext=mp4]/'
            f'best[height<={height}]/'
            f'best'
        )

    ydl_opts = {
        'format': fmt,
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,   # ← key: metadata only, 0 bytes written to disk
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web', 'ios', 'mweb'],
            }
        },
    }

    if os.path.exists(COOKIE_FILE):
        temp_cookie = os.path.join(DOWNLOAD_DIR, f"dc_cookie_{uuid.uuid4().hex[:8]}.txt")
        shutil.copyfile(COOKIE_FILE, temp_cookie)
        ydl_opts['cookiefile'] = temp_cookie

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=False)

        if not info:
            return {'mode': 'stream', 'direct_url': None, 'image_urls': None,
                    'title': 'Media', 'ext': 'mp4', 'filesize': None, 'duration': None, 'headers': {}, 'error': 'No info extracted'}

        title = info.get('title', 'Media')
        duration = info.get('duration', 0)

        # Check if it's an image playlist / multi-image post
        entries = info.get('entries')
        if entries:
            # Multi-item playlist / album
            img_urls = []
            for entry in entries:
                if entry and entry.get('url'):
                    img_urls.append(entry.get('url'))
            if img_urls:
                return {
                    'mode': 'images',
                    'direct_url': None,
                    'image_urls': img_urls,
                    'title': title[:150],
                    'ext': 'jpg',
                    'filesize': None,
                    'duration': None,
                    'headers': {},
                    'error': None,
                }

        # Resolve the best format URL
        formats = info.get('formats') or []
        chosen = None

        if is_audio:
            # Pick best audio-only format
            audio_fmts = [f for f in formats if f.get('vcodec') == 'none' and f.get('url')]
            if audio_fmts:
                chosen = max(audio_fmts, key=lambda f: f.get('abr') or 0)
        else:
            # Pick best video format that fits requested height
            h = int(height)
            # Prioritize progressive formats (both audio and video in single stream) for direct CDN playback
            complete_video_fmts = [
                f for f in formats 
                if f.get('url') 
                and (f.get('height') or 0) <= h 
                and f.get('vcodec') != 'none' 
                and f.get('acodec') not in ('none', None)
            ]
            if complete_video_fmts:
                chosen = max(complete_video_fmts, key=lambda f: (f.get('height') or 0, f.get('tbr') or 0))
            else:
                video_fmts = [f for f in formats if f.get('url') and (f.get('height') or 0) <= h and f.get('vcodec') != 'none']
                if video_fmts:
                    chosen = max(video_fmts, key=lambda f: (f.get('height') or 0, f.get('tbr') or 0))

        # Fallback to top-level url
        direct_url = (chosen or {}).get('url') or info.get('url')
        ext = (chosen or {}).get('ext') or info.get('ext') or ('mp3' if is_audio else 'mp4')
        filesize = (chosen or {}).get('filesize') or info.get('filesize')
        http_headers = (chosen or {}).get('http_headers') or info.get('http_headers') or {}

        # Decide mode:
        # - Platforms where browser / Telegram can directly fetch the URL → redirect
        # - YouTube and others that need auth/special headers or audio merge → proxy stream
        is_direct_platform = any(p in url_lower for p in DIRECT_REDIRECT_PLATFORMS)
        
        # Check if video has separate audio that needs merge (e.g. YouTube DASH)
        has_audio = (chosen or {}).get('acodec') not in ('none', None) if chosen else True

        if is_direct_platform and direct_url and (is_audio or has_audio):
            mode = 'redirect'
        elif is_direct_platform and direct_url:
            mode = 'redirect'
        else:
            # YouTube or formats that need streaming
            mode = 'stream'

        return {
            'mode': mode,
            'direct_url': direct_url,
            'image_urls': None,
            'title': title[:150],
            'ext': ext,
            'filesize': filesize,
            'duration': int(duration) if duration else None,
            'headers': http_headers,
            'error': None,
        }

    except Exception as e:
        logger.error(f"extract_direct_url_sync error: {e}")
        return {
            'mode': 'stream',
            'direct_url': None,
            'image_urls': None,
            'title': 'Media',
            'ext': 'mp4',
            'filesize': None,
            'duration': None,
            'headers': {},
            'error': str(e)[:200],
        }
    finally:
        if temp_cookie and os.path.exists(temp_cookie):
            try:
                os.remove(temp_cookie)
            except Exception:
                pass


async def extract_direct_url(url: str, quality: str = "720", is_audio: bool = False) -> Dict[str, Any]:
    """Async wrapper around extract_direct_url_sync."""
    return await asyncio.to_thread(extract_direct_url_sync, url, quality, is_audio)


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
