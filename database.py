from pymongo import MongoClient
from config import MONGO_URL

client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
try:
    db = client.get_database()
except Exception:
    db = client["pdfbot"]

# collections
premium_users = db["premium_users"]        # { user_id, expiry (ISO str) }
user_settings = db["user_settings"]        # { user_id, default_watermark, default_link, default_wm_size, default_wm_color }
users = db["users"]                        # { user_id, first_seen, last_seen, subscribed }
image_pending = db["image_pending"]        # For image watermark pending states

# ✅ ADD THIS (VERY IMPORTANT)
image_settings = db["image_settings"]      # { user_id, size_factor, color, position, alpha, font_key, transform, default_text }

# ensure indexes
try:
    premium_users.create_index("user_id", unique=True)
    user_settings.create_index("user_id", unique=True)
    users.create_index("user_id", unique=True)
    image_pending.create_index("user_id", unique=True)
    image_pending.create_index(
        "created_at",
        expireAfterSeconds=300  # Auto delete after 5 mins
    )
    image_settings.create_index("user_id", unique=True)
except Exception:
    pass
