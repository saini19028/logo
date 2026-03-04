# utils/image_utils.py
import os
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import textwrap

# Font styles mapping
FONT_STYLES = {
    'sans_default': ('Sans Serif', ['arial.ttf', 'Arial.ttf', 'DejaVuSans.ttf']),
    'sans_bold': ('Sans Bold', ['arialbd.ttf', 'Arial_Bold.ttf']),
    'serif': ('Serif', ['times.ttf', 'Times.ttf']),
    'serif_bold': ('Serif Bold', ['timesbd.ttf', 'Times_Bold.ttf']),
    'mono': ('Monospace', ['cour.ttf', 'Courier.ttf']),
    'modern': ('Modern', ['verdana.ttf', 'Verdana.ttf']),
    'script': ('Script', ['brushscr.ttf', 'Brush Script.ttf']),
}

def get_font_path(font_key='sans_default', size=20):
    """Get font path for given font key"""
    try:
        font_info = FONT_STYLES.get(font_key, FONT_STYLES['sans_default'])
        font_names = font_info[1]
        
        # Try system fonts first
        for font_name in font_names:
            try:
                # Try to load the font
                font = ImageFont.truetype(font_name, size)
                return font_name
            except IOError:
                continue
        
        # Fallback to default PIL font
        return None
    except Exception:
        return None

def transform_text(text, transform_type='normal'):
    """Transform text based on transform type"""
    if transform_type == 'upper':
        return text.upper()
    elif transform_type == 'lower':
        return text.lower()
    elif transform_type == 'spaced':
        return ' '.join(text)
    elif transform_type == 'boxed':
        return f"【 {text} 】"
    else:  # normal
        return text

def calculate_text_size(draw, text, font):
    """Calculate text size properly"""
    try:
        # Get bounding box
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        return width, height
    except:
        # Fallback method
        try:
            width = draw.textlength(text, font=font)
            height = font.size
            return width, height
        except:
            return 100, 20

def create_image_watermark(image_bytes, text, settings):
    """Add watermark to image with given settings"""
    try:
        # Open image
        image = Image.open(BytesIO(image_bytes))
        
        # Convert to RGBA if needed
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # Create a transparent layer for watermark
        txt_layer = Image.new('RGBA', image.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_layer)
        
        # Get settings
        size_factor = settings.get('size_factor', 1.0)
        color = settings.get('color', [255, 255, 255])
        position = settings.get('position', 'bottom_right')
        alpha = settings.get('alpha', 220)
        font_key = settings.get('font_key', 'sans_default')
        transform = settings.get('transform', 'normal')
        
        # Transform text
        transformed_text = transform_text(text, transform)
        
        # Calculate font size based on image dimensions
        img_width, img_height = image.size
        base_font_size = max(20, int(min(img_width, img_height) * 0.04))
        font_size = int(base_font_size * size_factor)
        
        # Get font
        font_path = get_font_path(font_key, font_size)
        if font_path:
            try:
                font = ImageFont.truetype(font_path, font_size)
            except:
                font = ImageFont.load_default()
        else:
            font = ImageFont.load_default()
        
        # Calculate text size
        text_width, text_height = calculate_text_size(draw, transformed_text, font)
        
        # Calculate position with margin
        margin = int(min(img_width, img_height) * 0.02)
        
        if position == 'top_left':
            x = margin
            y = margin
        elif position == 'top_right':
            x = img_width - text_width - margin
            y = margin
        elif position == 'bottom_left':
            x = margin
            y = img_height - text_height - margin
        elif position == 'bottom_right':
            x = img_width - text_width - margin
            y = img_height - text_height - margin
        elif position == 'center':
            x = (img_width - text_width) // 2
            y = (img_height - text_height) // 2
        elif position == 'diag_tl_br':
            # Diagonal from top-left to bottom-right
            angle = 45
            # We'll draw at center for diagonal
            x = img_width // 2 - text_width // 2
            y = img_height // 2 - text_height // 2
            # Create rotated text
            txt_rotated = Image.new('RGBA', image.size, (255, 255, 255, 0))
            draw_rotated = ImageDraw.Draw(txt_rotated)
            draw_rotated.text((x, y), transformed_text, font=font, fill=tuple(color) + (alpha,))
            txt_rotated = txt_rotated.rotate(angle, center=(img_width//2, img_height//2))
            image = Image.alpha_composite(image, txt_rotated)
            # Save to bytes
            output = BytesIO()
            if image.mode == 'RGBA':
                image.save(output, format='PNG')
            else:
                image.save(output, format='JPEG', quality=95)
            return output.getvalue()
        elif position == 'diag_bl_tr':
            # Diagonal from bottom-left to top-right
            angle = -45
            x = img_width // 2 - text_width // 2
            y = img_height // 2 - text_height // 2
            txt_rotated = Image.new('RGBA', image.size, (255, 255, 255, 0))
            draw_rotated = ImageDraw.Draw(txt_rotated)
            draw_rotated.text((x, y), transformed_text, font=font, fill=tuple(color) + (alpha,))
            txt_rotated = txt_rotated.rotate(angle, center=(img_width//2, img_height//2))
            image = Image.alpha_composite(image, txt_rotated)
            output = BytesIO()
            if image.mode == 'RGBA':
                image.save(output, format='PNG')
            else:
                image.save(output, format='JPEG', quality=95)
            return output.getvalue()
        else:  # Default to bottom_right
            x = img_width - text_width - margin
            y = img_height - text_height - margin
        
        # Draw text with proper alpha
        # Ensure alpha is within 0-255 range
        alpha = max(0, min(255, alpha))
        draw.text((x, y), transformed_text, font=font, fill=tuple(color) + (alpha,))
        
        # Combine image with watermark
        watermarked = Image.alpha_composite(image, txt_layer)
        
        # Convert back to RGB for JPEG saving
        if watermarked.mode == 'RGBA':
            watermarked = watermarked.convert('RGB')
        
        # Save to bytes
        output = BytesIO()
        watermarked.save(output, format='JPEG', quality=95)
        
        return output.getvalue()
        
    except Exception as e:
        raise Exception(f"Error creating image watermark: {str(e)}")
