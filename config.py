import os

# Bot configuration
API_ID = int(os.environ.get("API_ID", "20288994"))
API_HASH = os.environ.get("API_HASH", "d702614912f1ad370a0d18786002adbf")
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8314502536:AAFLGwBTzCXPxvBPC5oMIiSKVyDaY5sm5mY")

# Channel configuration
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1002995694885"))

# Redis configuration (for web interface)
REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "https://together-spaniel-13493.upstash.io")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "ATS1AAIncDJmMTE3M2ZmZGRjYTU0NGEwOGExODRjYTA2YjUwM2UwZnAyMTM0OTM")

# Web interface
BASE_URL = os.environ.get("BASE_URL", "https://filmzicloud.vercel.app")

# Bot settings
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
