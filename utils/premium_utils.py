# utils/premium_utils.py
from datetime import datetime, timedelta
from database import premium_users

def _get_timedelta(value: int, unit: str) -> timedelta:
    u = unit.lower()
    if u in ("min", "minute", "minutes"):
        return timedelta(minutes=value)
    if u in ("hour", "hours"):
        return timedelta(hours=value)
    if u in ("day", "days"):
        return timedelta(days=value)
    if u in ("week", "weeks"):
        return timedelta(weeks=value)
    if u in ("month", "months"):
        return timedelta(days=30 * value)
    if u in ("year", "years"):
        return timedelta(days=365 * value)
    if u in ("decade", "decades"):
        return timedelta(days=365 * 10 * value)
    return timedelta(days=value)

def add_premium_user(user_id: int, duration_value: int, duration_unit: str):
    try:
        delta = _get_timedelta(duration_value, duration_unit)
        now = datetime.utcnow()
        doc = premium_users.find_one({"user_id": user_id})
        if doc and doc.get("expiry"):
            try:
                curr = datetime.fromisoformat(doc["expiry"])
            except Exception:
                curr = now
            new_expiry = curr + delta if curr > now else now + delta
        else:
            new_expiry = now + delta
        premium_users.update_one({"user_id": user_id},
                                 {"$set": {"user_id": user_id, "expiry": new_expiry.isoformat()}},
                                 upsert=True)
        return True, new_expiry
    except Exception as e:
        return False, str(e)

def remove_premium_user(user_id: int):
    try:
        premium_users.delete_one({"user_id": user_id})
        return True, None
    except Exception as e:
        return False, str(e)

def is_premium_user(user_id: int) -> bool:
    doc = premium_users.find_one({"user_id": user_id})
    if not doc:
        return False
    expiry = doc.get("expiry")
    if not expiry:
        return False
    try:
        expiry_dt = datetime.fromisoformat(expiry)
    except Exception:
        return False
    return expiry_dt > datetime.utcnow()

def get_premium_expiry(user_id: int):
    doc = premium_users.find_one({"user_id": user_id})
    if not doc:
        return None
    try:
        return datetime.fromisoformat(doc.get("expiry"))
    except Exception:
        return None

def list_premium_users(limit=1000):
    cursor = premium_users.find().sort("expiry", -1).limit(limit)
    return [{"user_id": d.get("user_id"), "expiry": d.get("expiry")} for d in cursor]

def transfer_premium(from_user: int, to_user: int):
    try:
        now = datetime.utcnow()
        src = premium_users.find_one({"user_id": from_user})
        if not src or not src.get("expiry"):
            return False, "You do not have an active premium plan to transfer."
        try:
            src_expiry = datetime.fromisoformat(src["expiry"])
        except Exception:
            return False, "Source expiry parse error."
        if src_expiry <= now:
            return False, "Your premium has already expired."
        remaining = src_expiry - now
        tgt = premium_users.find_one({"user_id": to_user})
        if tgt and tgt.get("expiry"):
            try:
                tgt_expiry_dt = datetime.fromisoformat(tgt["expiry"])
            except Exception:
                tgt_expiry_dt = now
        else:
            tgt_expiry_dt = now
        new_tgt_expiry = max(tgt_expiry_dt, now) + remaining
        premium_users.update_one(
            {"user_id": to_user},
            {"$set": {"user_id": to_user, "expiry": new_tgt_expiry.isoformat()}},
            upsert=True
        )
        premium_users.delete_one({"user_id": from_user})
        return True, new_tgt_expiry
    except Exception as e:
        return False, str(e)
