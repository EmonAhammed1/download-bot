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
    check_profile_link,
    get_platform_name,
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

# Temporary in-memory cache for pending URLs per user/message
PENDING_URLS = {}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    first_name = html.escape(user.first_name if user and user.first_name else "ব্যবহারকারী")
    welcome_text = (
        f"👋 <b>স্বাগতম {first_name}!</b>\n\n"
        "✨ আমি একটি <b>Universal Media Downloader Bot</b>।\n"
        "যেকোনো ভিডিও, ফটো/পোস্ট বা অডিও ডাউনলোড করতে লিঙ্ক পাঠান।\n\n"
        "📥 <b>সমর্থিত প্ল্যাটফর্মসমূহ:</b>\n"
        "• 📸 <b>Instagram</b> (Reels, Posts, Carousel Photos, Stories)\n"
        "• 🔵 <b>Facebook</b> (Videos, Reels, Photo Posts)\n"
        "• 🔴 <b>YouTube</b> (Videos, Shorts, Music)\n"
        "• 🎵 <b>TikTok</b> (Without watermark)\n"
        "• 🐦 <b>Twitter / X</b>\n"
        "• 📌 <b>Pinterest</b>\n\n"
        "🚀 <b>ব্যবহার করার নিয়ম:</b>\n"
        "সরাসরি যেকোনো পোস্ট বা ভিডিওর লিঙ্ক এখানে মেসেজ হিসেবে পাঠিয়ে দিন!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👨‍💻 <b>Developed by Emon</b>"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "📖 <b>বট ব্যবহারের সহায়িকা:</b>\n\n"
        "১. যেকোনো ভিডিও, পোস্ট বা ফটোর লিঙ্ক কপি করুন।\n"
        "২. এখানে চ্যাটে পেস্ট করে সেন্ড করুন।\n"
        "৩. আপনার পছন্দের অপশন বেছে নিন:\n"
        "   - 🎬 <b>Video (1080p, 720p, 480p, 360p)</b>\n"
        "   - 🖼️ <b>Images (পোস্টের সব ছবি)</b>\n"
        "   - 🎵 <b>MP3 Audio</b>\n"
        "৪. বট ফাইলটি ডাউনলোড করে সরাসরি চ্যাটে পাঠিয়ে দেবে।"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detect and process incoming link from message."""
    text = update.message.text or update.message.caption or ""
    raw_url = extract_url(text)

    if not raw_url:
        await update.message.reply_text(
            "❌ কোনো সঠিক লিঙ্ক পাওয়া যায়নি। দয়া করে একটি সঠিক ভিডিও বা পোস্ট লিঙ্ক পাঠান।"
        )
        return

    url = clean_url(raw_url)

    # Check if the user sent a profile link instead of a post/reel
    profile_info = check_profile_link(url)
    if profile_info:
        platform_type, username = profile_info
        safe_username = html.escape(username)
        await update.message.reply_text(
            f"👤 <b>{platform_type} প্রোফাইল লিঙ্ক শনাক্ত হয়েছে:</b> <code>@{safe_username}</code>\n\n"
            f"⚠️ এটি একটি <b>ব্যবহারকারীর অ্যাকাউন্ট / প্রোফাইল লিঙ্ক</b> (কোনো নির্দিষ্ট পোস্ট বা রিলস নয়)।\n\n"
            f"💡 <b>কীভাবে ভিডিও বা ছবি ডাউনলোড করবেন:</b>\n"
            f"১. {platform_type} অ্যাপে যান।\n"
            f"২. যে <b>Reels (ভিডিও)</b> বা <b>Post (ছবি)</b> ডাউনলোড করতে চান, সেটিতে যান।\n"
            f"৩. <b>Share (শেয়ার)</b> আইকনে চাপ দিয়ে <b>Copy Link</b> চাপুন।\n"
            f"৪. সেই লিঙ্কটি এখানে পাঠালে বট সাথে সাথে সেটি ডাউনলোড করে দেবে!",
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
            InlineKeyboardButton("🎥 1080p (Full HD)", callback_data=f"vid_1080:{cache_key}"),
            InlineKeyboardButton("🎬 720p (HD)", callback_data=f"vid_720:{cache_key}"),
        ],
        [
            InlineKeyboardButton("📱 480p (SD)", callback_data=f"vid_480:{cache_key}"),
            InlineKeyboardButton("💾 360p (Saver)", callback_data=f"vid_360:{cache_key}"),
        ],
        [
            InlineKeyboardButton("🖼️ Images (সব ছবি)", callback_data=f"img_all:{cache_key}"),
            InlineKeyboardButton("🎵 MP3 Audio", callback_data=f"aud_mp3:{cache_key}"),
        ],
        [
            InlineKeyboardButton("❌ বাতিল করুন", callback_data=f"cancel:{cache_key}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    safe_url = html.escape(url)
    await update.message.reply_text(
        f"🔗 <b>শনাক্তকৃত লিঙ্ক:</b> {platform}\n"
        f"📎 <code>{safe_url}</code>\n\n"
        f"🎯 <b>ডাউনলোড অপশন নির্বাচন করুন:</b>",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback button clicks."""
    query = update.callback_query
    await query.answer()

    data = query.data
    action, cache_key = data.split(":", 1)

    if action == "cancel":
        PENDING_URLS.pop(cache_key, None)
        await query.edit_message_text("❌ ডাউনলোড বাতিল করা হয়েছে।")
        return

    url = PENDING_URLS.get(cache_key)
    if not url:
        await query.edit_message_text("⚠️ লিঙ্কের মেয়াদ শেষ হয়ে গেছে। দয়া করে আবার লিঙ্কটি পাঠান।")
        return

    # 1. Handle Images Download
    if action == "img_all":
        await query.edit_message_text("⏳ পোস্টের ছবিগুলো খোঁজা ও ডাউনলোড করা হচ্ছে...")
        downloaded_images = []
        open_files = []
        try:
            result = await download_images(url)
            downloaded_images = result.get('image_paths', [])
            title = result.get('title', 'Post Images')
            count = len(downloaded_images)

            if not downloaded_images or count == 0:
                await query.edit_message_text(
                    "❌ এই পোস্টে কোনো ডাউনলোডযোগ্য ছবি পাওয়া যায়নি।\n"
                    "এটি যদি একটি ভিডিও হয়, তবে ভিডিও অপশন সিলেক্ট করুন।"
                )
                return

            await query.edit_message_text(f"📤 {count}টি ছবি টেলিগ্রামে আপলোড হচ্ছে...")
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_PHOTO)

            bot_info = await context.bot.get_me()
            bot_username = bot_info.username if bot_info and bot_info.username else "MediaBot"
            title_safe = html.escape(title[:150])
            caption = f"🖼️ <b>{title_safe}</b>\n\n📸 মোট ছবি: <b>{count}টি</b>\n✨ @{bot_username}"

            if count == 1:
                # Send single photo
                f = open(downloaded_images[0], 'rb')
                open_files.append(f)
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=f,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    read_timeout=300,
                    write_timeout=300
                )
            else:
                # Telegram hard limit: Max 10 photos per media group.
                # Split evenly (e.g. 14 photos -> 7 + 7) for a balanced layout.
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
                            parse_mode=ParseMode.HTML,
                            read_timeout=300,
                            write_timeout=300
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
                            media=media_group,
                            read_timeout=300,
                            write_timeout=300
                        )

            await query.delete_message()

        except Exception as e:
            logger.error(f"Error handling images: {e}", exc_info=True)
            err_msg = html.escape(str(e)[:200])
            await query.edit_message_text(
                f"❌ ত্রুটি হয়েছে: <code>{err_msg}</code>\n\n"
                "দয়া করে নিশ্চিত করুন লিঙ্কটি পাবলিক ও অ্যাক্সেসযোগ্য।",
                parse_mode=ParseMode.HTML
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

    # 2. Handle Video or Audio Download
    if action.startswith("vid_"):
        quality = action.split("_")[1]
        is_audio = False
        status_text = f"⏳ ভিডিও ({quality}p) ডাউনলোড হচ্ছে..."
    else:
        quality = "MP3"
        is_audio = True
        status_text = "⏳ অডিও কনভার্ট ও ডাউনলোড হচ্ছে..."
    
    await query.edit_message_text(f"{status_text}\nদয়া করে কিছুক্ষণ অপেক্ষা করুন...")

    file_path = None
    try:
        # Download media with chosen quality
        result = await download_media(url, is_audio=is_audio, quality=quality)
        file_path = result.get('file_path')
        title = result.get('title', 'Media')
        duration = result.get('duration') or 0
        filesize = result.get('filesize', 0)
        ext = result.get('ext', 'mp4')

        if not file_path or not os.path.exists(file_path):
            await query.edit_message_text("❌ ফাইলটি ডাউনলোড করা সম্ভব হয়নি। লিঙ্কটি প্রাইভেট বা অবৈধ হতে পারে।")
            return

        if filesize > MAX_FILE_SIZE:
            size_mb = round(filesize / (1024 * 1024), 2)
            retry_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🎬 720p HD", callback_data=f"vid_720:{cache_key}"),
                    InlineKeyboardButton("🎬 480p", callback_data=f"vid_480:{cache_key}"),
                    InlineKeyboardButton("🎬 360p", callback_data=f"vid_360:{cache_key}"),
                ],
                [
                    InlineKeyboardButton("🎵 MP3 Audio (অডিও)", callback_data=f"aud_mp3:{cache_key}"),
                ]
            ])
            await query.edit_message_text(
                f"⚠️ <b>ফাইল সাইজ বেশি বড় ({size_mb} MB)!</b>\n\n"
                f"টেলিগ্রাম বটের লিমিট সর্বোচ্চ <b>50 MB</b>।\n"
                f"💡 দয়া করে কম রেজোলিউশন (যেমন: 720p, 480p বা 360p) নির্বাচন করুন:",
                reply_markup=retry_keyboard,
                parse_mode=ParseMode.HTML
            )
            # Keep cache_key in PENDING_URLS so retry buttons work
            if file_path:
                cleanup_file(file_path)
            return

        # Notify user that upload started
        await query.edit_message_text("📤 টেলিগ্রামে আপলোড হচ্ছে... দয়া করে অপেক্ষা করুন।")

        quality_label = "MP3 Audio" if is_audio else f"{quality}p HD"
        title_safe = html.escape(title[:200])
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username if bot_info and bot_info.username else "MediaBot"
        caption = f"🎬 <b>{title_safe}</b>\n\n📊 কোয়ালিটি: <b>{quality_label}</b>\n✨ @{bot_username}"

        if is_audio:
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_VOICE)
            with open(file_path, 'rb') as f:
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=f,
                    title=title,
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
            f"❌ ত্রুটি হয়েছে: <code>{err_msg}</code>\n\n"
            "দয়া করে নিশ্চিত করুন লিঙ্কটি পাবলিক ও অ্যাক্সেসযোগ্য।",
            parse_mode=ParseMode.HTML
        )
        PENDING_URLS.pop(cache_key, None)
    finally:
        # Always clean up local storage
        if file_path:
            cleanup_file(file_path)

def main():
    """Start the bot."""
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("Error: BOT_TOKEN is missing in config.py!")
        return

    print("Media Downloader Bot is starting...")
    
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

    print("Media Downloader Bot is running and ready for messages!")
    app.run_polling()

if __name__ == "__main__":
    main()
