import os

# Telegram Bot Token
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8842921041:AAGtey7a6i4ZdGi_nMW0MnJ8dE7VYUhAjXU")

# Maximum supported download size (500 MB)
MAX_FILE_SIZE = 500 * 1024 * 1024

# Telegram Bot API single file upload limit
TELEGRAM_UPLOAD_LIMIT = 49 * 1024 * 1024
