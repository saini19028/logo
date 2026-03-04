# utils/settings_utils.py
from database import user_settings, image_settings

def set_user_defaults(user_id, watermark=None, link=None, size=None, color=None, alpha=None, position=None):
    update_data = {}
    if watermark is not None:
        update_data["default_watermark"] = watermark
    if link is not None:
        update_data["default_link"] = link
    if size is not None:
        update_data["default_wm_size"] = size
    if color is not None:
        update_data["default_wm_color"] = color
    if alpha is not None:
        update_data["default_wm_alpha"] = alpha
    if position is not None:
        update_data["default_wm_position"] = position
    
    user_settings.update_one(
        {"user_id": user_id},
        {"$set": update_data},
        upsert=True
    )

def get_user_defaults(user_id):
    doc = user_settings.find_one({"user_id": user_id})
    if doc:
        return {
            "default_watermark": doc.get("default_watermark"),
            "default_link": doc.get("default_link"),
            "default_wm_size": doc.get("default_wm_size"),
            "default_wm_color": doc.get("default_wm_color"),
            "default_wm_alpha": doc.get("default_wm_alpha", 0.18),
            "default_wm_position": doc.get("default_wm_position", "center")
        }
    return None

def set_image_settings(user_id, **kwargs):
    """Set multiple image settings at once"""
    image_settings.update_one(
        {"user_id": user_id},
        {"$set": kwargs},
        upsert=True
    )

def get_image_settings(user_id):
    """Get all image settings for a user"""
    doc = image_settings.find_one({"user_id": user_id})
    if doc:
        return {
            'size_factor': doc.get('size_factor', 1.0),
            'color': doc.get('color', [255, 255, 255]),
            'position': doc.get('position', 'bottom_right'),
            'alpha': doc.get('alpha', 220),  # 0-255
            'font_key': doc.get('font_key', 'sans_default'),
            'transform': doc.get('transform', 'normal'),
            'default_text': doc.get('default_text')
        }
    # Return default settings
    return {
        'size_factor': 1.0,
        'color': [255, 255, 255],
        'position': 'bottom_right',
        'alpha': 220,
        'font_key': 'sans_default',
        'transform': 'normal',
        'default_text': None
    }

def update_image_setting(user_id, key, value):
    """Update a single image setting"""
    image_settings.update_one(
        {"user_id": user_id},
        {"$set": {key: value}},
        upsert=True
    )
