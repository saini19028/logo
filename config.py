# config.py - Complete configuration for PDF + Image Watermark Bot
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ========== TELEGRAM BOT CONFIGURATION ==========
# Telegram API credentials (from https://my.telegram.org)
API_ID = int(os.getenv("API_ID", "24861505"))
API_HASH = os.getenv("API_HASH", "fad28c88a18f4f2d9c67c2c08c19696f")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8701333510:AAFMfb6Owe1QAXIuPBoEz_IXAIXnFTqRl6M")



# ========== BOT OWNER CONFIGURATION ==========
# Bot Owner(s) - comma separated user IDs
# Example: "1469762885,1234567890"
OWNER_IDS = os.getenv("OWNER_ID", "1469762885")
OWNER_ID = [int(x.strip()) for x in OWNER_IDS.split(",") if x.strip()]

# Owner contact info for users
OWNER_CONTACT = os.getenv("OWNER_CONTACT", "**@kuldeep_saini19**")

# ========== DATABASE CONFIGURATION ==========
# MongoDB connection string
# Format: mongodb+srv://username:password@cluster.mongodb.net/dbname?retryWrites=true&w=majority
MONGO_URL = os.getenv("MONGODB_URL", os.getenv("MONGO_URL", "mongodb+srv://akjvjgeyblcoyj_db_user:FrEcy4r55q1IFTFI@cluster0.tag7eyl.mongodb.net/?appName=Cluster0"))

# ========== CHANNEL CONFIGURATION ==========
# Channel for storing processed files (must be public or bot must be admin)
#CHANNEL_STORE_ID = int(os.getenv("CHANNEL_STORE_ID", "-1003420207967"))

# Channel IDs for storing files
ORIGINAL_STORE_CHANNEL = int(os.getenv("ORIGINAL_STORE_CHANNEL", "-1003420207967"))  # For original user files
PROCESSED_STORE_CHANNEL = int(os.getenv("PROCESSED_STORE_CHANNEL", "-1003555007605"))  # For bot processed files


# Channel for force subscription (optional)
#CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")
#CHANNEL_ID = int(os.getenv("CHANNEL_ID", ""))  # Force-subscribe channel ID

# Force subscription invite link (optional)
#FORCE_SUB_URL = os.getenv("FORCE_SUB_URL", "")
#FORCE_PHOTO_URL = os.getenv("FORCE_PHOTO_URL", "https://files.catbox.moe/wqop01.jpg")

# ========== SERVER CONFIGURATION ==========
# Flask port (for web server)
PORT = int(os.getenv("PORT", "8080"))

# ========== DEFAULT VALUES ==========
# Default watermark text for PDFs
DEFAULT_WATERMARK = os.getenv("DEFAULT_WATERMARK", "@RPSC_RSMSSB_BOARD")

# Default link for PDFs
DEFAULT_LINK = os.getenv("DEFAULT_LINK", "https://t.me/+SY1QomaeCk44MjY1")

# Default font file for PDF watermarking
FONT_FILE = os.getenv("FONT_FILE", "TTF (5).ttf")

# ========== IMAGE WATERMARK DEFAULTS ==========
# Timeout for image watermark text input (seconds)
IMAGE_TIMEOUT = int(os.getenv("IMAGE_TIMEOUT", "20"))

# ========== VALIDATION ==========
# Validate required variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required! Please set it in .env file")

if not MONGO_URL:
    raise ValueError("MONGODB_URL/MONGO_URL is required! Please set it in .env file")

if not OWNER_ID:
    print("⚠️ WARNING: OWNER_ID is not set. Some admin features may not work.")

# ========== LOGGING CONFIGURATION ==========
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ========== ADVANCED SETTINGS ==========
# Prompt TTL for subscription check (seconds)
#PROMPT_TTL_SECONDS = int(os.getenv("PROMPT_TTL_SECONDS", "300"))

# Maximum file size for processing (in bytes, 20MB default)
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "2097152000"))

# Enable/disable auto-processing of PDFs
AUTO_PROCESS_PDFS = os.getenv("AUTO_PROCESS_PDFS", "true").lower() == "true"

# ========== PRINT CONFIG (for debugging) ==========
def print_config():
    """Print current configuration (without sensitive data)"""
    print("=" * 50)
    print("Bot Configuration:")
    print("=" * 50)
    print(f"API_ID: {API_ID}")
    print(f"API_HASH: {'*' * len(API_HASH) if API_HASH else 'Not set'}")
    print(f"BOT_TOKEN: {'Set' if BOT_TOKEN else 'NOT SET!'}")
    print(f"OWNER_ID: {OWNER_ID}")
    print(f"OWNER_CONTACT: {OWNER_CONTACT}")
    print(f"MONGO_URL: {'Set' if MONGO_URL else 'NOT SET!'}")
    print(f"PORT: {PORT}")
    print(f"CHANNEL_USERNAME: {CHANNEL_USERNAME}")
    print(f"CHANNEL_ID: {CHANNEL_ID}")
    print(f"CHANNEL_STORE_ID: {CHANNEL_STORE_ID}")
    print(f"DEFAULT_WATERMARK: {DEFAULT_WATERMARK}")
    print(f"DEFAULT_LINK: {DEFAULT_LINK}")
    print(f"IMAGE_TIMEOUT: {IMAGE_TIMEOUT} seconds")
    print(f"AUTO_PROCESS_PDFS: {AUTO_PROCESS_PDFS}")
    print("=" * 50)

# Print config when module is loaded
if __name__ == "__main__":
    print_config()
