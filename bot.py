import os
import sys
import html
import logging
import asyncio

# Ensure UTF-8 output encoding for Windows terminal
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ChatAction, ParseMode
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN, MAX_FILE_SIZE
from downloader import (
    extract_url,
    clean_url,
    clean_media_title,
    check_profile_link,
    get_platform_name,
    extract_direct_url,
    download_media,
    download_images,
    cleanup_file,
    cleanup_files,
)

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def debugPrint(msg: str):
    """User rule #11: Debug print in terminal for every action and response."""
    print(f"\n[DEBUG 🤖 BOT] {msg}", flush=True)

# Temporary in-memory cache for pending URLs per user/message
PENDING_URLS = {}

WEBSITE_URL = "https://download.emonahammed.shop/"
PORTFOLIO_URL = "https://emonahammed.shop/"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with stylish Universal Downloader branding."""
    user = update.effective_user
    first_name = html.escape(user.first_name if user and user.first_name else "User")
    debugPrint(f"/start command from user: {user.id if user else 'unknown'} ({first_name})")
    
    welcome_text = (
        f"⚡ <b>UNIVERSAL DOWNLOADER</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👋 <b>Welcome, {first_name}!</b>\n\n"
        f"High-speed media engine to download 4K videos, 320kbps MP3 audio, and photo albums with zero limits.\n\n"
        f"📥 <b>Supported Platforms:</b>\n"
        f"• 📸 <b>Instagram</b> — Reels, Posts, Carousels, Stories\n"
        f"• 🔵 <b>Facebook</b> — Reels, Videos, Watch, Posts\n"
        f"• 🔴 <b>YouTube</b> — Videos, Shorts, Music\n"
        f"• 🎵 <b>TikTok</b> — HD without watermark\n"
        f"• 🐦 <b>Twitter / X</b> — Clips, Media\n"
        f"• 📌 <b>Pinterest</b> — Videos, High-Res Pins\n\n"
        f"🚀 <b>How to Download:</b>\n"
        f"Simply copy & send any video or post link here!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Web App:</b> <a href=\"{WEBSITE_URL}\">Universal Downloader Web</a>\n"
        f"👨‍💻 <b>Developer:</b> <a href=\"{PORTFOLIO_URL}\">Emon Ahammed</a>"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("🌐 Open Web App", url=WEBSITE_URL),
            InlineKeyboardButton("👨‍💻 Developer Portfolio", url=PORTFOLIO_URL),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    debugPrint("Help command received")
    help_text = (
        f"⚡ <b>UNIVERSAL DOWNLOADER — HELP GUIDE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"1. <b>Copy Link:</b> Copy the link of any video, reel, or photo post.\n"
        f"2. <b>Send Link:</b> Paste and send the link in this chat.\n"
        f"3. <b>Select Format:</b> Choose your preferred quality:\n"
        f"   • 🎬 <b>1080p FHD / 720p HD</b> (High Definition Video)\n"
        f"   • 📱 <b>480p SD / 360p Fast</b> (Data Saver)\n"
        f"   • 🖼️ <b>All Photos</b> (Carousel & Album Extraction)\n"
        f"   • 🎵 <b>320kbps MP3</b> (High-Fidelity Audio)\n\n"
        f"🌐 <b>Website:</b> <a href=\"{WEBSITE_URL}\">{WEBSITE_URL}</a>\n"
        f"⚡ Fast direct streaming engine delivers media directly to your chat without delay."
    )
    keyboard = [
        [
            InlineKeyboardButton("🌐 Open Web App", url=WEBSITE_URL),
        ]
    ]
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detect and process incoming link from message."""
    text = update.message.text or update.message.caption or ""
    debugPrint(f"Message received: {text[:80]}")
    raw_url = extract_url(text)

    if not raw_url:
        debugPrint("No valid URL found in message")
        await update.message.reply_text(
            f"❌ <b>No valid link found!</b>\n\n"
            f"Please send a valid video, reel, or post URL.\n"
            f"🌐 Or download directly via our <a href=\"{WEBSITE_URL}\">Web App</a>.",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        return

    url = clean_url(raw_url)
    debugPrint(f"Cleaned URL: {url}")

    # Check if the user sent a profile link instead of a post/reel
    profile_info = check_profile_link(url)
    if profile_info:
        platform_type, username = profile_info
        safe_username = html.escape(username)
        debugPrint(f"Profile link detected: {platform_type} @{username}")
        await update.message.reply_text(
            f"👤 <b>{platform_type} Profile Link Detected:</b> <code>@{safe_username}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ This is a <b>user profile link</b>, not a specific video or post.\n\n"
            f"💡 <b>How to download media:</b>\n"
            f"1. Open the {platform_type} app.\n"
            f"2. Go to the specific <b>Reel, Video, or Photo Post</b> you want.\n"
            f"3. Tap <b>Share ➔ Copy Link</b>.\n"
            f"4. Send that link here to download instantly!",
            parse_mode=ParseMode.HTML
        )
        return

    platform = get_platform_name(url)
    user_id = update.effective_user.id
    msg_id = update.message.message_id
    cache_key = f"{user_id}_{msg_id}"
    PENDING_URLS[cache_key] = url

    keyboard = [
        [
            InlineKeyboardButton("🎬 1080p Full HD", callback_data=f"vid_1080:{cache_key}"),
            InlineKeyboardButton("🎬 720p HD", callback_data=f"vid_720:{cache_key}"),
        ],
        [
            InlineKeyboardButton("📱 480p SD", callback_data=f"vid_480:{cache_key}"),
            InlineKeyboardButton("💾 360p Fast", callback_data=f"vid_360:{cache_key}"),
        ],
        [
            InlineKeyboardButton("🖼️ All Photos", callback_data=f"img_all:{cache_key}"),
            InlineKeyboardButton("🎵 320kbps MP3", callback_data=f"aud_mp3:{cache_key}"),
        ],
        [
            InlineKeyboardButton("🌐 Open in Web App", url=WEBSITE_URL),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{cache_key}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    safe_url = html.escape(url)
    debugPrint(f"Sent format options for platform: {platform}")
    await update.message.reply_text(
        f"⚡ <b>UNIVERSAL DOWNLOADER</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ <b>Platform:</b> {platform}\n"
        f"📎 <code>{safe_url}</code>\n\n"
        f"🎯 <b>Select Quality to Download:</b>",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback button clicks."""
    query = update.callback_query
    await query.answer()

    data = query.data
    action, cache_key = data.split(":", 1)
    debugPrint(f"Button clicked: action={action} | cache_key={cache_key}")

    if action == "cancel":
        PENDING_URLS.pop(cache_key, None)
        await query.edit_message_text("❌ <b>Download cancelled.</b>", parse_mode=ParseMode.HTML)
        return

    url = PENDING_URLS.get(cache_key)
    if not url:
        await query.edit_message_text("⚠️ <b>Session expired.</b> Please send the link again.", parse_mode=ParseMode.HTML)
        return

    bot_info = await context.bot.get_me()
    bot_username = bot_info.username if bot_info and bot_info.username else "UniversalDownloader"

    # =========================================================================
    # 1. Handle Images Download (Direct CDN URL first -> Fallback to VPS)
    # =========================================================================
    if action == "img_all":
        await query.edit_message_text("⏳ <b>Fetching post images...</b> Please wait.", parse_mode=ParseMode.HTML)
        debugPrint(f"Handling images for {url}")
        
        # Step A: Try direct CDN image URLs first (Zero VPS Disk Usage)
        try:
            direct_data = await extract_direct_url(url)
            image_urls = direct_data.get('image_urls') or []
            if not image_urls and direct_data.get('mode') == 'redirect' and direct_data.get('ext') in ['jpg', 'jpeg', 'png', 'webp']:
                image_urls = [direct_data.get('direct_url')]

            if image_urls:
                count = len(image_urls)
                debugPrint(f"DIRECT SEND: Found {count} direct image URLs. Sending to Telegram...")
                raw_title = direct_data.get('title', 'Post Images')
                clean_title = clean_media_title(raw_title)
                title_safe = html.escape(clean_title[:150])
                caption = (
                    f"⚡ <b>UNIVERSAL DOWNLOADER</b>\n"
                    f"🖼️ <b>{title_safe}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📸 Total Photos: <b>{count}</b>\n"
                    f"🌐 <b>Web App:</b> <a href=\"{WEBSITE_URL}\">Universal Downloader</a>\n"
                    f"👨‍💻 <b>Author:</b> <a href=\"{PORTFOLIO_URL}\">Emon Ahammed</a>\n"
                    f"✨ @{bot_username}"
                )

                download_btn = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("⚡ Direct HD Photo", url=image_urls[0]),
                        InlineKeyboardButton("🌐 Web App", url=WEBSITE_URL)
                    ]
                ])

                if count == 1:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=image_urls[0],
                        caption=caption,
                        reply_markup=download_btn,
                        parse_mode=ParseMode.HTML
                    )
                else:
                    # Send media groups using direct image URLs
                    num_groups = (count + 9) // 10
                    k, m = divmod(count, num_groups)
                    chunks = []
                    start = 0
                    for i in range(num_groups):
                        size = k + (1 if i < m else 0)
                        chunks.append(image_urls[start:start + size])
                        start += size

                    for chunk_idx, chunk in enumerate(chunks):
                        if len(chunk) == 1:
                            await context.bot.send_photo(
                                chat_id=query.message.chat_id,
                                photo=chunk[0],
                                caption=caption if chunk_idx == 0 else None,
                                parse_mode=ParseMode.HTML
                            )
                        else:
                            media_group = [
                                InputMediaPhoto(media=u, caption=caption if chunk_idx == 0 and idx == 0 else None, parse_mode=ParseMode.HTML)
                                for idx, u in enumerate(chunk)
                            ]
                            await context.bot.send_media_group(
                                chat_id=query.message.chat_id,
                                media=media_group
                            )

                await query.delete_message()
                PENDING_URLS.pop(cache_key, None)
                debugPrint("DIRECT SEND SUCCESS: All images delivered via direct CDN URLs.")
                return

        except Exception as direct_err:
            logger.warning(f"Direct image send attempt failed ({direct_err}), falling back to local downloader...")
            debugPrint(f"Direct image attempt failed: {direct_err}. Trying fallback...")

        # Step B: Fallback to local download on VPS if direct CDN fetch fails
        downloaded_images = []
        open_files = []
        try:
            result = await download_images(url)
            downloaded_images = result.get('image_paths', [])
            raw_title = result.get('title', 'Post Images')
            clean_title = clean_media_title(raw_title)
            count = len(downloaded_images)

            if not downloaded_images or count == 0:
                await query.edit_message_text(
                    f"❌ <b>No downloadable photos found in this post.</b>\n\n"
                    f"If this post is a video, please select a video quality option.\n"
                    f"🌐 Or try on our <a href=\"{WEBSITE_URL}\">Web App</a>.",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
                return

            await query.edit_message_text(f"📤 <b>Uploading {count} photo(s) to Telegram...</b>", parse_mode=ParseMode.HTML)
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_PHOTO)

            title_safe = html.escape(clean_title[:150])
            caption = (
                f"⚡ <b>UNIVERSAL DOWNLOADER</b>\n"
                f"🖼️ <b>{title_safe}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📸 Total Photos: <b>{count}</b>\n"
                f"🌐 <b>Web App:</b> <a href=\"{WEBSITE_URL}\">Universal Downloader</a>\n"
                f"👨‍💻 <b>Author:</b> <a href=\"{PORTFOLIO_URL}\">Emon Ahammed</a>\n"
                f"✨ @{bot_username}"
            )

            if count == 1:
                f = open(downloaded_images[0], 'rb')
                open_files.append(f)
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=f,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
            else:
                num_groups = (count + 9) // 10
                k, m = divmod(count, num_groups)
                chunks = []
                start = 0
                for i in range(num_groups):
                    size = k + (1 if i < m else 0)
                    chunks.append(downloaded_images[start:start + size])
                    start += size
                
                for chunk_idx, chunk in enumerate(chunks):
                    if len(chunk) == 1:
                        f = open(chunk[0], 'rb')
                        open_files.append(f)
                        await context.bot.send_photo(
                            chat_id=query.message.chat_id,
                            photo=f,
                            caption=caption if chunk_idx == 0 else None,
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        media_group = []
                        for idx, path in enumerate(chunk):
                            f = open(path, 'rb')
                            open_files.append(f)
                            if chunk_idx == 0 and idx == 0:
                                media_group.append(InputMediaPhoto(media=f, caption=caption, parse_mode=ParseMode.HTML))
                            else:
                                media_group.append(InputMediaPhoto(media=f))

                        await context.bot.send_media_group(
                            chat_id=query.message.chat_id,
                            media=media_group
                        )

            await query.delete_message()

        except Exception as e:
            logger.error(f"Error handling images: {e}", exc_info=True)
            err_msg = html.escape(str(e)[:200])
            await query.edit_message_text(
                f"❌ <b>Error occurred:</b> <code>{err_msg}</code>\n\n"
                f"Please make sure the post is public and accessible.\n"
                f"🌐 Web App: <a href=\"{WEBSITE_URL}\">{WEBSITE_URL}</a>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        finally:
            for f in open_files:
                try:
                    f.close()
                except Exception:
                    pass
            if downloaded_images:
                cleanup_files(downloaded_images)
            PENDING_URLS.pop(cache_key, None)
        return

    # =========================================================================
    # 2. Handle Video or Audio Download (Direct CDN URL first -> Fallback to VPS)
    # =========================================================================
    if action.startswith("vid_"):
        quality = action.split("_")[1]
        is_audio = False
        status_text = f"⏳ <b>Loading video ({quality}p)...</b>"
        quality_label = f"{quality}p HD"
    else:
        quality = "MP3"
        is_audio = True
        status_text = "⏳ <b>Extracting 320kbps MP3 audio...</b>"
        quality_label = "320kbps MP3 Audio"
    
    await query.edit_message_text(f"{status_text}\nPlease wait a moment...", parse_mode=ParseMode.HTML)
    debugPrint(f"Handling media: quality={quality}, is_audio={is_audio}, url={url}")

    # -------------------------------------------------------------------------
    # STEP 1: Try Direct CDN URL (Zero VPS Disk & Bandwidth Usage)
    # -------------------------------------------------------------------------
    try:
        direct_info = await extract_direct_url(url, quality=quality, is_audio=is_audio)
        direct_url = direct_info.get('direct_url')
        mode = direct_info.get('mode')
        raw_title = direct_info.get('title', 'Media')
        clean_title = clean_media_title(raw_title)
        duration = direct_info.get('duration') or 0
        ext = direct_info.get('ext', 'mp4')

        if direct_url and (mode == 'redirect' or not is_audio):
            debugPrint(f"DIRECT SEND: Found direct URL {direct_url[:80]}. Sending directly to Telegram...")
            title_safe = html.escape(clean_title[:200])
            caption = (
                f"⚡ <b>UNIVERSAL DOWNLOADER</b>\n"
                f"🎬 <b>{title_safe}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>Quality:</b> {quality_label}\n"
                f"🌐 <b>Web App:</b> <a href=\"{WEBSITE_URL}\">Universal Downloader</a>\n"
                f"👨‍💻 <b>Author:</b> <a href=\"{PORTFOLIO_URL}\">Emon Ahammed</a>\n"
                f"✨ @{bot_username}"
            )

            direct_btn = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⚡ Direct High-Speed Download", url=direct_url),
                    InlineKeyboardButton("🌐 Web App", url=WEBSITE_URL)
                ]
            ])

            if is_audio:
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=direct_url,
                    title=clean_title,
                    duration=int(duration) if duration else None,
                    caption=caption,
                    reply_markup=direct_btn,
                    parse_mode=ParseMode.HTML
                )
            elif ext in ['jpg', 'jpeg', 'png', 'webp']:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=direct_url,
                    caption=caption,
                    reply_markup=direct_btn,
                    parse_mode=ParseMode.HTML
                )
            else:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=direct_url,
                    duration=int(duration) if duration else None,
                    caption=caption,
                    supports_streaming=True,
                    reply_markup=direct_btn,
                    parse_mode=ParseMode.HTML
                )

            await query.delete_message()
            PENDING_URLS.pop(cache_key, None)
            debugPrint("DIRECT SEND SUCCESS: Media sent directly without touching VPS disk!")
            return

    except Exception as direct_err:
        logger.warning(f"Direct media send failed ({direct_err}), falling back to VPS downloader...")
        debugPrint(f"Direct send attempt failed: {direct_err}. Falling back to VPS downloader...")

    # -------------------------------------------------------------------------
    # STEP 2: Fallback to VPS Download (Only when direct CDN fetch is impossible)
    # -------------------------------------------------------------------------
    file_path = None
    try:
        result = await download_media(url, is_audio=is_audio, quality=quality)
        file_path = result.get('file_path')
        raw_title = result.get('title', 'Media')
        clean_title = clean_media_title(raw_title)
        duration = result.get('duration') or 0
        filesize = result.get('filesize', 0)
        ext = result.get('ext', 'mp4')

        if not file_path or not os.path.exists(file_path):
            await query.edit_message_text(
                f"❌ <b>Could not download media.</b>\n"
                f"The link might be private, expired, or unsupported.\n"
                f"🌐 Try on our Web App: <a href=\"{WEBSITE_URL}\">{WEBSITE_URL}</a>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            return

        if filesize > MAX_FILE_SIZE:
            size_mb = round(filesize / (1024 * 1024), 2)
            retry_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🎬 720p HD", callback_data=f"vid_720:{cache_key}"),
                    InlineKeyboardButton("📱 480p SD", callback_data=f"vid_480:{cache_key}"),
                    InlineKeyboardButton("💾 360p Fast", callback_data=f"vid_360:{cache_key}"),
                ],
                [
                    InlineKeyboardButton("🎵 320kbps MP3", callback_data=f"aud_mp3:{cache_key}"),
                ],
                [
                    InlineKeyboardButton("🌐 Download via Web App (No Limits)", url=WEBSITE_URL),
                ]
            ])
            await query.edit_message_text(
                f"⚠️ <b>File Exceeds Telegram Bot Limit ({size_mb} MB)!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Telegram bot upload limit is <b>50 MB</b>.\n\n"
                f"💡 <b>No Size Limit on Web App:</b> You can download this in full 4K / original resolution on our Web App:\n"
                f"👉 <a href=\"{WEBSITE_URL}\">Universal Downloader Web</a>",
                reply_markup=retry_keyboard,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            if file_path:
                cleanup_file(file_path)
            return

        # Notify user that upload started
        await query.edit_message_text("📤 <b>Uploading media to Telegram...</b> Please wait.", parse_mode=ParseMode.HTML)

        title_safe = html.escape(clean_title[:200])
        caption = (
            f"⚡ <b>UNIVERSAL DOWNLOADER</b>\n"
            f"🎬 <b>{title_safe}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Quality:</b> {quality_label}\n"
            f"🌐 <b>Web App:</b> <a href=\"{WEBSITE_URL}\">Universal Downloader</a>\n"
            f"👨‍💻 <b>Author:</b> <a href=\"{PORTFOLIO_URL}\">Emon Ahammed</a>\n"
            f"✨ @{bot_username}"
        )

        if is_audio:
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_VOICE)
            with open(file_path, 'rb') as f:
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=f,
                    title=clean_title,
                    duration=int(duration),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    read_timeout=300,
                    write_timeout=300
                )
        elif ext in ['jpg', 'jpeg', 'png', 'webp']:
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_PHOTO)
            with open(file_path, 'rb') as f:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=f,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    read_timeout=300,
                    write_timeout=300
                )
        else:
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_VIDEO)
            with open(file_path, 'rb') as f:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=f,
                    duration=int(duration),
                    caption=caption,
                    supports_streaming=True,
                    parse_mode=ParseMode.HTML,
                    read_timeout=300,
                    write_timeout=300
                )

        # Cleanup status message
        await query.delete_message()
        PENDING_URLS.pop(cache_key, None)

    except Exception as e:
        logger.error(f"Error handling media: {e}", exc_info=True)
        err_msg = html.escape(str(e)[:200])
        await query.edit_message_text(
            f"❌ <b>Error occurred:</b> <code>{err_msg}</code>\n\n"
            f"Please make sure the link is public and valid.\n"
            f"🌐 Web App: <a href=\"{WEBSITE_URL}\">{WEBSITE_URL}</a>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        PENDING_URLS.pop(cache_key, None)
    finally:
        # Always clean up local storage immediately
        if file_path:
            cleanup_file(file_path)

def main():
    """Start the bot."""
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("Error: BOT_TOKEN is missing in config.py!")
        return

    print("Universal Downloader Bot is starting...")
    
    # Configure custom HTTP request with extended timeouts for large media uploads
    request_config = HTTPXRequest(
        connection_pool_size=16,
        connect_timeout=60.0,
        read_timeout=300.0,
        write_timeout=300.0,
        pool_timeout=60.0
    )

    app = ApplicationBuilder().token(BOT_TOKEN).request(request_config).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_button))

    print("Universal Downloader Bot is running and ready for messages!")
    app.run_polling()

if __name__ == "__main__":
    main()
