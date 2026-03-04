# main.py — Complete working bot with all features (in‑place editing + fixed logo transparency)
import os
import io
import shutil
import threading
import time
import pyromod
import logging
import asyncio
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, Message
from pyrogram.errors import ListenerTimeout, QueryIdInvalid
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, ArrayObject
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import Color, HexColor
from datetime import timedelta, datetime
from pymongo import ReturnDocument
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# --- Your project modules ---
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID, PORT, ORIGINAL_STORE_CHANNEL, PROCESSED_STORE_CHANNEL, DEFAULT_WATERMARK, DEFAULT_LINK, FONT_FILE, IMAGE_TIMEOUT
from utils.premium_utils import (
    is_premium_user, add_premium_user, remove_premium_user,
    get_premium_expiry, list_premium_users, transfer_premium
)
from utils.settings_utils import (
    set_user_defaults, get_user_defaults,
    set_image_settings, get_image_settings, update_image_setting,
    get_logo_defaults, set_logo_defaults
)
from utils.image_utils import create_image_watermark
from utils.merge_utils import merge_pdfs
from utils.split_utils import split_pdf_by_pages, split_pdf_equal_parts
from database import users, user_settings, premium_users

# ---------- Logging ----------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
log = logging.getLogger(__name__)

# ---------- Flask (uptime) ----------
web_app = Flask(__name__)
@web_app.route("/")
def home():
    return "✅ PDF & Image Watermark Bot is running!"

def run_flask():
    web_app.run(host="0.0.0.0", port=PORT)

# ---------- Constants ----------
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB maximum file size
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for download

# ---------- PDF helpers ----------
def pdf_add_link(src, out, link):
    try:
        # Stream the PDF reading and writing
        rd = PdfReader(open(src, 'rb'))
        wr = PdfWriter()
        
        for i, p in enumerate(rd.pages):
            if "/Annots" in p:
                p[NameObject("/Annots")] = ArrayObject()
            w = float(p.mediabox.width)
            h = float(p.mediabox.height)
            wr.add_page(p)
            try:
                wr.add_uri(page_number=i, uri=link, rect=(0, 0, w, h), border=None)
            except Exception:
                pass
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(out)) or '.', exist_ok=True)
        with open(out, "wb") as f:
            wr.write(f)
        return True
    except Exception as e:
        log.exception(f"pdf_add_link error: {e}")
        try:
            # Ensure output directory exists before copying
            os.makedirs(os.path.dirname(os.path.abspath(out)) or '.', exist_ok=True)
            shutil.copy(src, out)
            return False
        except Exception as copy_error:
            log.error(f"Failed to copy file: {copy_error}")
            return False

def _apply_fill_color(c, color_name):
    try:
        colors = {
            "gray": (0.5, 0.5, 0.5),
            "red": (1, 0, 0),
            "blue": (0, 0, 1),
            "black": (0, 0, 0),
            "white": (1, 1, 1),
            "green": (0, 1, 0),
            "yellow": (1, 1, 0)
        }
        rgb = colors.get(color_name, (0, 0, 0))
        c.setFillColorRGB(*rgb)
    except Exception:
        pass

def pdf_watermark(
    src,
    out,
    text,
    font=FONT_FILE,
    size_override=None,
    color_override=None,
    alpha_override=None,
    position_override=None
):
    try:
        font_path = os.path.join(".", font)
        if os.path.isfile(font_path):
            pdfmetrics.registerFont(TTFont("WmFont", font_path))
        else:
            pdfmetrics.registerFont(TTFont("WmFont", font))

        rd = PdfReader(src)
        wr = PdfWriter()

        for page in rd.pages:
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)

            size = size_override or max(20, min(min(w, h) / 4, 108))

            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=(w, h))
            c.setFont("WmFont", size)
            
            # Apply color
            if color_override:
                _apply_fill_color(c, color_override)
            else:
                c.setFillColorRGB(0.5, 0.5, 0.5)  # Default gray

            # Apply transparency
            alpha = alpha_override if alpha_override is not None else 0.18
            if hasattr(c, "setFillAlpha"):
                c.setFillAlpha(alpha)

            # Get position
            position = position_override or "center"
            margin = 50
            
            # Calculate text width for alignment
            text_width = c.stringWidth(text, "WmFont", size)
            
            if position == "top_left":
                x = margin
                y = h - margin
                c.drawString(x, y, text)
            elif position == "top_right":
                x = w - margin - text_width
                y = h - margin
                c.drawString(x, y, text)
            elif position == "bottom_left":
                x = margin
                y = margin
                c.drawString(x, y, text)
            elif position == "bottom_right":
                x = w - margin - text_width
                y = margin
                c.drawString(x, y, text)
            elif position == "center":
                x = w / 2
                y = h / 2
                c.drawCentredString(x, y, text)
            elif position == "diag_tl_br":
                # Diagonal from Top-Left to Bottom-Right - NO MIRROR
                c.saveState()
                c.translate(w/2, h/2)
                c.rotate(45)  # Simple 45 degree rotation
                c.drawCentredString(0, 0, text)
                c.restoreState()
            elif position == "diag_bl_tr":
                # Diagonal from Bottom-Left to Top-Right - NO MIRROR
                c.saveState()
                c.translate(w/2, h/2)
                c.rotate(-45)  # Simple -45 degree rotation
                c.drawCentredString(0, 0, text)
                c.restoreState()
            else:
                # Default to center
                x = w / 2
                y = h / 2
                c.drawCentredString(x, y, text)
            
            c.save()
            packet.seek(0)
            overlay_page = PdfReader(packet).pages[0]

            # ✅ SAFE MERGE
            page.merge_page(overlay_page)
            wr.add_page(page)

        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "wb") as f:
            wr.write(f)

        return True

    except Exception as e:
        log.exception(f"pdf_watermark error: {e}")
        try:
            shutil.copy(src, out)
            return False
        except:
            return False

# ---------- PDF Logo Watermark Engine (FIXED transparency, no BytesIO error) ----------
def pdf_logo_watermark(
    src,
    out,
    logo_path,
    size_factor=None,
    position_override=None,
    alpha_override=None
):
    """
    Add a logo image as a watermark to every page of a PDF.
    - size_factor: fraction of page width (e.g., 0.2 = 20% of width)
    - position_override: e.g., 'bottom_right', 'center'
    - alpha_override: float 0.0 (transparent) to 1.0 (opaque)
    """
    try:
        from PIL import Image

        # Load logo and convert to RGBA (to handle alpha)
        logo_img = Image.open(logo_path).convert("RGBA")
        logo_width, logo_height = logo_img.size

        # Apply user alpha if given (0.0-1.0)
        if alpha_override is not None:
            # Split channels
            r, g, b, a = logo_img.split()
            # Multiply alpha by user alpha
            a = a.point(lambda p: int(p * alpha_override))
            logo_img = Image.merge("RGBA", (r, g, b, a))

        rd = PdfReader(src)
        wr = PdfWriter()

        for page in rd.pages:
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)

            # Scale logo based on page width and user factor
            factor = size_factor if size_factor is not None else 0.2
            target_width = w * factor
            target_height = logo_height * (target_width / logo_width)

            # Ensure it doesn't exceed page height
            if target_height > h:
                target_height = h * 0.8
                target_width = logo_width * (target_height / logo_height)

            # Create overlay PDF with the logo
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=(w, h))

            # Determine position
            position = position_override or "bottom_right"
            margin = 50
            if position == "top_left":
                x = margin
                y = h - margin - target_height
            elif position == "top_right":
                x = w - margin - target_width
                y = h - margin - target_height
            elif position == "bottom_left":
                x = margin
                y = margin
            elif position == "bottom_right":
                x = w - margin - target_width
                y = margin
            elif position == "center":
                x = (w - target_width) / 2
                y = (h - target_height) / 2
            else:
                x = (w - target_width) / 2
                y = (h - target_height) / 2

            # Draw the PIL image directly (preserves transparency)
            c.drawInlineImage(logo_img, x, y, width=target_width, height=target_height)
            c.save()

            packet.seek(0)
            overlay_page = PdfReader(packet).pages[0]
            page.merge_page(overlay_page)
            wr.add_page(page)

        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "wb") as f:
            wr.write(f)
        return True

    except Exception as e:
        log.exception(f"pdf_logo_watermark error: {e}")
        try:
            shutil.copy(src, out)
            return False
        except:
            return False

# ---------- Pyrogram client ----------
app = Client("pdfbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=4, max_concurrent_transmissions=2)

# ---------- Set Bot Commands ----------
async def set_bot_commands():
    try:
        commands = [
            BotCommand("start", "Start the bot"),
            BotCommand("pdf", "Add watermark & link to PDF (Premium)"),
            BotCommand("link", "Add only link to PDF (Premium)"),
            BotCommand("watermark", "Add only watermark to PDF (Premium)"),
            BotCommand("logo", "Add logo watermark to PDF (Premium)"),
            BotCommand("image", "Add watermark to image (Premium)"),
            BotCommand("settings", "Configure PDF settings"),
            BotCommand("image_settings", "Configure image watermark settings"),
            BotCommand("logo_settings", "Configure logo watermark settings"),
            BotCommand("myplan", "Check your premium status"),
            BotCommand("contact_owner", "Contact bot owner"),
            BotCommand("merge", "Merge multiple PDFs (Premium)"),
            BotCommand("split", "Split PDF into parts (Premium)"),
            BotCommand("add", "Add premium to user (Owner only)"),
            BotCommand("remove", "Remove premium from user (Owner only)"),
            BotCommand("check", "Check user premium status (Owner only)"),
            BotCommand("all_users", "List all users (Owner only)"),
            BotCommand("premium_list", "List all premium users (Owner only)"),
            BotCommand("broadcast", "Broadcast to premium users (Owner only)"),
            BotCommand("broadcast_all", "Broadcast to all users (Owner only)"),
            BotCommand("stats", "Show bot statistics (Owner only)"),
            BotCommand("help", "Show help message")
        ]
        await app.set_bot_commands(commands)
        log.info("Bot commands set successfully!")
    except Exception as e:
        log.error(f"Error setting bot commands: {e}")

# ---------- Send Restart Message to Owner Only ----------
async def send_restart_message():
    try:
        for owner_id in OWNER_ID:
            try:
                await app.send_message(owner_id, "✅ Bot has been restarted successfully!")
                await asyncio.sleep(0.1)
            except Exception:
                continue
        log.info("Restart message sent to owner(s)")
    except Exception as e:
        log.error(f"Error sending restart messages: {e}")

# ---------- Keyboards ----------
def keyboard_main_for_premium():
    kb = [
        [InlineKeyboardButton("🖼️ Image Watermark", callback_data="cmd_image_watermark")],
        [InlineKeyboardButton("🔹 PDF Watermark & Link", callback_data="cmd_start")],
        [InlineKeyboardButton("🔗 PDF Only Link", callback_data="cmd_link"), 
         InlineKeyboardButton("🖋️ PDF Only Watermark", callback_data="cmd_watermark")],
        [InlineKeyboardButton("🖼️ PDF Logo Watermark", callback_data="cmd_logo_watermark")],
        [InlineKeyboardButton("⚙️ Image Settings", callback_data="cmd_image_settings"), 
         InlineKeyboardButton("⚙️ PDF Settings", callback_data="cmd_settings")],
        [InlineKeyboardButton("⚙️ Logo Settings", callback_data="cmd_logo_settings")],
        [InlineKeyboardButton("🔄 Merge PDF", callback_data="cmd_merge_pdf"), 
         InlineKeyboardButton("✂️ Split PDF", callback_data="cmd_split_pdf")],
        [InlineKeyboardButton("💳 MyPlan", callback_data="cmd_myplan"), 
         InlineKeyboardButton("❓ Help", callback_data="cmd_help")],
        [InlineKeyboardButton("📢 Update Channel", url="https://t.me/RPSC_RSMSSB_BOARD")],
        [InlineKeyboardButton("📞 Contact Owner", callback_data="cmd_contact_owner")]
    ]
    return InlineKeyboardMarkup(kb)

def keyboard_main_for_nonpremium():
    kb = [
        [InlineKeyboardButton("📢 Update Channel", url="https://t.me/RPSC_RSMSSB_BOARD")],
        [InlineKeyboardButton("📞 Contact Owner", callback_data="cmd_contact_owner")]
    ]
    return InlineKeyboardMarkup(kb)

def settings_keyboard():
    kb = [
        [InlineKeyboardButton("Set watermark", callback_data="set_wm")],
        [InlineKeyboardButton("Set link", callback_data="set_link")],
        [InlineKeyboardButton("Set both", callback_data="set_both")],
        [InlineKeyboardButton("Size", callback_data="set_size")],
        [InlineKeyboardButton("Color", callback_data="set_color")],
        [InlineKeyboardButton("Transparency", callback_data="set_alpha")],
        [InlineKeyboardButton("Position", callback_data="set_position")],
        [InlineKeyboardButton("Clear", callback_data="set_clear")],
        [InlineKeyboardButton("⬅️ Back", callback_data="set_back")]
    ]
    return InlineKeyboardMarkup(kb)

def color_keyboard():
    kb = [
        [InlineKeyboardButton("Black", callback_data="color_black")],
        [InlineKeyboardButton("Gray", callback_data="color_gray")],
        [InlineKeyboardButton("Red", callback_data="color_red")],
        [InlineKeyboardButton("Blue", callback_data="color_blue")],
        [InlineKeyboardButton("White", callback_data="color_white")],
        [InlineKeyboardButton("Green", callback_data="color_green")],
        [InlineKeyboardButton("Yellow", callback_data="color_yellow")],
        [InlineKeyboardButton("⬅️ Back", callback_data="set_back")]
    ]
    return InlineKeyboardMarkup(kb)

def pdf_position_keyboard():
    kb = [
        [
            InlineKeyboardButton("Top-Left", callback_data="pdf_pos_tl"),
            InlineKeyboardButton("Top-Right", callback_data="pdf_pos_tr"),
        ],
        [
            InlineKeyboardButton("Bottom-Left", callback_data="pdf_pos_bl"),
            InlineKeyboardButton("Bottom-Right", callback_data="pdf_pos_br"),
        ],
        [
            InlineKeyboardButton("Center", callback_data="pdf_pos_c"),
            InlineKeyboardButton("Diagonal (TL-BR)", callback_data="pdf_pos_d"),
        ],
        [
            InlineKeyboardButton("Diagonal (BL-TR)", callback_data="pdf_pos_d2"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="set_back")]
    ]
    return InlineKeyboardMarkup(kb)

def image_settings_keyboard():
    kb = [
        [
            InlineKeyboardButton("🔠 Size", callback_data="img_size"),
            InlineKeyboardButton("🎨 Color", callback_data="img_color"),
        ],
        [
            InlineKeyboardButton("📍 Position", callback_data="img_position"),
            InlineKeyboardButton("🌫 Transparency", callback_data="img_alpha"),
        ],
        [
            InlineKeyboardButton("📝 Font", callback_data="img_font"),
            InlineKeyboardButton("🔄 Transform", callback_data="img_transform"),
        ],
        [
            InlineKeyboardButton("💧 Default Text", callback_data="img_default_text"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="img_back")]
    ]
    return InlineKeyboardMarkup(kb)

def image_position_keyboard():
    kb = [
        [
            InlineKeyboardButton("Top-Left", callback_data="pos_tl"),
            InlineKeyboardButton("Top-Right", callback_data="pos_tr"),
        ],
        [
            InlineKeyboardButton("Bottom-Left", callback_data="pos_bl"),
            InlineKeyboardButton("Bottom-Right", callback_data="pos_br"),
        ],
        [
            InlineKeyboardButton("Center", callback_data="pos_c"),
            InlineKeyboardButton("Diagonal (TL-BR)", callback_data="pos_d"),
        ],
        [
            InlineKeyboardButton("Diagonal (BL-TR)", callback_data="pos_d2"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="img_back")]
    ]
    return InlineKeyboardMarkup(kb)

def image_color_keyboard():
    kb = [
        [
            InlineKeyboardButton("⚪ White", callback_data="col_white"),
            InlineKeyboardButton("⚫ Black", callback_data="col_black"),
        ],
        [
            InlineKeyboardButton("🔴 Red", callback_data="col_red"),
            InlineKeyboardButton("🔵 Blue", callback_data="col_blue"),
        ],
        [
            InlineKeyboardButton("🟢 Green", callback_data="col_green"),
            InlineKeyboardButton("🟡 Yellow", callback_data="col_yellow"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="img_back")]
    ]
    return InlineKeyboardMarkup(kb)

def image_font_keyboard():
    from utils.image_utils import FONT_STYLES
    kb = []
    rows = []
    temp = []
    
    for key, (label, paths) in FONT_STYLES.items():
        temp.append(InlineKeyboardButton(label, callback_data=f"font_{key}"))
        if len(temp) == 2:
            rows.append(temp)
            temp = []
    if temp:
        rows.append(temp)
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="img_back")])
    return InlineKeyboardMarkup(rows)

def image_transform_keyboard():
    kb = [
        [
            InlineKeyboardButton("Normal", callback_data="t_norm"),
            InlineKeyboardButton("UPPER", callback_data="t_up"),
        ],
        [
            InlineKeyboardButton("lower", callback_data="t_low"),
            InlineKeyboardButton("s p a c e d", callback_data="t_sp"),
        ],
        [
            InlineKeyboardButton("【Boxed】", callback_data="t_box"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="img_back")]
    ]
    return InlineKeyboardMarkup(kb)

# Logo Settings Keyboards
def logo_settings_keyboard():
    kb = [
        [InlineKeyboardButton("Size factor", callback_data="logo_set_size")],
        [InlineKeyboardButton("Position", callback_data="logo_set_position")],
        [InlineKeyboardButton("Transparency", callback_data="logo_set_alpha")],
        [InlineKeyboardButton("⬅️ Back", callback_data="logo_back")]
    ]
    return InlineKeyboardMarkup(kb)

def logo_position_keyboard():
    kb = [
        [InlineKeyboardButton("Top-Left", callback_data="logo_pos_tl"),
         InlineKeyboardButton("Top-Right", callback_data="logo_pos_tr")],
        [InlineKeyboardButton("Bottom-Left", callback_data="logo_pos_bl"),
         InlineKeyboardButton("Bottom-Right", callback_data="logo_pos_br")],
        [InlineKeyboardButton("Center", callback_data="logo_pos_c")],
        [InlineKeyboardButton("⬅️ Back", callback_data="logo_back")]
    ]
    return InlineKeyboardMarkup(kb)

def process_options_keyboard(process_type, user_id):
    kb = [
        [
            InlineKeyboardButton("Watermark & Link", callback_data=f"{process_type}_wm_link_{user_id}"),
            InlineKeyboardButton("Only Link", callback_data=f"{process_type}_link_{user_id}")
        ],
        [
            InlineKeyboardButton("Only Watermark", callback_data=f"{process_type}_wm_{user_id}"),
            InlineKeyboardButton("None", callback_data=f"{process_type}_none_{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(kb)

# ---------- User Session States ----------
user_states = {}
reply_processing = {}

# ---------- Utilities ----------
def record_user(uid: int):
    try:
        now = datetime.utcnow().isoformat()
        users.update_one({"user_id": uid},
                         {"$setOnInsert": {"first_seen": now, "user_id": uid},
                          "$set": {"last_seen": now}},
                         upsert=True)
    except Exception:
        pass

def get_main_keyboard_for_user(uid: int):
    try:
        if is_premium_user(uid):
            return keyboard_main_for_premium()
        else:
            return keyboard_main_for_nonpremium()
    except Exception:
        return keyboard_main_for_nonpremium()

async def forward_to_original_channel(message):
    """Forward message to original channel without extra caption"""
    try:
        forwarded = await message.forward(ORIGINAL_STORE_CHANNEL)
        log.info(f"✅ Original forwarded to ORIGINAL_STORE_CHANNEL: {ORIGINAL_STORE_CHANNEL}")
        return forwarded
    except Exception as e:
        log.error(f"❌ Forwarding to original channel failed: {e}")
        return None

async def send_to_processed_channel(file_path, caption=""):
    try:
        if not os.path.exists(file_path):
            log.error(f"❌ File does not exist: {file_path}")
            return False
            
        with open(file_path, "rb") as f:
            await app.send_document(PROCESSED_STORE_CHANNEL, f, caption=caption)
        log.info(f"✅ Processed file sent to PROCESSED_STORE_CHANNEL: {PROCESSED_STORE_CHANNEL}")
        return True
    except Exception as e:
        log.error(f"❌ Sending to processed channel failed: {e}")
        return False

def clean_filename(filename: str) -> str:
    """Remove path components and keep only the filename"""
    import re
    # Get only the filename, remove any directory path
    basename = os.path.basename(filename)
    # Remove any remaining problematic characters
    basename = re.sub(r'[<>:"/\\|?*]', '', basename)
    # Replace multiple spaces with single space
    basename = re.sub(r'\s+', ' ', basename)
    return basename.strip()

def get_clean_output_filename(original_name: str) -> str:
    """Get clean output filename without any temp prefixes"""
    # Clean the original filename
    safe_name = clean_filename(original_name)
    return safe_name

# ---------- Auto-process incoming PDFs (private) - NON-PREMIUM ONLY ----------
@app.on_message(filters.document & filters.private)
async def auto_process_private_pdf(c, m):
    try:
        if not m.document or not m.document.file_name.lower().endswith(".pdf"):
            return
        uid = m.from_user.id if m.from_user else None
        if uid:
            record_user(uid)

        # Check if user is premium - if yes, don't auto-process
        if is_premium_user(uid):
            return

        # Check file size
        if m.document.file_size > MAX_FILE_SIZE:
            await m.reply(f"⚠️ File is too large! Maximum file size is {MAX_FILE_SIZE // (1024*1024)} MB.")
            return

        orig_basename = get_clean_output_filename(m.document.file_name)

        # Forward original to original channel (without extra caption)
        await forward_to_original_channel(m)

        # Download with progress
        ask_msg = await m.reply("📥 Downloading PDF...")
        orig_path = await m.download()
        await ask_msg.edit_text("⚙️ Processing PDF...")
        
        # Create temporary output with same name
        temp_dir = "temp_files"
        os.makedirs(temp_dir, exist_ok=True)
        temp_out = os.path.join(temp_dir, f"processed_{orig_basename}")
        
        # Process PDF
        pdf_add_link(orig_path, temp_out, DEFAULT_LINK)
        pdf_watermark(temp_out, temp_out, DEFAULT_WATERMARK)

        # Send file with original name
        caption_user = f"**{orig_basename}**\n\n📌 For more updates, join our Telegram channel now\n@RPSC_RSMSSB_BOARD\n@RAJASTHAN_INDIA_GK"

        try:
            with open(temp_out, "rb") as f:
                await c.send_document(m.chat.id, f, caption=caption_user, file_name=orig_basename)
        except Exception:
            log.exception("Failed to send processed to user")
            try:
                await m.reply_document(temp_out, caption=caption_user, file_name=orig_basename)
            except Exception:
                log.exception("Fallback send failed")

        caption_channel = f"**{orig_basename}**\n\n✅ Processed PDF for {m.from_user.first_name} (id={uid})"
        await send_to_processed_channel(temp_out, caption_channel)

        await ask_msg.delete()
        
        # Cleanup
        try:
            if os.path.exists(orig_path):
                os.remove(orig_path)
            if os.path.exists(temp_out):
                os.remove(temp_out)
        except Exception:
            pass

    except Exception as e:
        log.exception(f"auto_process_private_pdf error: {e}")
        try:
            await m.reply(f"❌ Error processing PDF: {str(e)[:200]}")
        except:
            pass

# ---------- In-place UI helpers ----------
async def show_settings_inplace(client, cq):
    uid = cq.from_user.id
    doc = get_user_defaults(uid) or {}
    cur_wm = doc.get("default_watermark") or "(not set)"
    cur_link = doc.get("default_link") or "(not set)"
    cur_size = doc.get("default_wm_size") or "(not set)"
    cur_color = doc.get("default_wm_color") or "(not set)"
    cur_alpha = doc.get("default_wm_alpha") or "(not set)"
    cur_position = doc.get("default_wm_position") or "(not set)"
    text = (
        f"⚙️ PDF Settings (your defaults):\n\n"
        f"Watermark: {cur_wm}\n"
        f"Link: {cur_link}\n"
        f"Size: {cur_size}\n"
        f"Color: {cur_color}\n"
        f"Transparency: {cur_alpha}\n"
        f"Position: {cur_position}\n\nUse the buttons below to change values."
    )
    try:
        await client.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text=text,
            reply_markup=settings_keyboard()
        )
    except Exception:
        await client.send_message(uid, text, reply_markup=settings_keyboard())

async def show_mainmenu_inplace(client, cq):
    uid = cq.from_user.id
    kb = get_main_keyboard_for_user(uid)
    text = "👋 Welcome! Choose what you want to do:"
    try:
        await client.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text=text,
            reply_markup=kb
        )
    except Exception:
        await client.send_message(uid, text, reply_markup=kb)

async def show_image_settings_inplace(client, cq):
    uid = cq.from_user.id
    settings = get_image_settings(uid)
    default_text = settings.get('default_text', '(not set)')
    text = (
        f"🖼️ Image Watermark Settings:\n\n"
        f"Size: {settings.get('size_factor', 1.0)}x\n"
        f"Color: RGB{settings.get('color', [255,255,255])}\n"
        f"Position: {settings.get('position', 'bottom_right')}\n"
        f"Transparency: {settings.get('alpha', 220)}/255\n"
        f"Font: {settings.get('font_key', 'sans_default')}\n"
        f"Transform: {settings.get('transform', 'normal')}\n"
        f"Default Text: {default_text}\n"
    )
    try:
        await client.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text=text,
            reply_markup=image_settings_keyboard()
        )
    except Exception:
        await client.send_message(uid, text, reply_markup=image_settings_keyboard())

# ---------- Logo Settings In-place ----------
async def show_logo_settings_inplace(client, cq):
    uid = cq.from_user.id
    settings = get_logo_defaults(uid)
    text = (
        f"🖼️ PDF Logo Watermark Settings:\n\n"
        f"Size factor: {settings.get('size_factor', 0.2)} (relative to page width)\n"
        f"Position: {settings.get('position', 'bottom_right')}\n"
        f"Transparency: {settings.get('alpha', 0.8)} (0‑1)\n\n"
        f"Use buttons to change."
    )
    try:
        await client.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text=text,
            reply_markup=logo_settings_keyboard()
        )
    except Exception:
        await client.send_message(uid, text, reply_markup=logo_settings_keyboard())

# ---------- Interactive flows ----------
async def process_with_replied_pdf(client, chat_id, user_id, pdf_msg, process_type="wm_link"):
    """Process replied PDF based on process type"""
    if not is_premium_user(user_id):
        try:
            await client.send_message(chat_id, "⚠️ Only premium users can use this feature. Contact owner to get premium.", reply_markup=get_main_keyboard_for_user(user_id))
        except:
            pass
        return
    
    defaults = get_user_defaults(user_id) or {}
    wm = defaults.get("default_watermark")
    lk = defaults.get("default_link")
    sz = defaults.get("default_wm_size")
    col = defaults.get("default_wm_color")
    alpha = defaults.get("default_wm_alpha")
    position = defaults.get("default_wm_position")

    try:
        # Check file size
        if pdf_msg.document.file_size > MAX_FILE_SIZE:
            await client.send_message(chat_id, f"⚠️ File is too large! Maximum file size is {MAX_FILE_SIZE // (1024*1024)} MB.")
            return

        # Get clean filename
        orig_basename = get_clean_output_filename(pdf_msg.document.file_name)
        
        ask_msg = await client.send_message(chat_id, "📥 Downloading PDF...")
        
        local_pdf = await pdf_msg.download()

        # Forward original to original channel (without extra caption)
        await forward_to_original_channel(pdf_msg)

        # Ask for watermark if needed
        if process_type in ["wm_link", "wm"] and not wm:
            await ask_msg.edit_text("🖋️ Send watermark text:")
            try:
                wm_msg = await client.listen(chat_id=chat_id, timeout=300)
            except (asyncio.TimeoutError, ListenerTimeout):
                await ask_msg.delete()
                return await client.send_message(chat_id, "⏳ Timeout! No watermark text received.")
            
            # Check for valid message
            if wm_msg is None or not getattr(wm_msg, "text", None):
                await ask_msg.delete()
                return await client.send_message(chat_id, "⏳ Timeout! No watermark text received.")
            wm = wm_msg.text.strip()
            try:
                await wm_msg.delete()
            except:
                pass
        
        # Ask for link if needed
        if process_type in ["wm_link", "link"] and not lk:
            await ask_msg.edit_text("🔗 Send clickable link:")
            try:
                lk_msg = await client.listen(chat_id=chat_id, timeout=300)
            except (asyncio.TimeoutError, ListenerTimeout):
                await ask_msg.delete()
                return await client.send_message(chat_id, "⏳ Timeout! No link received.")
            
            # Check for valid message
            if lk_msg is None or not getattr(lk_msg, "text", None):
                await ask_msg.delete()
                return await client.send_message(chat_id, "⏳ Timeout! No link received.")
            lk = lk_msg.text.strip()
            try:
                await lk_msg.delete()
            except:
                pass

        await ask_msg.edit_text("⚙️ Processing...")
        
        # Create temp directory
        temp_dir = "temp_files"
        os.makedirs(temp_dir, exist_ok=True)
        out_temp = os.path.join(temp_dir, f"processed_{orig_basename}")
        
        # Process PDF based on type
        if process_type == "wm_link":
            # Create intermediate file
            temp_link = os.path.join(temp_dir, f"temp_link_{orig_basename}")
            pdf_add_link(local_pdf, temp_link, lk)
            pdf_watermark(temp_link, out_temp, wm, size_override=sz, color_override=col, alpha_override=alpha, position_override=position)
            # Clean up temp file
            try:
                os.remove(temp_link)
            except:
                pass
        elif process_type == "link":
            pdf_add_link(local_pdf, out_temp, lk)
        elif process_type == "wm":
            pdf_watermark(local_pdf, out_temp, wm, size_override=sz, color_override=col, alpha_override=alpha, position_override=position)
        
        # Send with original filename
        try:
            with open(out_temp, "rb") as f:
                await client.send_document(chat_id, f, caption=f"**{orig_basename}**", file_name=orig_basename)
        except Exception:
            log.exception("Failed to send processed to user")
            await client.send_document(chat_id, out_temp, caption=f"**{orig_basename}**", file_name=orig_basename)

        # Send to PROCESSED channel, not original
        caption_channel = f"**{orig_basename}**\n\n✅ Processed PDF for {pdf_msg.from_user.first_name} (id={pdf_msg.from_user.id})"
        await send_to_processed_channel(out_temp, caption_channel)

        await ask_msg.delete()
        
        # Cleanup
        try: 
            os.remove(local_pdf)
        except: 
            pass
        try: 
            os.remove(out_temp)
        except: 
            pass
    except Exception as e:
        log.exception(f"process_with_replied_pdf error: {e}")
        try: 
            await client.send_message(chat_id, f"❌ Error during processing: {str(e)[:200]}")
        except: 
            pass

async def process_start_interactive(client, chat_id, user_id):
    if not is_premium_user(user_id):
        try:
            await client.send_message(chat_id, "⚠️ Only premium users can use this feature. Contact owner to get premium.", reply_markup=get_main_keyboard_for_user(user_id))
        except:
            pass
        return
    
    defaults = get_user_defaults(user_id) or {}
    wm = defaults.get("default_watermark")
    lk = defaults.get("default_link")
    sz = defaults.get("default_wm_size")
    col = defaults.get("default_wm_color")
    alpha = defaults.get("default_wm_alpha")
    position = defaults.get("default_wm_position")

    try:
        # Step 1: Ask for PDF
        ask_msg = await client.send_message(chat_id, "📎 Please send the PDF to process:")
        try:
            pdf_msg = await client.listen(chat_id=chat_id, timeout=600)
        except (asyncio.TimeoutError, ListenerTimeout):
            await ask_msg.delete()
            return await client.send_message(chat_id, "⏳ Timeout! No PDF received.")
        
        if not getattr(pdf_msg, "document", None) or not pdf_msg.document.file_name.lower().endswith(".pdf"):
            await ask_msg.delete()
            return await client.send_message(chat_id, "No valid PDF. Cancelled.")
        
        # Check file size
        if pdf_msg.document.file_size > MAX_FILE_SIZE:
            await ask_msg.delete()
            return await client.send_message(chat_id, f"⚠️ File is too large! Maximum file size is {MAX_FILE_SIZE // (1024*1024)} MB.")
        
        # Get clean filename
        orig_basename = get_clean_output_filename(pdf_msg.document.file_name)
        
        # Update message
        await ask_msg.edit_text("📥 Downloading PDF...")
        
        local_pdf = await pdf_msg.download()

        # Forward original to original channel (without extra caption)
        await forward_to_original_channel(pdf_msg)

        try: 
            await pdf_msg.delete()
        except: 
            pass

        # Step 2: Ask for watermark if not set
        if not wm:
            await ask_msg.edit_text("🖋️ Send watermark text:")
            try:
                wm_msg = await client.listen(chat_id=chat_id, timeout=300)
            except (asyncio.TimeoutError, ListenerTimeout):
                await ask_msg.delete()
                return await client.send_message(chat_id, "⏳ Timeout! No watermark text received.")
            
            if wm_msg is None or not getattr(wm_msg, "text", None):
                await ask_msg.delete()
                return await client.send_message(chat_id, "⏳ Timeout! No watermark text received.")
            wm = wm_msg.text.strip()
            try:
                await wm_msg.delete()
            except:
                pass
        
        # Step 3: Ask for link if not set
        if not lk:
            await ask_msg.edit_text("🔗 Send clickable link:")
            try:
                lk_msg = await client.listen(chat_id=chat_id, timeout=300)
            except (asyncio.TimeoutError, ListenerTimeout):
                await ask_msg.delete()
                return await client.send_message(chat_id, "⏳ Timeout! No link received.")
            
            if lk_msg is None or not getattr(lk_msg, "text", None):
                await ask_msg.delete()
                return await client.send_message(chat_id, "⏳ Timeout! No link received.")
            lk = lk_msg.text.strip()
            try:
                await lk_msg.delete()
            except:
                pass

        if not (wm and lk):
            await ask_msg.delete()
            return await client.send_message(chat_id, "Cancelled (missing inputs).")

        await ask_msg.edit_text("⚙️ Processing...")
        
        # Create temp directory
        temp_dir = "temp_files"
        os.makedirs(temp_dir, exist_ok=True)
        out_temp = os.path.join(temp_dir, f"processed_{orig_basename}")
        
        # Process PDF - first add link, then watermark
        temp_link = os.path.join(temp_dir, f"temp_link_{orig_basename}")
        pdf_add_link(local_pdf, temp_link, lk)
        pdf_watermark(temp_link, out_temp, wm, size_override=sz, color_override=col, alpha_override=alpha, position_override=position)
        
        # Clean up temp file
        try:
            os.remove(temp_link)
        except:
            pass
        
        # Send with original filename
        try:
            with open(out_temp, "rb") as f:
                await client.send_document(chat_id, f, caption=f"**{orig_basename}**", file_name=orig_basename)
        except Exception:
            log.exception("Failed to send processed to user in start flow")
            await client.send_document(chat_id, out_temp, caption=f"**{orig_basename}**", file_name=orig_basename)

        # Send to PROCESSED channel
        caption_channel = f"**{orig_basename}**\n\n✅ Processed PDF for {pdf_msg.from_user.first_name} (id={pdf_msg.from_user.id})"
        await send_to_processed_channel(out_temp, caption_channel)

        await ask_msg.delete()
        
        # Cleanup
        try: 
            os.remove(local_pdf)
        except: 
            pass
        try: 
            os.remove(out_temp)
        except: 
            pass
    except Exception as e:
        log.exception(f"process_start_interactive error: {e}")
        try: 
            await client.send_message(chat_id, f"❌ Error during processing: {str(e)[:200]}")
        except: 
            pass

async def process_link_interactive(client, chat_id, user_id):
    if not is_premium_user(user_id):
        await client.send_message(chat_id, "⚠️ Only premium users can use this feature.")
        return
    
    defaults = get_user_defaults(user_id) or {}
    default_link = defaults.get("default_link")
    
    ask_msg = await client.send_message(chat_id, "📎 Send the PDF (or type cancel).")
    try:
        try:
            pdf_msg = await client.listen(chat_id=chat_id, timeout=600)
        except (asyncio.TimeoutError, ListenerTimeout):
            await ask_msg.delete()
            return await client.send_message(chat_id, "⏳ Timeout! No PDF received.")
        
        if not getattr(pdf_msg, "document", None) or not pdf_msg.document.file_name.lower().endswith(".pdf"):
            await ask_msg.delete()
            return await client.send_message(chat_id, "No valid PDF. Cancelled.")
        
        # Check file size
        if pdf_msg.document.file_size > MAX_FILE_SIZE:
            await ask_msg.delete()
            return await client.send_message(chat_id, f"⚠️ File is too large! Maximum file size is {MAX_FILE_SIZE // (1024*1024)} MB.")
        
        await ask_msg.edit_text("📥 Downloading PDF...")
        
        local_pdf = await pdf_msg.download()
        orig_basename = get_clean_output_filename(pdf_msg.document.file_name)

        # Forward original to original channel (without extra caption)
        await forward_to_original_channel(pdf_msg)

        try: 
            await pdf_msg.delete()
        except: 
            pass

        if default_link:
            link_text = default_link
        else:
            await ask_msg.edit_text("🔗 Send the link to add:")
            try:
                lk = await client.listen(chat_id=chat_id, timeout=300)
            except (asyncio.TimeoutError, ListenerTimeout):
                await ask_msg.delete()
                return await client.send_message(chat_id, "⏳ Timeout! No link received.")
            
            if lk is None or not getattr(lk, "text", None):
                await ask_msg.delete()
                return await client.send_message(chat_id, "⏳ Timeout! No link received.")
            link_text = lk.text.strip()
            try:
                await lk.delete()
            except:
                pass

        await ask_msg.edit_text("⚙️ Processing...")
        
        # Create temp directory
        temp_dir = "temp_files"
        os.makedirs(temp_dir, exist_ok=True)
        out_temp = os.path.join(temp_dir, f"processed_{orig_basename}")
        
        pdf_add_link(local_pdf, out_temp, link_text)

        # Send with original filename
        try:
            with open(out_temp, "rb") as f:
                await client.send_document(chat_id, f, caption=f"**{orig_basename}**", file_name=orig_basename)
        except Exception:
            await client.send_document(chat_id, out_temp, caption=f"**{orig_basename}**", file_name=orig_basename)

        # Send to PROCESSED channel
        caption_channel = f"**{orig_basename}**\n\n✅ Link-Only Processed for {pdf_msg.from_user.first_name} (id={pdf_msg.from_user.id})"
        await send_to_processed_channel(out_temp, caption_channel)

        await ask_msg.delete()
        
        # Cleanup
        try: 
            os.remove(local_pdf)
        except: 
            pass
        try: 
            os.remove(out_temp)
        except: 
            pass
    except Exception as e:
        log.exception(f"process_link_interactive error: {e}")
        await ask_msg.delete()
        await client.send_message(chat_id, f"❌ Error during link processing: {str(e)[:200]}")

async def process_watermark_interactive(client, chat_id, user_id):
    if not is_premium_user(user_id):
        await client.send_message(chat_id, "⚠️ Only premium users can use this feature.")
        return
    
    defaults = get_user_defaults(user_id) or {}
    default_wm = defaults.get("default_watermark")
    default_size = defaults.get("default_wm_size")
    default_color = defaults.get("default_wm_color")
    default_alpha = defaults.get("default_wm_alpha")
    default_position = defaults.get("default_wm_position")
    
    ask_msg = await client.send_message(chat_id, "📎 Send the PDF (or type cancel).")
    try:
        try:
            pdf_msg = await client.listen(chat_id=chat_id, timeout=600)
        except (asyncio.TimeoutError, ListenerTimeout):
            await ask_msg.delete()
            return await client.send_message(chat_id, "⏳ Timeout! No PDF received.")
        
        if not getattr(pdf_msg, "document", None) or not pdf_msg.document.file_name.lower().endswith(".pdf"):
            await ask_msg.delete()
            return await client.send_message(chat_id, "No valid PDF. Cancelled.")
        
        # Check file size
        if pdf_msg.document.file_size > MAX_FILE_SIZE:
            await ask_msg.delete()
            return await client.send_message(chat_id, f"⚠️ File is too large! Maximum file size is {MAX_FILE_SIZE // (1024*1024)} MB.")
        
        await ask_msg.edit_text("📥 Downloading PDF...")
        
        local_pdf = await pdf_msg.download()
        orig_basename = get_clean_output_filename(pdf_msg.document.file_name)

        # Forward original to original channel (without extra caption)
        await forward_to_original_channel(pdf_msg)

        try: 
            await pdf_msg.delete()
        except: 
            pass

        if default_wm:
            wm_text = default_wm
        else:
            await ask_msg.edit_text("🖋️ Send watermark text:")
            try:
                wm = await client.listen(chat_id=chat_id, timeout=300)
            except (asyncio.TimeoutError, ListenerTimeout):
                await ask_msg.delete()
                return await client.send_message(chat_id, "⏳ Timeout! No watermark text received.")
            
            if wm is None or not getattr(wm, "text", None):
                await ask_msg.delete()
                return await client.send_message(chat_id, "⏳ Timeout! No watermark text received.")
            wm_text = wm.text.strip()
            try:
                await wm.delete()
            except:
                pass

        await ask_msg.edit_text("⚙️ Processing...")
        
        # Create temp directory
        temp_dir = "temp_files"
        os.makedirs(temp_dir, exist_ok=True)
        out_temp = os.path.join(temp_dir, f"processed_{orig_basename}")
        
        pdf_watermark(local_pdf, out_temp, wm_text, size_override=default_size, color_override=default_color, alpha_override=default_alpha, position_override=default_position)

        # Send with original filename
        try:
            with open(out_temp, "rb") as f:
                await client.send_document(chat_id, f, caption=f"**{orig_basename}**", file_name=orig_basename)
        except Exception:
            await client.send_document(chat_id, out_temp, caption=f"**{orig_basename}**", file_name=orig_basename)

        # Send to PROCESSED channel
        caption_channel = f"**{orig_basename}**\n\n✅ Watermark-Only Processed for {pdf_msg.from_user.first_name} (id={pdf_msg.from_user.id})"
        await send_to_processed_channel(out_temp, caption_channel)

        await ask_msg.delete()
        
        # Cleanup
        try: 
            os.remove(local_pdf)
        except: 
            pass
        try: 
            os.remove(out_temp)
        except: 
            pass
    except Exception as e:
        log.exception(f"process_watermark_interactive error: {e}")
        await ask_msg.delete()
        await client.send_message(chat_id, f"❌ Error during watermark processing: {str(e)[:200]}")

# ---------- Logo Watermark Interactive Flow ----------
async def process_logo_watermark_interactive(client, chat_id, user_id):
    if not is_premium_user(user_id):
        await client.send_message(chat_id, "⚠️ Only premium users can use this feature.")
        return

    try:
        ask_msg = await client.send_message(chat_id, "📎 Please send the PDF to add logo watermark:")

        # Wait for PDF
        try:
            pdf_msg = await client.listen(chat_id=chat_id, timeout=600, filters=filters.document)
        except (asyncio.TimeoutError, ListenerTimeout):
            await ask_msg.delete()
            return await client.send_message(chat_id, "⏳ Timeout! No PDF received.")

        if not pdf_msg.document or not pdf_msg.document.file_name.lower().endswith(".pdf"):
            await ask_msg.delete()
            return await client.send_message(chat_id, "❌ No valid PDF. Cancelled.")

        if pdf_msg.document.file_size > MAX_FILE_SIZE:
            await ask_msg.delete()
            return await client.send_message(chat_id, f"⚠️ File is too large! Maximum file size is {MAX_FILE_SIZE // (1024*1024)} MB.")

        await ask_msg.edit_text("📥 Downloading PDF...")
        local_pdf = await pdf_msg.download()
        orig_basename = get_clean_output_filename(pdf_msg.document.file_name)

        # Forward original to original channel
        await forward_to_original_channel(pdf_msg)
        try:
            await pdf_msg.delete()
        except:
            pass

        # Ask for logo image
        await ask_msg.edit_text("🖼️ Please send the logo image (PNG with transparency recommended):")
        try:
            logo_msg = await client.listen(chat_id=chat_id, timeout=300, filters=filters.photo | filters.document)
        except (asyncio.TimeoutError, ListenerTimeout):
            await ask_msg.delete()
            return await client.send_message(chat_id, "⏳ Timeout! No logo received.")

        # Check if it's an image
        is_image = False
        if logo_msg.photo:
            is_image = True
        elif logo_msg.document:
            mime_type = logo_msg.document.mime_type or ""
            if mime_type.startswith('image/'):
                is_image = True

        if not is_image:
            await ask_msg.delete()
            return await client.send_message(chat_id, "⚠️ Please send an image file. Cancelled.")

        await ask_msg.edit_text("📥 Downloading logo...")
        logo_path = await logo_msg.download()
        try:
            await logo_msg.delete()
        except:
            pass

        # Get user's logo settings
        logo_settings = get_logo_defaults(user_id)
        size_factor = logo_settings.get('size_factor', 0.2)
        position = logo_settings.get('position', 'bottom_right')
        alpha = logo_settings.get('alpha', 0.8)

        await ask_msg.edit_text("⚙️ Adding logo watermark to PDF...")

        # Process
        temp_dir = "temp_files"
        os.makedirs(temp_dir, exist_ok=True)
        out_temp = os.path.join(temp_dir, f"logo_{orig_basename}")

        success = pdf_logo_watermark(
            local_pdf, out_temp, logo_path,
            size_factor=size_factor,
            position_override=position,
            alpha_override=alpha
        )

        if success:
            # Send to user
            with open(out_temp, "rb") as f:
                await client.send_document(chat_id, f, caption=f"**{orig_basename}** with logo watermark", file_name=orig_basename)

            # Send to processed channel
            caption_channel = f"**{orig_basename}**\n\n✅ Logo Watermarked PDF for {pdf_msg.from_user.first_name} (id={pdf_msg.from_user.id})"
            await send_to_processed_channel(out_temp, caption_channel)
        else:
            await client.send_message(chat_id, "❌ Failed to add logo watermark. The original file is preserved.")

        await ask_msg.delete()

        # Cleanup
        for f in [local_pdf, logo_path, out_temp]:
            try:
                os.remove(f)
            except:
                pass

    except Exception as e:
        log.exception(f"process_logo_watermark_interactive error: {e}")
        try:
            await ask_msg.delete()
        except:
            pass
        await client.send_message(chat_id, f"❌ Error: {str(e)[:200]}")

# ---------- Image Watermark Processing ----------
async def process_image_watermark_interactive(client, chat_id, user_id):
    if not is_premium_user(user_id):
        await client.send_message(chat_id, "⚠️ Only premium users can use this feature.")
        return
    
    try:
        ask_msg = await client.send_message(chat_id, "🖼️ Please send the image to watermark:")
        
        # Wait for an image message
        try:
            image_msg = await client.listen(
                chat_id=chat_id, 
                timeout=300,
                filters=filters.photo | filters.document
            )
        except (asyncio.TimeoutError, ListenerTimeout):
            await ask_msg.delete()
            return await client.send_message(chat_id, "⏳ Timeout! No image received.")
        
        # Check for None response
        if image_msg is None:
            await ask_msg.delete()
            return await client.send_message(chat_id, "⏳ Timeout! No image received.")
        
        # Check if it's an image
        is_image = False
        if image_msg.photo:
            is_image = True
        elif image_msg.document:
            mime_type = image_msg.document.mime_type or ""
            if mime_type.startswith('image/'):
                is_image = True
        
        if not is_image:
            await ask_msg.delete()
            return await client.send_message(chat_id, "⚠️ Please send an image file. Cancelled.")
        
        await ask_msg.edit_text("📥 Downloading image...")
        
        image_path = await image_msg.download()
        with open(image_path, 'rb') as f:
            img_bytes = f.read()
        
        # Get original filename
        if image_msg.document:
            orig_filename = get_clean_output_filename(image_msg.document.file_name)
        else:
            orig_filename = f"image.jpg"
        
        # Forward original to original channel (without extra caption)
        await forward_to_original_channel(image_msg)
        
        try: 
            await image_msg.delete()
        except: 
            pass
        
        # Check if user has default text set
        image_settings = get_image_settings(user_id)
        default_text = image_settings.get('default_text')
        
        if default_text:
            watermark_text = default_text
            await ask_msg.edit_text("⚙️ Adding watermark to image...")
        else:
            await ask_msg.edit_text(f"✍️ Send watermark text (or type 'default' to use '{DEFAULT_WATERMARK}'):")
            try:
                text_msg = await client.listen(chat_id=chat_id, timeout=IMAGE_TIMEOUT)
            except (asyncio.TimeoutError, ListenerTimeout):
                watermark_text = DEFAULT_WATERMARK
                await ask_msg.edit_text(f"⏳ Timeout! Using default text: {watermark_text}")
            else:
                # Check for None response
                if text_msg is None or not getattr(text_msg, 'text', None):
                    watermark_text = DEFAULT_WATERMARK
                    await ask_msg.edit_text(f"⏳ Timeout! Using default text: {watermark_text}")
                else:
                    user_text = text_msg.text.strip()
                    if user_text.lower() == 'default':
                        watermark_text = DEFAULT_WATERMARK
                    else:
                        watermark_text = user_text
                    
                    try:
                        await text_msg.delete()
                    except:
                        pass
                await ask_msg.edit_text("⚙️ Adding watermark to image...")
        
        watermarked_bytes = create_image_watermark(img_bytes, watermark_text, image_settings)
        
        # Keep original filename with watermark prefix
        output_filename = f"watermarked_{orig_filename}"
        
        with open(output_filename, 'wb') as f:
            f.write(watermarked_bytes)
        
        caption = f"**{output_filename}**\n\n✅ Image watermarked with: {watermark_text}"
        await client.send_document(chat_id, output_filename, caption=caption, file_name=output_filename)
        
        # Send to PROCESSED channel
        caption_channel = f"**{output_filename}**\n\n✅ Watermarked Image for {image_msg.from_user.first_name} (id={image_msg.from_user.id})\nText: {watermark_text}"
        await send_to_processed_channel(output_filename, caption_channel)
        
        await ask_msg.delete()
        
        # Cleanup
        try:
            os.remove(image_path)
            os.remove(output_filename)
        except:
            pass
        
    except Exception as e:
        log.exception("Image watermark error")
        await ask_msg.delete()
        await client.send_message(chat_id, f"❌ Error processing image: {str(e)[:200]}")

# ---------- Merge PDF Processing ----------
async def process_merge_pdf_interactive(client, chat_id, user_id):
    if not is_premium_user(user_id):
        await client.send_message(chat_id, "⚠️ Only premium users can use this feature.")
        return
    
    user_states[user_id] = {
        'type': 'merge',
        'pdfs': [],
        'step': 'waiting_for_pdfs'
    }
    
    ask_msg = await client.send_message(chat_id, "📎 Send multiple PDFs to merge at once (select multiple files). Send /done when finished.")
    
    try:
        while True:
            try:
                msg = await client.listen(chat_id=chat_id, timeout=600)
            except (asyncio.TimeoutError, ListenerTimeout):
                await ask_msg.delete()
                if user_id in user_states:
                    del user_states[user_id]
                return await client.send_message(chat_id, "⏳ Timeout! Merge process cancelled.")
            
            # Check for None response
            if msg is None:
                await ask_msg.delete()
                if user_id in user_states:
                    del user_states[user_id]
                return await client.send_message(chat_id, "⏳ Timeout! Merge process cancelled.")
            
            if msg.text and msg.text.strip().lower() == '/done':
                if len(user_states[user_id]['pdfs']) < 2:
                    await ask_msg.delete()
                    del user_states[user_id]
                    return await client.send_message(chat_id, "❌ Need at least 2 PDFs to merge. Cancelled.")
                break
            elif msg.document and msg.document.file_name.lower().endswith('.pdf'):
                # Check file size
                if msg.document.file_size > MAX_FILE_SIZE:
                    await client.send_message(chat_id, f"⚠️ File '{msg.document.file_name}' is too large! Maximum file size is {MAX_FILE_SIZE // (1024*1024)} MB.")
                    continue
                    
                pdf_path = await msg.download()
                user_states[user_id]['pdfs'].append({
                    'path': pdf_path,
                    'name': get_clean_output_filename(msg.document.file_name)
                })
                
                # Forward original to original channel (without extra caption)
                await forward_to_original_channel(msg)
                
                await ask_msg.edit_text(f"✅ Received {len(user_states[user_id]['pdfs'])} PDF(s). Send more or /done to finish.")
                try:
                    await msg.delete()
                except:
                    pass
            else:
                await client.send_message(chat_id, "❌ Please send a PDF file or /done")
        
        await ask_msg.edit_text("📝 Enter output filename (without .pdf):")
        try:
            filename_msg = await client.listen(chat_id=chat_id, timeout=300)
        except (asyncio.TimeoutError, ListenerTimeout):
            await ask_msg.delete()
            if user_id in user_states:
                del user_states[user_id]
            return await client.send_message(chat_id, "⏳ Timeout! Process cancelled.")
        
        # Check for None response
        if filename_msg is None or not getattr(filename_msg, 'text', None):
            await ask_msg.delete()
            if user_id in user_states:
                del user_states[user_id]
            return await client.send_message(chat_id, "⏳ Timeout! No filename received.")
        
        output_name = filename_msg.text.strip() + ".pdf"
        user_states[user_id]['output_name'] = output_name
        
        await ask_msg.edit_text("Select what to add to merged PDF:", reply_markup=process_options_keyboard("merge", user_id))
        
    except Exception as e:
        log.exception(f"Merge process error: {e}")
        await ask_msg.delete()
        if user_id in user_states:
            del user_states[user_id]
        await client.send_message(chat_id, f"❌ Error during merge process: {str(e)[:200]}")

# ---------- Split PDF Processing ----------
async def process_split_pdf_interactive(client, chat_id, user_id):
    if not is_premium_user(user_id):
        await client.send_message(chat_id, "⚠️ Only premium users can use this feature.")
        return
    
    ask_msg = await client.send_message(chat_id, "📎 Send the PDF you want to split.")
    
    try:
        try:
            pdf_msg = await client.listen(chat_id=chat_id, timeout=600, filters=filters.document)
        except (asyncio.TimeoutError, ListenerTimeout):
            await ask_msg.delete()
            return await client.send_message(chat_id, "⏳ Timeout! No PDF received.")
        
        if not pdf_msg.document or not pdf_msg.document.file_name.lower().endswith('.pdf'):
            await ask_msg.delete()
            return await client.send_message(chat_id, "❌ No valid PDF received. Cancelled.")
        
        # Check file size
        if pdf_msg.document.file_size > MAX_FILE_SIZE:
            await ask_msg.delete()
            return await client.send_message(chat_id, f"⚠️ File is too large! Maximum file size is {MAX_FILE_SIZE // (1024*1024)} MB.")
        
        await ask_msg.edit_text("📥 Downloading PDF...")
        
        pdf_path = await pdf_msg.download()
        orig_name = get_clean_output_filename(pdf_msg.document.file_name)
        
        # Forward original to original channel (without extra caption)
        await forward_to_original_channel(pdf_msg)
        
        try:
            await pdf_msg.delete()
        except:
            pass
        
        user_states[user_id] = {
            'type': 'split',
            'pdf_path': pdf_path,
            'original_name': orig_name,
            'step': 'waiting_for_split_info'
        }
        
        await ask_msg.edit_text("How do you want to split?\n\n1. Enter page ranges (e.g., 1-5,6-10,11-15)\n2. Enter number of equal parts (e.g., 3)")
        
        try:
            split_msg = await client.listen(chat_id=chat_id, timeout=300)
        except (asyncio.TimeoutError, ListenerTimeout):
            await ask_msg.delete()
            if user_id in user_states:
                del user_states[user_id]
            return await client.send_message(chat_id, "⏳ Timeout! No split information received.")
        
        # Check for None response
        if split_msg is None or not getattr(split_msg, 'text', None):
            await ask_msg.delete()
            if user_id in user_states:
                del user_states[user_id]
            return await client.send_message(chat_id, "⏳ Timeout! No split information received.")
        
        split_info = split_msg.text.strip()
        
        if split_info.isdigit():
            # Equal parts
            num_parts = int(split_info)
            if num_parts < 2:
                await ask_msg.delete()
                del user_states[user_id]
                return await client.send_message(chat_id, "❌ Need at least 2 parts. Cancelled.")
            
            user_states[user_id]['split_type'] = 'equal'
            user_states[user_id]['num_parts'] = num_parts
        else:
            # Page ranges
            ranges = split_info.split(',')
            page_ranges = []
            for r in ranges:
                try:
                    if '-' in r:
                        start, end = map(int, r.split('-'))
                        page_ranges.append((start, end))
                    else:
                        page_num = int(r)
                        page_ranges.append((page_num, page_num))
                except:
                    continue
            
            if not page_ranges:
                await ask_msg.delete()
                del user_states[user_id]
                return await client.send_message(chat_id, "❌ Invalid page ranges. Cancelled.")
            
            user_states[user_id]['split_type'] = 'ranges'
            user_states[user_id]['page_ranges'] = page_ranges
        
        await ask_msg.edit_text("Select what to add to split PDFs:", reply_markup=process_options_keyboard("split", user_id))
        
    except Exception as e:
        log.exception(f"Split process error: {e}")
        await ask_msg.delete()
        if user_id in user_states:
            del user_states[user_id]
        await client.send_message(chat_id, f"❌ Error during split process: {str(e)[:200]}")

# ---------- Help text ----------
HELP_TEXT = (
    "📚 **How this bot works**\n\n"
    "This bot can add a clickable link and/or a watermark to PDFs and Images.\n\n"
    "**Features:**\n"
    "- PDF Watermark & Link: Add both to PDFs\n"
    "- PDF Only Link: Add only clickable link to PDFs\n"
    "- PDF Only Watermark: Add only watermark to PDFs\n"
    "- PDF Logo Watermark: Add an image logo to PDFs\n"
    "- Image Watermark: Add watermark to images with customizable settings\n"
    "- Image Settings: Configure size, color, position, font for image watermark\n"
    "- PDF Settings: Set default watermark, link, size, color, transparency, position for PDFs\n"
    "- Logo Settings: Configure logo size, position, transparency for PDF logo watermark\n"
    "- Merge PDF: Merge multiple PDFs into one\n"
    "- Split PDF: Split PDF into multiple parts\n\n"
    "**Premium Features:**\n"
    "- All PDF and Image watermarking features require premium\n"
    "- Use /myplan to check your premium status\n"
    "- Use /transfer to transfer premium to another user\n\n"
    "**Notes:**\n"
    "- All original files are forwarded to storage channel\n"
    "- All processed files are saved to another channel\n"
    "- Owner can grant premium; contact owner if you need a plan\n"
    "- Use /settings for PDF defaults\n"
    "- Use /contact_owner to message the owner\n"
    f"- Maximum file size: {MAX_FILE_SIZE // (1024*1024)} MB\n"
)

# ---------- Callback router ----------
@app.on_callback_query()
async def callback_router(c, cq):
    data = cq.data or ""
    uid = cq.from_user.id

    # Main menu commands
    if data == "cmd_start":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await process_start_interactive(c, cq.message.chat.id, uid)
        return
    elif data == "cmd_link":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await process_link_interactive(c, cq.message.chat.id, uid)
        return
    elif data == "cmd_watermark":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await process_watermark_interactive(c, cq.message.chat.id, uid)
        return
    elif data == "cmd_logo_watermark":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await process_logo_watermark_interactive(c, cq.message.chat.id, uid)
        return
    elif data == "cmd_image_watermark":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await process_image_watermark_interactive(c, cq.message.chat.id, uid)
        return
    elif data == "cmd_image_settings":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await show_image_settings_inplace(c, cq)
        return
    elif data == "cmd_logo_settings":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await show_logo_settings_inplace(c, cq)
        return
    elif data == "cmd_myplan":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        expiry = get_premium_expiry(uid)
        if not expiry:
            return await c.send_message(uid, "❌ You don't have an active premium plan.")
        expiry_ist = expiry + timedelta(hours=5, minutes=30)
        return await c.send_message(uid, f"💳 Your plan is active until: {expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')} (IST)")
    elif data == "cmd_merge_pdf":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await process_merge_pdf_interactive(c, cq.message.chat.id, uid)
        return
    elif data == "cmd_split_pdf":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await process_split_pdf_interactive(c, cq.message.chat.id, uid)
        return
    elif data == "cmd_contact_owner":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await c.send_message(uid, "✍️ Send the message you want to forward to the owner. You have 2 minutes.")
        try:
            try:
                msg = await c.listen(chat_id=uid, timeout=120)
            except (asyncio.TimeoutError, ListenerTimeout):
                return await c.send_message(uid, "⚠️ Timeout! No message received.")
            if msg is None or (not getattr(msg, "text", None) and not getattr(msg, "document", None)):
                return await c.send_message(uid, "⚠️ Empty message or timeout. Cancelled.")
            payload = f"📩 Message from {cq.from_user.first_name} (id={uid}):\n\n"
            if getattr(msg, "text", None): payload += msg.text
            if getattr(msg, "document", None): payload += f"\n\n[User also sent document: {msg.document.file_name}]"
            for oid in OWNER_ID:
                try:
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Reply to this user", callback_data=f"reply_user_{uid}")]])
                    await app.send_message(oid, payload, reply_markup=kb)
                except Exception:
                    pass
            return await c.send_message(uid, "✅ Your message was forwarded to the owner(s).")
        except Exception:
            return await c.send_message(uid, "⏳ Timeout or error. Try again later.")
    elif data == "cmd_help":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        return await c.send_message(uid, HELP_TEXT)
    elif data == "cmd_settings":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await show_settings_inplace(c, cq)
        return

    # Merge process options
    elif data.startswith("merge_"):
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        parts = data.split("_")
        if len(parts) < 3:
            return
        
        # Handle different button types
        if len(parts) == 4:  # For "wm_link" option
            option = f"{parts[1]}_{parts[2]}"  # "wm_link"
            target_user_id = int(parts[3])
        else:  # For "link", "wm", "none" options
            option = parts[1]
            target_user_id = int(parts[2])
        
        if target_user_id != uid:
            try:
                await cq.answer("❌ Not your process!", show_alert=True)
            except QueryIdInvalid:
                pass
            return
        
        if uid not in user_states or user_states[uid]['type'] != 'merge':
            try:
                await cq.answer("❌ No active merge process!", show_alert=True)
            except QueryIdInvalid:
                pass
            return
        
        merge_data = user_states[uid]
        
        # Create temp directory for processing
        import tempfile
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Merge PDFs
            output_path = os.path.join(temp_dir, merge_data.get('output_name', 'merged_output.pdf'))
            pdf_paths = [item['path'] for item in merge_data['pdfs']]
            
            await cq.message.edit_text("🔄 Merging PDFs...")
            merge_pdfs(pdf_paths, output_path)
            
            # Apply selected options
            defaults = get_user_defaults(uid) or {}
            
            if option == "wm_link":
                # Apply both watermark and link
                wm_text = defaults.get("default_watermark", DEFAULT_WATERMARK)
                link_text = defaults.get("default_link", DEFAULT_LINK)
                temp_link = os.path.join(temp_dir, "temp_link.pdf")
                temp_final = os.path.join(temp_dir, "temp_final.pdf")
                
                # First add link
                pdf_add_link(output_path, temp_link, link_text)
                # Then add watermark
                pdf_watermark(temp_link, temp_final, wm_text, 
                            size_override=defaults.get("default_wm_size"),
                            color_override=defaults.get("default_wm_color"),
                            alpha_override=defaults.get("default_wm_alpha"),
                            position_override=defaults.get("default_wm_position"))
                os.replace(temp_final, output_path)
                
            elif option == "wm":
                wm_text = defaults.get("default_watermark", DEFAULT_WATERMARK)
                temp_out = os.path.join(temp_dir, "temp_wm.pdf")
                pdf_watermark(output_path, temp_out, wm_text, 
                            size_override=defaults.get("default_wm_size"),
                            color_override=defaults.get("default_wm_color"),
                            alpha_override=defaults.get("default_wm_alpha"),
                            position_override=defaults.get("default_wm_position"))
                os.replace(temp_out, output_path)
            
            elif option == "link":
                link_text = defaults.get("default_link", DEFAULT_LINK)
                temp_out = os.path.join(temp_dir, "temp_link.pdf")
                pdf_add_link(output_path, temp_out, link_text)
                os.replace(temp_out, output_path)
            
            # Send to user
            await cq.message.edit_text("📤 Sending merged PDF...")
            output_filename = os.path.basename(output_path)
            with open(output_path, "rb") as f:
                await c.send_document(uid, f, caption=f"**{output_filename}**", file_name=output_filename)
            
            # Send to PROCESSED channel
            caption_channel = f"**{output_filename}**\n\n✅ Merged {len(pdf_paths)} PDFs for {cq.from_user.first_name} (id={uid})"
            await send_to_processed_channel(output_path, caption_channel)
            
            await cq.message.delete()
            
        except Exception as e:
            log.exception("Merge error")
            await cq.message.edit_text(f"❌ Error: {str(e)[:200]}")
        finally:
            # Cleanup
            try:
                shutil.rmtree(temp_dir)
                for item in merge_data['pdfs']:
                    if os.path.exists(item['path']):
                        os.remove(item['path'])
            except:
                pass
            
            if uid in user_states:
                del user_states[uid]

    # Split process options
    elif data.startswith("split_"):
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        parts = data.split("_")
        if len(parts) < 3:
            return
        
        # Handle different button types
        if len(parts) == 4:  # For "wm_link" option
            option = f"{parts[1]}_{parts[2]}"  # "wm_link"
            target_user_id = int(parts[3])
        else:  # For "link", "wm", "none" options
            option = parts[1]
            target_user_id = int(parts[2])
        
        if target_user_id != uid:
            try:
                await cq.answer("❌ Not your process!", show_alert=True)
            except QueryIdInvalid:
                pass
            return
        
        if uid not in user_states or user_states[uid]['type'] != 'split':
            try:
                await cq.answer("❌ No active split process!", show_alert=True)
            except QueryIdInvalid:
                pass
            return
        
        split_data = user_states[uid]
        
        import tempfile
        temp_dir = tempfile.mkdtemp()
        
        try:
            await cq.message.edit_text("🔄 Splitting PDF...")
            
            # Split PDF
            if split_data['split_type'] == 'equal':
                output_files = split_pdf_equal_parts(
                    split_data['pdf_path'], 
                    temp_dir, 
                    split_data['num_parts']
                )
            else:
                output_files = split_pdf_by_pages(
                    split_data['pdf_path'], 
                    temp_dir, 
                    split_data['page_ranges']
                )
            
            # Apply selected options to each split part
            defaults = get_user_defaults(uid) or {}
            processed_files = []
            
            base_name = os.path.splitext(split_data['original_name'])[0]
            
            for i, file_path in enumerate(output_files):
                # Create appropriate filename with page numbers
                if split_data['split_type'] == 'equal':
                    # For equal parts
                    part_name = f"{base_name}_part{i+1}_of_{len(output_files)}.pdf"
                else:
                    # For page ranges
                    start_page, end_page = split_data['page_ranges'][i]
                    if start_page == end_page:
                        part_name = f"{base_name}_page_{start_page}.pdf"
                    else:
                        part_name = f"{base_name}_pages_{start_page}_to_{end_page}.pdf"
                
                final_path = os.path.join(temp_dir, part_name)
                
                # Apply options
                if option == "wm_link":
                    # Apply both watermark and link
                    wm_text = defaults.get("default_watermark", DEFAULT_WATERMARK)
                    link_text = defaults.get("default_link", DEFAULT_LINK)
                    temp_link = os.path.join(temp_dir, f"temp_link_{i}.pdf")
                    
                    # First add link
                    pdf_add_link(file_path, temp_link, link_text)
                    # Then add watermark
                    pdf_watermark(temp_link, final_path, wm_text,
                                size_override=defaults.get("default_wm_size"),
                                color_override=defaults.get("default_wm_color"),
                                alpha_override=defaults.get("default_wm_alpha"),
                                position_override=defaults.get("default_wm_position"))
                    
                elif option == "wm":
                    wm_text = defaults.get("default_watermark", DEFAULT_WATERMARK)
                    pdf_watermark(file_path, final_path, wm_text,
                                size_override=defaults.get("default_wm_size"),
                                color_override=defaults.get("default_wm_color"),
                                alpha_override=defaults.get("default_wm_alpha"),
                                position_override=defaults.get("default_wm_position"))
                    
                elif option == "link":
                    link_text = defaults.get("default_link", DEFAULT_LINK)
                    pdf_add_link(file_path, final_path, link_text)
                    
                else:
                    shutil.copy(file_path, final_path)
                
                processed_files.append(final_path)
            
            # Send ALL files to user as a group
            await cq.message.edit_text(f"📤 Sending {len(processed_files)} split PDFs...")
            
            for file_path in processed_files:
                part_name = os.path.basename(file_path)
                with open(file_path, "rb") as f:
                    await c.send_document(uid, f, caption=f"**{part_name}**", file_name=part_name)
                
                # Send to PROCESSED channel
                caption_channel = f"**{part_name}**\n\n✅ Split part for {cq.from_user.first_name} (id={uid})"
                await send_to_processed_channel(file_path, caption_channel)
            
            await cq.message.delete()
            
        except Exception as e:
            log.exception("Split error")
            await cq.message.edit_text(f"❌ Error: {str(e)[:200]}")
        finally:
            # Cleanup
            try:
                shutil.rmtree(temp_dir)
                if os.path.exists(split_data['pdf_path']):
                    os.remove(split_data['pdf_path'])
            except:
                pass
            
            if uid in user_states:
                del user_states[uid]

    # ---------- PDF Settings handlers (in-place editing) ----------
    elif data.startswith("set_"):
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        uid = cq.from_user.id

        if data == "set_wm":
            # Edit current message to ask for input
            await c.edit_message_text(
                chat_id=cq.message.chat.id,
                message_id=cq.message.id,
                text="Send the watermark text (will be saved).",
                reply_markup=None
            )
            try:
                msg = await c.listen(chat_id=uid, timeout=120)
                if msg is None or not msg.text:
                    await show_settings_inplace(c, cq)
                    return
                set_user_defaults(uid, watermark=msg.text.strip())
                await show_settings_inplace(c, cq)
            except Exception:
                await show_settings_inplace(c, cq)
            return

        elif data == "set_link":
            await c.edit_message_text(
                chat_id=cq.message.chat.id,
                message_id=cq.message.id,
                text="Send the default link (full URL).",
                reply_markup=None
            )
            try:
                msg = await c.listen(chat_id=uid, timeout=120)
                if msg is None or not msg.text:
                    await show_settings_inplace(c, cq)
                    return
                set_user_defaults(uid, link=msg.text.strip())
                await show_settings_inplace(c, cq)
            except Exception:
                await show_settings_inplace(c, cq)
            return

        elif data == "set_both":
            await c.edit_message_text(
                chat_id=cq.message.chat.id,
                message_id=cq.message.id,
                text="Send the watermark text:",
                reply_markup=None
            )
            try:
                wm = await c.listen(chat_id=uid, timeout=120)
                if wm is None or not wm.text:
                    await show_settings_inplace(c, cq)
                    return
                # Ask for link in same message
                await c.edit_message_text(
                    chat_id=cq.message.chat.id,
                    message_id=cq.message.id,
                    text="Send the default link:",
                    reply_markup=None
                )
                lk = await c.listen(chat_id=uid, timeout=120)
                if lk is None or not lk.text:
                    await show_settings_inplace(c, cq)
                    return
                set_user_defaults(uid, watermark=wm.text.strip(), link=lk.text.strip())
                await show_settings_inplace(c, cq)
            except Exception:
                await show_settings_inplace(c, cq)
            return

        elif data == "set_clear":
            set_user_defaults(uid, watermark=None, link=None, size=None, color=None, alpha=None, position=None)
            user_settings.delete_one({"user_id": uid})
            await show_settings_inplace(c, cq)
            return

        elif data == "set_size":
            await c.edit_message_text(
                chat_id=cq.message.chat.id,
                message_id=cq.message.id,
                text="Send watermark size (numeric, e.g., 20):",
                reply_markup=None
            )
            try:
                msg = await c.listen(chat_id=uid, timeout=120)
                if msg is None or not msg.text:
                    await show_settings_inplace(c, cq)
                    return
                if msg.text.strip().isdigit():
                    set_user_defaults(uid, size=int(msg.text.strip()))
                else:
                    await c.send_message(uid, "Invalid input (must be a number).")
                await show_settings_inplace(c, cq)
            except Exception:
                await show_settings_inplace(c, cq)
            return

        elif data == "set_color":
            # Show color keyboard (already in-place)
            try:
                await c.edit_message_text(
                    chat_id=cq.message.chat.id,
                    message_id=cq.message.id,
                    text="Choose watermark color:",
                    reply_markup=color_keyboard()
                )
            except Exception:
                await c.send_message(uid, "Choose watermark color:", reply_markup=color_keyboard())
            return

        elif data == "set_alpha":
            await c.edit_message_text(
                chat_id=cq.message.chat.id,
                message_id=cq.message.id,
                text="Send transparency percentage (0-100, 0=fully transparent, 100=fully opaque):",
                reply_markup=None
            )
            try:
                msg = await c.listen(chat_id=uid, timeout=120)
                if msg is None or not msg.text:
                    await show_settings_inplace(c, cq)
                    return
                try:
                    alpha = float(msg.text.strip())
                    alpha = max(0.0, min(1.0, alpha / 100.0))
                    set_user_defaults(uid, alpha=alpha)
                except ValueError:
                    await c.send_message(uid, "Invalid input (must be a number).")
                await show_settings_inplace(c, cq)
            except Exception:
                await show_settings_inplace(c, cq)
            return

        elif data == "set_position":
            # Show position keyboard (already in-place)
            try:
                await c.edit_message_text(
                    chat_id=cq.message.chat.id,
                    message_id=cq.message.id,
                    text="Choose watermark position:",
                    reply_markup=pdf_position_keyboard()
                )
            except Exception:
                await c.send_message(uid, "Choose watermark position:", reply_markup=pdf_position_keyboard())
            return

        elif data == "set_back":
            await show_mainmenu_inplace(c, cq)
            return

    # Color picks (PDF settings)
    elif data.startswith("color_"):
        color = data.split("_", 1)[1]
        set_user_defaults(uid, color=color)
        try:
            await cq.answer(f"Color set: {color}")
        except QueryIdInvalid:
            pass
        await show_settings_inplace(c, cq)
        return

    # PDF Position picks
    elif data.startswith("pdf_pos_"):
        pos_map = {
            "pdf_pos_tl": "top_left",
            "pdf_pos_tr": "top_right",
            "pdf_pos_bl": "bottom_left",
            "pdf_pos_br": "bottom_right",
            "pdf_pos_c": "center",
            "pdf_pos_d": "diag_tl_br",
            "pdf_pos_d2": "diag_bl_tr",
        }
        if data in pos_map:
            set_user_defaults(uid, position=pos_map[data])
            try:
                await cq.answer(f"Position set to {pos_map[data].replace('_', ' ').title()}")
            except QueryIdInvalid:
                pass
            await show_settings_inplace(c, cq)
        return

    # Image settings handlers (already in-place)
    elif data == "img_back":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await show_mainmenu_inplace(c, cq)
        return
    
    elif data == "img_size":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await c.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text="Send size factor (0.5 for small, 1.0 for normal, 2.0 for large):",
            reply_markup=None
        )
        try:
            msg = await c.listen(chat_id=uid, timeout=120)
            if msg is None or not msg.text:
                await show_image_settings_inplace(c, cq)
                return
            try:
                size = float(msg.text.strip())
                update_image_setting(uid, "size_factor", size)
            except ValueError:
                await c.send_message(uid, "❌ Invalid number")
            await show_image_settings_inplace(c, cq)
        except Exception:
            await show_image_settings_inplace(c, cq)
        return
    
    elif data.startswith("col_"):
        color_map = {
            "col_white": [255, 255, 255],
            "col_black": [0, 0, 0],
            "col_red": [255, 0, 0],
            "col_blue": [0, 0, 255],
            "col_green": [0, 255, 0],
            "col_yellow": [255, 255, 0],
        }
        if data in color_map:
            update_image_setting(uid, "color", color_map[data])
            try:
                await cq.answer(f"Color set to {data.replace('col_', '')}")
            except QueryIdInvalid:
                pass
            await show_image_settings_inplace(c, cq)
        return
    
    elif data == "img_color":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await c.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text="Select color:",
            reply_markup=image_color_keyboard()
        )
        return
    
    elif data == "img_position":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await c.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text="Select position:",
            reply_markup=image_position_keyboard()
        )
        return
    
    elif data.startswith("pos_"):
        pos_map = {
            "pos_tl": "top_left",
            "pos_tr": "top_right",
            "pos_bl": "bottom_left",
            "pos_br": "bottom_right",
            "pos_c": "center",
            "pos_d": "diag_tl_br",
            "pos_d2": "diag_bl_tr",
        }
        if data in pos_map:
            update_image_setting(uid, "position", pos_map[data])
            try:
                await cq.answer(f"Position set to {pos_map[data]}")
            except QueryIdInvalid:
                pass
            await show_image_settings_inplace(c, cq)
        return
    
    elif data == "img_alpha":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await c.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text="Send transparency percentage (0-100, 0=fully transparent, 100=fully opaque):",
            reply_markup=None
        )
        try:
            msg = await c.listen(chat_id=uid, timeout=120)
            if msg is None or not msg.text:
                await show_image_settings_inplace(c, cq)
                return
            try:
                alpha = int(msg.text.strip())
                alpha = max(0, min(100, alpha))
                update_image_setting(uid, "alpha", int(alpha * 2.55))
            except ValueError:
                await c.send_message(uid, "❌ Invalid number")
            await show_image_settings_inplace(c, cq)
        except Exception:
            await show_image_settings_inplace(c, cq)
        return
    
    elif data == "img_font":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await c.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text="Select font:",
            reply_markup=image_font_keyboard()
        )
        return
    
    elif data.startswith("font_"):
        font_key = data.replace("font_", "")
        from utils.image_utils import FONT_STYLES
        if font_key in FONT_STYLES:
            update_image_setting(uid, "font_key", font_key)
            try:
                await cq.answer(f"Font set to {FONT_STYLES[font_key][0]}")
            except QueryIdInvalid:
                pass
            await show_image_settings_inplace(c, cq)
        return
    
    elif data == "img_transform":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await c.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text="Select text transform:",
            reply_markup=image_transform_keyboard()
        )
        return
    
    elif data.startswith("t_"):
        transform_map = {
            "t_norm": "normal",
            "t_up": "upper",
            "t_low": "lower",
            "t_sp": "spaced",
            "t_box": "boxed",
        }
        if data in transform_map:
            update_image_setting(uid, "transform", transform_map[data])
            try:
                await cq.answer(f"Transform set to {transform_map[data]}")
            except QueryIdInvalid:
                pass
            await show_image_settings_inplace(c, cq)
        return
    
    elif data == "img_default_text":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await c.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text="Send default watermark text for images:",
            reply_markup=None
        )
        try:
            msg = await c.listen(chat_id=uid, timeout=120)
            if msg is None or not msg.text:
                await show_image_settings_inplace(c, cq)
                return
            update_image_setting(uid, "default_text", msg.text.strip())
            await show_image_settings_inplace(c, cq)
        except Exception:
            await show_image_settings_inplace(c, cq)
        return

    # ---------- Logo settings callbacks (in-place) ----------
    elif data == "logo_back":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await show_mainmenu_inplace(c, cq)
        return

    elif data == "logo_set_size":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await c.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text="Send size factor (e.g., 0.2 for 20% of page width):",
            reply_markup=None
        )
        try:
            msg = await c.listen(chat_id=uid, timeout=120)
            if msg is None or not msg.text:
                await show_logo_settings_inplace(c, cq)
                return
            try:
                size = float(msg.text.strip())
                set_logo_defaults(uid, size=size)
            except ValueError:
                await c.send_message(uid, "❌ Invalid number.")
            await show_logo_settings_inplace(c, cq)
        except Exception:
            await show_logo_settings_inplace(c, cq)
        return

    elif data == "logo_set_position":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        try:
            await c.edit_message_text(
                chat_id=cq.message.chat.id,
                message_id=cq.message.id,
                text="Select logo position:",
                reply_markup=logo_position_keyboard()
            )
        except Exception:
            await c.send_message(uid, "Select logo position:", reply_markup=logo_position_keyboard())
        return

    elif data.startswith("logo_pos_"):
        pos_map = {
            "logo_pos_tl": "top_left",
            "logo_pos_tr": "top_right",
            "logo_pos_bl": "bottom_left",
            "logo_pos_br": "bottom_right",
            "logo_pos_c": "center"
        }
        if data in pos_map:
            set_logo_defaults(uid, position=pos_map[data])
            try:
                await cq.answer(f"Position set to {pos_map[data].replace('_', ' ').title()}")
            except QueryIdInvalid:
                pass
            await show_logo_settings_inplace(c, cq)
        return

    elif data == "logo_set_alpha":
        try:
            await cq.answer()
        except QueryIdInvalid:
            pass
        await c.edit_message_text(
            chat_id=cq.message.chat.id,
            message_id=cq.message.id,
            text="Send transparency value (0.0 = fully transparent, 1.0 = fully opaque):",
            reply_markup=None
        )
        try:
            msg = await c.listen(chat_id=uid, timeout=120)
            if msg is None or not msg.text:
                await show_logo_settings_inplace(c, cq)
                return
            try:
                alpha = float(msg.text.strip())
                alpha = max(0.0, min(1.0, alpha))
                set_logo_defaults(uid, alpha=alpha)
            except ValueError:
                await c.send_message(uid, "❌ Invalid number.")
            await show_logo_settings_inplace(c, cq)
        except Exception:
            await show_logo_settings_inplace(c, cq)
        return

    # Owner reply handler
    elif data.startswith("reply_user_"):
        try:
            target_uid = int(data.split("_", 2)[2])
        except Exception:
            try:
                await cq.answer("Invalid.")
            except QueryIdInvalid:
                pass
            return
        owner_id = cq.from_user.id
        try:
            await cq.answer("Type the reply; send /cancel to stop.")
        except QueryIdInvalid:
            pass
        try:
            try:
                owner_msg = await c.listen(chat_id=owner_id, timeout=120)
            except (asyncio.TimeoutError, ListenerTimeout):
                await c.send_message(owner_id, "⏳ Timeout! No reply received.")
                return
        except Exception:
            await c.send_message(owner_id, "Error or cancelled.")
            return
        if owner_msg is None:
            return await c.send_message(owner_id, "⏳ Timeout! No reply received.")
        if getattr(owner_msg, "text", "") == "/cancel":
            return await c.send_message(owner_id, "Reply cancelled.")
        forward_payload = f"📩 Message from owner {cq.from_user.first_name}:\n\n"
        if getattr(owner_msg, "text", None):
            forward_payload += owner_msg.text
        if getattr(owner_msg, "document", None):
            try: 
                await app.send_message(target_uid, forward_payload)
            except: 
                pass
            try: 
                await app.send_document(target_uid, owner_msg.document.file_id, caption="📎 Attached by owner")
            except: 
                pass
            return await c.send_message(owner_id, "✅ Your reply and attachment forwarded (or failed).")
        else:
            try:
                await app.send_message(target_uid, forward_payload)
            except Exception:
                return await c.send_message(owner_id, "Failed to deliver message to user (maybe blocked).")
            return await c.send_message(owner_id, "✅ Your reply has been forwarded.")

    try:
        await cq.answer()
    except QueryIdInvalid:
        pass

# ---------- Commands with reply support ----------
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
    record_user(m.from_user.id)
    kb = get_main_keyboard_for_user(m.from_user.id)
    await m.reply("👋 Welcome! Choose what you want to do:", reply_markup=kb)

# PDF command with reply support
@app.on_message(filters.command("pdf") & filters.private & filters.reply)
async def pdf_cmd_reply(c, m):
    record_user(m.from_user.id)
    replied_msg = m.reply_to_message
    if not replied_msg or not replied_msg.document or not replied_msg.document.file_name.lower().endswith(".pdf"):
        await m.reply("❌ Please reply to a PDF file.")
        return
    await process_with_replied_pdf(c, m.chat.id, m.from_user.id, replied_msg, "wm_link")

@app.on_message(filters.command("pdf") & filters.private & ~filters.reply)
async def pdf_cmd(c, m):
    record_user(m.from_user.id)
    await process_start_interactive(c, m.chat.id, m.from_user.id)

# Link command with reply support
@app.on_message(filters.command("link") & filters.private & filters.reply)
async def link_cmd_reply(c, m):
    record_user(m.from_user.id)
    replied_msg = m.reply_to_message
    if not replied_msg or not replied_msg.document or not replied_msg.document.file_name.lower().endswith(".pdf"):
        await m.reply("❌ Please reply to a PDF file.")
        return
    await process_with_replied_pdf(c, m.chat.id, m.from_user.id, replied_msg, "link")

@app.on_message(filters.command("link") & filters.private & ~filters.reply)
async def link_cmd(c, m):
    record_user(m.from_user.id)
    await process_link_interactive(c, m.chat.id, m.from_user.id)

# Watermark command with reply support
@app.on_message(filters.command("watermark") & filters.private & filters.reply)
async def watermark_cmd_reply(c, m):
    record_user(m.from_user.id)
    replied_msg = m.reply_to_message
    if not replied_msg or not replied_msg.document or not replied_msg.document.file_name.lower().endswith(".pdf"):
        await m.reply("❌ Please reply to a PDF file.")
        return
    await process_with_replied_pdf(c, m.chat.id, m.from_user.id, replied_msg, "wm")

@app.on_message(filters.command("watermark") & filters.private & ~filters.reply)
async def watermark_cmd(c, m):
    record_user(m.from_user.id)
    await process_watermark_interactive(c, m.chat.id, m.from_user.id)

# Logo command
@app.on_message(filters.command("logo") & filters.private & filters.reply)
async def logo_cmd_reply(c, m):
    record_user(m.from_user.id)
    await m.reply("Please use /logo without reply to start the interactive logo watermark process.")

@app.on_message(filters.command("logo") & filters.private & ~filters.reply)
async def logo_cmd(c, m):
    record_user(m.from_user.id)
    await process_logo_watermark_interactive(c, m.chat.id, m.from_user.id)

# Image command with reply support
@app.on_message(filters.command("image") & filters.private & filters.reply)
async def image_cmd_reply(c, m):
    record_user(m.from_user.id)
    replied_msg = m.reply_to_message
    # Check if replied message has an image
    is_image = False
    if replied_msg.photo:
        is_image = True
    elif replied_msg.document:
        mime_type = replied_msg.document.mime_type or ""
        if mime_type.startswith('image/'):
            is_image = True
    
    if not is_image:
        await m.reply("❌ Please reply to an image file.")
        return
    
    # Process image watermark
    if not is_premium_user(m.from_user.id):
        await m.reply("⚠️ Only premium users can use this feature.")
        return
    
    try:
        ask_msg = await c.send_message(m.chat.id, "📥 Downloading image...")
        
        image_path = await replied_msg.download()
        with open(image_path, 'rb') as f:
            img_bytes = f.read()
        
        # Get original filename
        if replied_msg.document:
            orig_filename = get_clean_output_filename(replied_msg.document.file_name)
        else:
            orig_filename = f"image.jpg"
        
        # Forward original to original channel (without extra caption)
        await forward_to_original_channel(replied_msg)
        
        # Check if user has default text set
        image_settings = get_image_settings(m.from_user.id)
        default_text = image_settings.get('default_text')
        
        if default_text:
            watermark_text = default_text
            await ask_msg.edit_text("⚙️ Adding watermark to image...")
        else:
            await ask_msg.edit_text(f"✍️ Send watermark text (or type 'default' to use '{DEFAULT_WATERMARK}'):")
            try:
                text_msg = await c.listen(chat_id=m.chat.id, timeout=IMAGE_TIMEOUT)
            except (asyncio.TimeoutError, ListenerTimeout):
                watermark_text = DEFAULT_WATERMARK
                await ask_msg.edit_text(f"⏳ Timeout! Using default text: {watermark_text}")
            else:
                if text_msg is None or not getattr(text_msg, 'text', None):
                    watermark_text = DEFAULT_WATERMARK
                    await ask_msg.edit_text(f"⏳ Timeout! Using default text: {watermark_text}")
                else:
                    user_text = text_msg.text.strip()
                    if user_text.lower() == 'default':
                        watermark_text = DEFAULT_WATERMARK
                    else:
                        watermark_text = user_text
                    
                    try:
                        await text_msg.delete()
                    except:
                        pass
                await ask_msg.edit_text("⚙️ Adding watermark to image...")
        
        watermarked_bytes = create_image_watermark(img_bytes, watermark_text, image_settings)
        
        # Keep original filename with watermark prefix
        output_filename = f"watermarked_{orig_filename}"
        
        with open(output_filename, 'wb') as f:
            f.write(watermarked_bytes)
        
        caption = f"**{output_filename}**\n\n✅ Image watermarked with: {watermark_text}"
        await c.send_document(m.chat.id, output_filename, caption=caption, file_name=output_filename)
        
        # Send to PROCESSED channel
        caption_channel = f"**{output_filename}**\n\n✅ Watermarked Image for {replied_msg.from_user.first_name} (id={replied_msg.from_user.id})\nText: {watermark_text}"
        await send_to_processed_channel(output_filename, caption_channel)
        
        await ask_msg.delete()
        
        # Cleanup
        try:
            os.remove(image_path)
            os.remove(output_filename)
        except:
            pass
        
    except Exception as e:
        log.exception("Image watermark error")
        await ask_msg.delete()
        await c.send_message(m.chat.id, f"❌ Error processing image: {str(e)[:200]}")

@app.on_message(filters.command("image") & filters.private & ~filters.reply)
async def image_cmd(c, m):
    record_user(m.from_user.id)
    await process_image_watermark_interactive(c, m.chat.id, m.from_user.id)

# Split command with reply support
@app.on_message(filters.command("split") & filters.private & filters.reply)
async def split_cmd_reply(c, m):
    record_user(m.from_user.id)
    replied_msg = m.reply_to_message
    if not replied_msg or not replied_msg.document or not replied_msg.document.file_name.lower().endswith(".pdf"):
        await m.reply("❌ Please reply to a PDF file.")
        return
    
    # Store the replied PDF for split processing
    user_id = m.from_user.id
    pdf_path = await replied_msg.download()
    orig_name = get_clean_output_filename(replied_msg.document.file_name)
    
    # Forward original to original channel (without extra caption)
    await forward_to_original_channel(replied_msg)
    
    user_states[user_id] = {
        'type': 'split',
        'pdf_path': pdf_path,
        'original_name': orig_name,
        'step': 'waiting_for_split_info'
    }
    
    ask_msg = await c.send_message(m.chat.id, "How do you want to split?\n\n1. Enter page ranges (e.g., 1-5,6-10,11-15)\n2. Enter number of equal parts (e.g., 3)")
    
    try:
        try:
            split_msg = await c.listen(chat_id=m.chat.id, timeout=300)
        except (asyncio.TimeoutError, ListenerTimeout):
            await ask_msg.delete()
            if user_id in user_states:
                del user_states[user_id]
            return await c.send_message(m.chat.id, "⏳ Timeout! No split information received.")
        
        # Check for None response
        if split_msg is None or not getattr(split_msg, 'text', None):
            await ask_msg.delete()
            if user_id in user_states:
                del user_states[user_id]
            return await c.send_message(m.chat.id, "⏳ Timeout! No split information received.")
        
        split_info = split_msg.text.strip()
        
        if split_info.isdigit():
            # Equal parts
            num_parts = int(split_info)
            if num_parts < 2:
                await ask_msg.delete()
                del user_states[user_id]
                return await c.send_message(m.chat.id, "❌ Need at least 2 parts. Cancelled.")
            
            user_states[user_id]['split_type'] = 'equal'
            user_states[user_id]['num_parts'] = num_parts
        else:
            # Page ranges
            ranges = split_info.split(',')
            page_ranges = []
            for r in ranges:
                try:
                    if '-' in r:
                        start, end = map(int, r.split('-'))
                        page_ranges.append((start, end))
                    else:
                        page_num = int(r)
                        page_ranges.append((page_num, page_num))
                except:
                    continue
            
            if not page_ranges:
                await ask_msg.delete()
                del user_states[user_id]
                return await c.send_message(m.chat.id, "❌ Invalid page ranges. Cancelled.")
            
            user_states[user_id]['split_type'] = 'ranges'
            user_states[user_id]['page_ranges'] = page_ranges
        
        await ask_msg.edit_text("Select what to add to split PDFs:", reply_markup=process_options_keyboard("split", user_id))
        
    except Exception as e:
        log.exception(f"split_cmd_reply error: {e}")
        await ask_msg.delete()
        if user_id in user_states:
            del user_states[user_id]
        await c.send_message(m.chat.id, f"❌ Error during split process: {str(e)[:200]}")

@app.on_message(filters.command("split") & filters.private & ~filters.reply)
async def split_cmd(c, m):
    record_user(m.from_user.id)
    await process_split_pdf_interactive(c, m.chat.id, m.from_user.id)

# Merge command (no reply needed)
@app.on_message(filters.command("merge") & filters.private)
async def merge_cmd(c, m):
    record_user(m.from_user.id)
    await process_merge_pdf_interactive(c, m.chat.id, m.from_user.id)

# Other commands
@app.on_message(filters.command("help") & filters.private)
async def help_cmd(c, m):
    record_user(m.from_user.id)
    await m.reply(HELP_TEXT)

@app.on_message(filters.command("settings") & filters.private)
async def settings_cmd(c, m):
    record_user(m.from_user.id)
    await show_settings_inplace(c, m)

@app.on_message(filters.command("image_settings") & filters.private)
async def image_settings_cmd(c, m):
    record_user(m.from_user.id)
    settings = get_image_settings(m.from_user.id)
    default_text = settings.get('default_text', '(not set)')
    text = (
        f"🖼️ Image Watermark Settings:\n\n"
        f"Size: {settings.get('size_factor', 1.0)}x\n"
        f"Color: RGB{settings.get('color', [255,255,255])}\n"
        f"Position: {settings.get('position', 'bottom_right')}\n"
        f"Transparency: {settings.get('alpha', 220)}/255\n"
        f"Font: {settings.get('font_key', 'sans_default')}\n"
        f"Transform: {settings.get('transform', 'normal')}\n"
        f"Default Text: {default_text}\n"
    )
    await m.reply(text, reply_markup=image_settings_keyboard())

# Logo settings command
@app.on_message(filters.command("logo_settings") & filters.private)
async def logo_settings_cmd(c, m):
    record_user(m.from_user.id)
    await show_logo_settings_inplace(c, m)

@app.on_message(filters.command("contact_owner") & filters.private)
async def contact_owner_cmd(c, m):
    record_user(m.from_user.id)
    await c.send_message(m.from_user.id, "✍️ Send the message you want to forward to the owner. You have 2 minutes.")
    try:
        try:
            msg = await c.listen(chat_id=m.chat.id, timeout=120)
        except (asyncio.TimeoutError, ListenerTimeout):
            return await c.send_message(m.from_user.id, "⚠️ Timeout! No message received.")
        if msg is None or (not getattr(msg, "text", None) and not getattr(msg, "document", None)):
            return await c.send_message(m.from_user.id, "⚠️ Empty message or timeout. Cancelled.")
        payload = f"📩 Message from {m.from_user.first_name} (id={m.from_user.id}):\n\n"
        if getattr(msg, "text", None):
            payload += msg.text
        if getattr(msg, "document", None):
            payload += f"\n\n[User also sent document: {msg.document.file_name}]"
        for oid in OWNER_ID:
            try:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("Reply to this user", callback_data=f"reply_user_{m.from_user.id}")]])
                await app.send_message(oid, payload, reply_markup=kb)
            except Exception:
                pass
        await c.send_message(m.from_user.id, "✅ Your message was forwarded to the owner(s).")
    except Exception:
        await c.send_message(m.from_user.id, "⏳ Timeout or error. Try again later.")

@app.on_message(filters.command("myplan") & filters.private)
async def myplan_cmd(c, m):
    record_user(m.from_user.id)
    expiry = get_premium_expiry(m.from_user.id)
    if not expiry:
        return await m.reply("❌ You don't have an active premium plan.")
    expiry_ist = expiry + timedelta(hours=5, minutes=30)
    await m.reply(f"💳 Your plan is active until: {expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')} (IST)")

@app.on_message(filters.command("transfer") & filters.private)
async def transfer_cmd(c, m):
    record_user(m.from_user.id)
    args = m.text.split()
    if len(args) != 2:
        return await m.reply("Usage: /transfer <target_user_id>")
    try:
        target = int(args[1])
        ok, res = transfer_premium(m.from_user.id, target)
        if ok:
            expiry = res
            expiry_ist = expiry + timedelta(hours=5, minutes=30)
            await m.reply(f"✅ Transfer successful. {target} now has premium until {expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')} (IST)")
            try: 
                await app.send_message(target, f"✅ You have received premium (transferred by {m.from_user.id}). Valid until {expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')} (IST)")
            except: 
                pass
        else:
            await m.reply(f"❌ Transfer failed: {res}")
    except Exception as e:
        await m.reply(f"Error: {e}")

# ---------- Owner/admin commands ----------
@app.on_message(filters.command("add") & filters.user(OWNER_ID))
async def add_premium_cmd(c, m):
    args = m.text.split()
    if len(args) != 4:
        return await m.reply("Usage: /add <user_id> <duration_value> <duration_unit>")
    try:
        target = int(args[1]); val = int(args[2]); unit = args[3].lower()
        ok, res = add_premium_user(target, val, unit)
        if ok:
            expiry = res; expiry_ist = expiry + timedelta(hours=5, minutes=30)
            await m.reply(f"✅ Added premium for {target}\nValid until: {expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')} (IST)")
            try: 
                await app.send_message(target, f"✅ You have been granted premium.\nValidity upto: {expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')} (IST)")
            except: 
                pass
        else:
            await m.reply(f"❌ Failed to add premium: {res}")
    except Exception as e:
        await m.reply(f"Error: {e}")

@app.on_message(filters.command("remove") & filters.user(OWNER_ID))
async def remove_premium_cmd(c, m):
    args = m.text.split()
    if len(args) != 2: 
        return await m.reply("Usage: /remove <user_id>")
    try:
        uid = int(args[1]); ok, err = remove_premium_user(uid)
        if ok:
            await m.reply(f"✅ Removed premium for {uid}")
            try: 
                await app.send_message(uid, "❌ Your premium has been revoked by the owner.")
            except: 
                pass
        else:
            await m.reply(f"❌ Error removing premium: {err}")
    except Exception as e:
        await m.reply(f"Error: {e}")

@app.on_message(filters.command("check") & filters.user(OWNER_ID))
async def check_cmd(c, m):
    args = m.text.split()
    if len(args) != 2: 
        return await m.reply("Usage: /check <user_id>")
    try:
        uid = int(args[1]); expiry = get_premium_expiry(uid)
        if not expiry: 
            return await m.reply("User is not premium.")
        expiry_ist = expiry + timedelta(hours=5, minutes=30)
        await m.reply(f"User {uid} premium until: {expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')} (IST)")
    except Exception as e:
        await m.reply(f"Error: {e}")

@app.on_message(filters.command("all_users") & filters.user(OWNER_ID))
async def all_users_cmd(c, m):
    try:
        all_users = list(users.find({}).sort("first_seen", -1).limit(1000))
        if not all_users: 
            return await m.reply("No users found.")
        
        user_list = []
        for user in all_users:
            uid = user.get("user_id")
            first_seen = user.get("first_seen", "Unknown")
            last_seen = user.get("last_seen", "Unknown")
            
            # Try to get user info
            try:
                user_info = await app.get_users(uid)
                name = f"{user_info.first_name or ''} {user_info.last_name or ''}".strip()
                if not name:
                    name = user_info.username or f"User {uid}"
            except:
                name = f"User {uid}"
            
            # Format date
            try:
                first_date = datetime.fromisoformat(first_seen).strftime('%d/%m/%Y %I:%M%p')
            except:
                first_date = first_seen
            
            user_list.append(f"{name} {uid}. {first_date}")
        
        text = "📋 All Bot Users:\n\n" + "\n".join(user_list)
        
        if len(text) > 4000:
            with open("all_users.txt", "w", encoding="utf-8") as f: 
                f.write("\n".join(user_list))
            await m.reply_document("all_users.txt", caption="List of all bot users")
            os.remove("all_users.txt")
        else:
            await m.reply(text)
    except Exception as e:
        await m.reply(f"Error: {e}")

@app.on_message(filters.command("premium_list") & filters.user(OWNER_ID))
async def premium_list_cmd(c, m):
    try:
        items = list_premium_users(limit=500)
        if not items: 
            return await m.reply("No premium users found.")
        parts = [f"{d.get('user_id')} → {d.get('expiry')}" for d in items]
        text = "📜 Premium users:\n\n" + "\n".join(parts)
        if len(text) > 4000:
            with open("premium_list.txt", "w", encoding="utf-8") as f: 
                f.write("\n".join(parts))
            await m.reply_document("premium_list.txt"); 
            os.remove("premium_list.txt")
        else:
            await m.reply(text)
    except Exception as e:
        await m.reply(f"Error: {e}")

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID) & filters.reply)
async def broadcast_cmd(c, m):
    if not m.reply_to_message:
        return await m.reply("❌ Please reply to a message to broadcast.")
    
    broadcast_message = m.reply_to_message
    await m.reply("📢 Broadcasting to premium users... This may take some time.")
    
    sent = 0
    failed = 0
    successful_users = []
    failed_users = []
    
    items = list_premium_users(limit=5000)
    for d in items:
        uid = d.get("user_id")
        try:
            await broadcast_message.copy(uid)
            sent += 1
            successful_users.append(uid)
            await asyncio.sleep(0.1)
        except Exception as e:
            failed += 1
            failed_users.append(uid)
    
    # Create report
    report = f"✅ Broadcast completed.\n\n📊 **Statistics:**\nSent: {sent}\nFailed: {failed}\n\n"
    
    if successful_users:
        report += "✅ **Successful Users:**\n"
        for uid in successful_users[:50]:  # Show first 50
            try:
                user_info = await app.get_users(uid)
                name = user_info.first_name or user_info.username or f"User {uid}"
                report += f"  {name} ({uid}) ✅\n"
            except:
                report += f"  User {uid} ✅\n"
    
    if failed_users:
        report += "\n❌ **Failed Users:**\n"
        for uid in failed_users[:50]:  # Show first 50
            try:
                user_info = await app.get_users(uid)
                name = user_info.first_name or user_info.username or f"User {uid}"
                report += f"  {name} ({uid}) ❌\n"
            except:
                report += f"  User {uid} ❌\n"
    
    await m.reply(report)

@app.on_message(filters.command("broadcast_all") & filters.user(OWNER_ID) & filters.reply)
async def broadcast_all_cmd(c, m):
    if not m.reply_to_message:
        return await m.reply("❌ Please reply to a message to broadcast.")
    
    broadcast_message = m.reply_to_message
    await m.reply("📢 Broadcasting to ALL users... This may take some time.")
    
    sent = 0
    failed = 0
    successful_users = []
    failed_users = []
    
    all_users = users.find({})
    for user in all_users:
        uid = user.get("user_id")
        try:
            await broadcast_message.copy(uid)
            sent += 1
            successful_users.append(uid)
            await asyncio.sleep(0.1)
        except Exception:
            failed += 1
            failed_users.append(uid)
    
    # Create report
    report = f"✅ Broadcast to ALL users completed.\n\n📊 **Statistics:**\nSent: {sent}\nFailed: {failed}\n\n"
    
    if successful_users:
        report += "✅ **Successful Users:**\n"
        for uid in successful_users[:50]:  # Show first 50
            try:
                user_info = await app.get_users(uid)
                name = user_info.first_name or user_info.username or f"User {uid}"
                report += f"  {name} ({uid}) ✅\n"
            except:
                report += f"  User {uid} ✅\n"
    
    if failed_users:
        report += "\n❌ **Failed Users:**\n"
        for uid in failed_users[:50]:  # Show first 50
            try:
                user_info = await app.get_users(uid)
                name = user_info.first_name or user_info.username or f"User {uid}"
                report += f"  {name} ({uid}) ❌\n"
            except:
                report += f"  User {uid} ❌\n"
    
    await m.reply(report)

@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def stats_cmd(c, m):
    try:
        total_users = users.count_documents({})
        premium_count = premium_users.count_documents({})
        await m.reply(f"📊 Bot Statistics:\n\nTotal Users: {total_users}\nPremium Users: {premium_count}")
    except Exception as e:
        await m.reply(f"Error: {e}")

# ---------- Initialize and Run ----------
@app.on_message(filters.command("init") & filters.user(OWNER_ID))
async def init_bot(c, m):
    """Initialize bot commands and send restart message"""
    await m.reply("🔄 Initializing bot...")
    await set_bot_commands()
    await send_restart_message()
    await m.reply("✅ Bot initialization complete!")

# ---------- Main function ----------
async def main():
    await app.start()
    log.info("Bot started successfully!")
    
    # Set bot commands
    await set_bot_commands()
    
    # Send restart message to owner only
    await send_restart_message()
    
    # Keep the bot running
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Create temp directory
    os.makedirs("temp_files", exist_ok=True)
    
    # Start Flask in a thread
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    log.info("Flask started on port %s", PORT)
    
    # Run the bot
    try:
        app.run(main())
    except Exception as e:
        log.error(f"Bot crashed: {e}")
        raise
