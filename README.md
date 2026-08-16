# 🎬 Universal Media Downloader Telegram Bot

একটি শক্তিশালী টেলিগ্রাম বট যা দিয়ে ব্যবহারকারীরা বিভিন্ন সোশ্যাল মিডিয়ার লিঙ্ক পাঠিয়ে ভিডিও, ইমেজ এবং অডিও (MP3) ডাউনলোড করতে পারবেন।

## 🌟 সমর্থিত প্ল্যাটফর্মসমূহ
- 🔴 **YouTube** (Videos, Shorts, Music)
- 📸 **Instagram** (Reels, Posts, IGTV, Photos)
- 🔵 **Facebook** (Videos, Reels)
- 🎵 **TikTok** (Without watermark)
- 🐦 **Twitter / X**
- 📌 **Pinterest**

## 🚀 লোকালি চালানোর নিয়ম

### ১. লাইব্রেরি ইনস্টল করুন
```bash
pip install -r requirements.txt
```

### ২. বট চালান
```bash
python bot.py
```

## ⚙️ কনফিগারেশন
`config.py` ফাইলে আপনার টেলিগ্রাম বটের টোকেন যুক্ত করা রয়েছে। আপনি চাইলে পরিবেশ চলক (Environment Variable) হিসেবেও টোকেন সেট করতে পারেন:
```bash
set BOT_TOKEN=your_telegram_bot_token
python bot.py
```

## ☁️ ২৪/৭ ক্লাউডে হোস্ট করার নিয়ম (Free Deployment)
1. GitHub-এ এই প্রজেক্ট পুশ করুন।
2. [Render.com](https://render.com) এ লগইন করে **New Background Worker** সিলেক্ট করুন।
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python bot.py`
5. Environment Variable হিসেবে `BOT_TOKEN` সেট করে ডিপ্লয় করুন।
