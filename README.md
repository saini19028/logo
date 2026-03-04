# PDF & Image Watermark Bot 🤖

A powerful Telegram bot that adds watermarks and clickable links to PDF files, and customizable watermarks to images. Built with Pyrogram and Flask.

![Bot Features](https://img.shields.io/badge/Features-PDF%20%26%20Image%20Watermarking-blue)
![Python](https://img.shields.io/badge/Python-3.10+-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## ✨ Features

### 📄 **PDF Features**
- ✅ Add clickable links to PDFs
- ✅ Add watermarks to PDFs (text with rotation)
- ✅ Auto-process incoming PDFs
- ✅ Customizable watermark size and color
- ✅ Store original and processed PDFs in channel
- ✅ Premium user management

### 🖼️ **Image Features**
- ✅ Add text watermarks to images
- ✅ Customizable settings:
  - Size adjustment (0.5x to 2.0x)
  - Color selection (Red, Blue, Green, etc.)
  - Position (Top-left, Bottom-right, Center, Diagonal)
  - Transparency control (0-100%)
  - Font selection (8+ font styles)
  - Text transformation (UPPER, lower, spaced, boxed)
- ✅ Auto-timeout with default watermark
- ✅ Store original and watermarked images in channel

### 👑 **Premium System**
- Tier-based access to features
- Time-based premium plans (minutes, hours, days, months, years)
- Premium transfer between users
- Owner management commands

### ⚙️ **User Features**
- Per-user default settings for PDFs
- Per-user image watermark settings
- Force subscription to channel
- Direct contact with owner
- Interactive settings menus

## 📦 Installation

### Prerequisites
- Python 3.10+
- MongoDB database
- Telegram Bot Token
- Telegram API ID & Hash

### Step-by-Step Setup

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/pdf-image-watermark-bot.git
cd pdf-image-watermark-bot
