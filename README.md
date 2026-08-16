# 🎬 Universal Media Downloader Telegram Bot

An advanced, high-performance Telegram Bot built with Python that allows users to download videos, audio (MP3), photo albums, and carousels from all major social media platforms.

---

## 🌟 Supported Platforms & Features

| Platform | Supported Content | Available Qualities |
| :--- | :--- | :--- |
| 🔴 **YouTube** | Videos, Shorts, Music | 1080p (FHD), 720p (HD), 480p, 360p, MP3 Audio (192kbps) |
| 📸 **Instagram** | Reels, Video Posts, Multi-Image Carousels, Photos | Full HD 1080p, Direct Video MP4, High-Res Image Albums |
| 🔵 **Facebook** | Videos, Reels, Public Photo Posts | HD MP4, SD, MP3 Audio, High-Res Images |
| 🎵 **TikTok** | Videos without watermark, Audio | HD MP4, MP3 |
| 🐦 **Twitter / X** | Videos, Photos, GIFs | Best Quality MP4 / JPG |
| 📌 **Pinterest** | Videos, High-Resolution Pins | Best Quality MP4 / JPG |

---

## 📁 Repository Structure & Architecture

```
download-bot/
├── bot.py                  # Main Telegram Bot logic & message/callback handlers
├── downloader.py           # Core media extraction engine (yt-dlp, Instagram GraphQL API, BS4)
├── config.py               # Bot token configuration and file size limits
├── deploy.py               # 1-Click Auto-Sync to GitHub and Deploy to VPS via SSH/SFTP
├── deploy.bat              # Windows batch script for 1-click deployment
├── requirements.txt        # Python package dependencies
├── Dockerfile              # Docker container configuration with FFmpeg & Python 3.11
├── Procfile                # Worker process file for cloud platforms (Render, Heroku)
├── .gitignore              # Ignores temp downloads, __pycache__, and venvs
└── .github/
    └── workflows/
        └── deploy.yml      # GitHub Actions CI/CD pipeline for automated VPS deployment
```

---

## 🧠 Key Technical Highlights

1. **Instagram GraphQL Direct Integration:**
   - Bypasses traditional `yt-dlp` scraping bottlenecks for Instagram multi-photo carousels and posts by directly querying Instagram's official GraphQL document endpoints.
   - Extracts all carousel images in original full-resolution (up to 14+ photos).

2. **Smart Balanced Media Groups:**
   - Telegram Bot API enforces a hard limit of max 10 photos per `sendMediaGroup`.
   - The bot dynamically splits photo albums evenly (e.g., 14 photos are split into 7 + 7 balanced albums) so images render in a clean, symmetric grid.

3. **Extended HTTP Request Timeouts:**
   - Configured with custom `HTTPXRequest` (300s read/write timeouts) to prevent `Timed out` errors when uploading large video/audio files (10MB - 50MB) to Telegram.

4. **Crash-Proof HTML Parsing:**
   - All dynamic titles, user names, and descriptions are escaped with `html.escape` and rendered using `ParseMode.HTML` to prevent entity parse errors from special characters, emojis, and hashtags.

5. **Automatic File Cleanup:**
   - Temporary files downloaded to the local `downloads/` directory are immediately deleted after being dispatched to Telegram, ensuring zero disk bloat.

---

## 💻 Local Development & Setup

### Prerequisites
- Python 3.10+
- FFmpeg installed and added to system PATH

### Installation
```bash
# Clone the repository
git clone https://github.com/EmonAhammed1/download-bot.git
cd download-bot

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running Locally
```bash
python bot.py
```

---

## 🚀 VPS Deployment & Infrastructure

The bot is actively hosted on an Ubuntu VPS with `systemd` process management:

- **Server IP:** `72.244.153.23`
- **Application Directory:** `/opt/media-downloader-bot`
- **Virtual Environment:** `/opt/media-downloader-bot/venv`
- **Systemd Service:** `media-downloader-bot.service`

### VPS Service Management Commands
```bash
# Check status
systemctl status media-downloader-bot

# View live real-time logs
journalctl -u media-downloader-bot -f

# Restart bot
systemctl restart media-downloader-bot

# Stop bot
systemctl stop media-downloader-bot
```

---

## 🔄 1-Click Sync & Deployment Workflow

Whenever you make changes to the codebase, run:

```bash
python deploy.py "Your commit message"
```
Or simply double-click `deploy.bat` on Windows.

**What this does automatically:**
1. Stages and commits all changes.
2. Pushes commits to GitHub `origin main`.
3. Connects to the VPS via SSH / SFTP.
4. Uploads the updated Python files to `/opt/media-downloader-bot`.
5. Restarts `media-downloader-bot.service` on the server in ~3 seconds.

---

## 🤖 Instructions for Future AI Agents & Developers

When extending or maintaining this codebase:
- **State Management & Async:** The bot runs asynchronously with `python-telegram-bot` v20+. Always wrap synchronous operations (like `yt-dlp` or file I/O) in `asyncio.to_thread`.
- **Parsing Mode:** Always use `ParseMode.HTML` and wrap dynamic strings in `html.escape()`. Never use legacy Markdown.
- **File Limits:** Keep Telegram Bot API's 50MB file size limit in mind; if a file exceeds `MAX_FILE_SIZE`, alert the user and offer a lower resolution.
- **Service Isolation:** When deploying on the VPS, never touch global packages or system services. Keep all operations confined to `/opt/media-downloader-bot` and `media-downloader-bot.service`.
