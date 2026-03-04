# utils/settings_utils.py – add these functions

def get_logo_defaults(user_id):
    """Return logo watermark settings for a user."""
    doc = user_settings.find_one({"user_id": user_id})
    if not doc:
        return {
            "size_factor": 0.2,
            "position": "bottom_right",
            "alpha": 0.8
        }
    return {
        "size_factor": doc.get("default_logo_size", 0.2),
        "position": doc.get("default_logo_position", "bottom_right"),
        "alpha": doc.get("default_logo_alpha", 0.8)
    }

def set_logo_defaults(user_id, size=None, position=None, alpha=None):
    """Update logo watermark defaults for a user."""
    update = {}
    if size is not None:
        update["default_logo_size"] = size
    if position is not None:
        update["default_logo_position"] = position
    if alpha is not None:
        update["default_logo_alpha"] = max(0.0, min(1.0, alpha))
    if update:
        user_settings.update_one(
            {"user_id": user_id},
            {"$set": update},
            upsert=True
        )
    return True
