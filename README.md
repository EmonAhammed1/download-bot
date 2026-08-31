# 🚀 Universal Media Downloader — Web App & Telegram Bot

<p align="center">
  <a href="https://download.emonahammed.shop/"><img src="https://img.shields.io/badge/🌐_Live_Website-download.emonahammed.shop-00d2ff?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Live Web App"></a>
  <a href="https://t.me/my1_assistant_demo_bot"><img src="https://img.shields.io/badge/🤖_Telegram_Bot-@my1__assistant__demo__bot-229ED9?style=for-the-badge&logo=telegram&logoColor=white" alt="Telegram Bot"></a>
  <a href="https://emonahammed.shop/"><img src="https://img.shields.io/badge/👨‍💻_Developer-Emon_Ahammed-ff007f?style=for-the-badge&logo=safari&logoColor=white" alt="Developer Portfolio"></a>
  <br>
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/yt--dlp-Latest-red?style=flat-square&logo=youtube&logoColor=white" alt="yt-dlp">
  <img src="https://img.shields.io/badge/FFmpeg-Enabled-green?style=flat-square&logo=ffmpeg&logoColor=white" alt="FFmpeg">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker">
</p>

An ultra-fast, high-performance universal media extraction ecosystem available as both a **Retro-Modern Web Application** and an **Automated Telegram Bot**. Download 4K / 1080p videos, 320kbps MP3 audio, multi-image carousels, reels, and stories with zero watermark and maximum speed from all major platforms.

---

## 🔗 Quick Access Links

| Platform | Live Access Link | Description |
| :--- | :--- | :--- |
| 🌐 **Web Application** | [**https://download.emonahammed.shop/**](https://download.emonahammed.shop/) | Instant browser download with quality picker & live CDN streaming |
| 🤖 **Telegram Bot** | [**@my1_assistant_demo_bot**](https://t.me/my1_assistant_demo_bot) | Direct Telegram downloads with inline keyboards & album splitting |
| 👨‍💻 **Developer Portfolio** | [**emonahammed.shop**](https://emonahammed.shop/) | Created & maintained by Emon Ahammed |

---

## 🌟 Supported Platforms & Formats

| Platform | Supported Content | Available Qualities & Formats |
| :--- | :--- | :--- |
| 🔴 **YouTube** | Videos, Shorts, Music Tracks | 1080p (FHD), 720p (HD), 480p, 360p, MP3 Audio (320kbps / 192kbps) |
| 📸 **Instagram** | Reels, Video Posts, Multi-Image Carousels, Stories, Photos | 1080p Direct MP4, High-Res Original JPGs, Multi-Photo Galleries |
| 🔵 **Facebook** | Public Videos, Reels, Watch Videos, High-Res Photos | HD MP4, SD MP4, High-Bitrate MP3 Audio, Full JPGs |
| 🎵 **TikTok** | Videos without Watermark, Audio Only | Crystal-clear HD MP4 (No Watermark), MP3 |
| 🐦 **Twitter / X** | Videos, Photos, Animated GIFs | Best Quality MP4 / JPG |
| 📌 **Pinterest** | Video Pins, High-Resolution Graphic Pins | Best Quality MP4 / High-Res JPG |

---

## ⚡ Dual-Interface Ecosystem

### 1. 🌐 Modern Web Application (`web_app.py`)
- **Retro-Brutalist & Cyber Aesthetic UI:** Responsive layout with micro-animations and intuitive format selectors.
- **Direct CDN Streaming & Proxy Engine:** Zero server disk consumption for YouTube, Instagram, Facebook, and TikTok streaming.
- **Single & Multi-Image Gallery:** Dynamic grid rendering for Instagram carousel posts with individual and batch downloads.
- **Real-Time Client Feedback:** Visual loading indicators, status cards, and download triggers.

### 2. 🤖 Automated Telegram Bot (`bot.py`)
- **Interactive Inline Keyboards:** Instant resolution selection (1080p, 720p, 480p, MP3) with 1-tap callbacks.
- **Smart Balanced Media Groups:** Automatically balances photo albums (e.g. 14 photos split into 7 + 7) adhering to Telegram's 10-media limit.
- **Resilient Network Timeouts:** Custom 300s `HTTPXRequest` handlers prevent timeout disconnects when dispatching 50MB files.
- **Auto-Cleanup:** Immediate deletion of temporary downloads post-upload to maintain a clean filesystem.

---

## 📁 Repository Structure

```
download-bot/
├── bot.py                  # Telegram Bot service (python-telegram-bot v20+)
├── web_app.py              # FastAPI Web Application & streaming endpoints
├── downloader.py           # Core extraction engine (yt-dlp, Instagram GraphQL API, BS4)
├── config.py               # Shared configuration & file size thresholds
├── templates/
│   └── index.html          # Web application UI template
├── static/
│   ├── css/
│   │   └── style.css       # Retro-brutalist custom styling
│   ├── js/
│   │   └── app.js          # Dynamic UI interactions & download pipeline
│   └── img/                # Logos, favicons & assets
├── deploy.py               # 1-Click Git push & SSH/SFTP deploy to VPS
├── deploy.bat              # Windows 1-click batch launcher
├── requirements.txt        # Python package dependencies
├── Dockerfile              # Container definition (Python 3.11 + FFmpeg + Deno)
├── docker-compose.yml      # Multi-service container orchestration
└── .github/
    └── workflows/
        └── deploy.yml      # CI/CD deployment workflow
```

---

## 🧠 Key Technical Highlights

1. **Instagram GraphQL Direct Integration:**
   Bypasses typical scraping limits for Instagram carousels by directly querying Instagram's official GraphQL endpoints to retrieve full-resolution original media.

2. **Zero-Disk Proxy Streaming:**
   Pipes media streams from source CDNs directly to client browsers using `httpx` chunk streaming, preventing high I/O disk bottlenecks on the VPS.

3. **Crash-Proof HTML Sanitization:**
   Escapes all dynamic metadata and titles with `html.escape` to ensure error-free rendering in Telegram's HTML parse mode and Web DOM.

4. **1-Click Auto-Deploy Pipeline:**
   Full synchronization pipeline via `deploy.py` that pushes code to GitHub and updates both systemd services on the production VPS in under 5 seconds.

---

## 💻 Local Development & Setup

### Prerequisites
- Python 3.10+
- FFmpeg installed and available in system `PATH`

### Installation
```bash
# Clone the repository
git clone https://github.com/EmonAhammed1/download-bot.git
cd download-bot

# Create and activate virtual environment
python -m venv venv

# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running Locally

**To run the Web Application:**
```bash
python web_app.py
# Web app will be accessible at http://localhost:8000
```

**To run the Telegram Bot:**
```bash
python bot.py
```

**To run both using Docker:**
```bash
docker-compose up -d --build
```

---

## 🚀 VPS Production Deployment

Both the Web App and Telegram Bot run on an Ubuntu VPS managed via `systemd`:

- **Server IP:** `72.244.153.23`
- **Web App URL:** [https://download.emonahammed.shop/](https://download.emonahammed.shop/) (Reverse Proxied to Port 8000)
- **Telegram Bot:** [@my1_assistant_demo_bot](https://t.me/my1_assistant_demo_bot)
- **Application Directory:** `/opt/media-downloader-bot`

### VPS Service Management Commands

```bash
# Check status of both services
systemctl status media-downloader-web
systemctl status media-downloader-bot

# View live real-time logs
journalctl -u media-downloader-web -f
journalctl -u media-downloader-bot -f

# Restart services
systemctl restart media-downloader-web
systemctl restart media-downloader-bot
```

---

## 🔄 1-Click Sync & Deployment Workflow

Whenever updates are made locally, run:

```bash
python deploy.py "Your commit message"
```
Or double-click `deploy.bat` on Windows.

**Automated actions performed:**
1. Stages and commits all changes in Git.
2. Pushes commits to GitHub `origin main`.
3. Connects to VPS via SSH / SFTP.
4. Uploads all modified code, templates, and static assets.
5. Restarts `media-downloader-web` and `media-downloader-bot` services instantly.

---

## 👨‍💻 Author & Maintainer

- **Developer:** Emon Ahammed
- **Portfolio:** [https://emonahammed.shop/](https://emonahammed.shop/)
- **GitHub:** [@EmonAhammed1](https://github.com/EmonAhammed1)

