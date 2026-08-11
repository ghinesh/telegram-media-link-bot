import os
import mimetypes
import threading
import requests
from flask import Flask, Response, abort

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Render automatically provides this variable.
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing")

if not BASE_URL:
    raise RuntimeError("RENDER_EXTERNAL_URL is missing")


# =========================
# WEB SERVER
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "Telegram Media Link Bot is running."


@app.route("/health")
def health():
    return "OK"


@app.route("/file/<file_id>")
def serve_file(file_id):
    """
    Creates a stable link that fetches the Telegram file
    when somebody opens the link.
    """

    try:
        # Ask Telegram for the current file path
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile"
        result = requests.get(
            url,
            params={"file_id": file_id},
            timeout=30,
        )

        data = result.json()

        if not data.get("ok"):
            abort(404)

        file_path = data["result"]["file_path"]

        # Current Telegram download URL
        download_url = (
            f"https://api.telegram.org/file/bot"
            f"{BOT_TOKEN}/{file_path}"
        )

        # Stream the file to the user
        r = requests.get(
            download_url,
            stream=True,
            timeout=60,
        )

        if r.status_code != 200:
            abort(r.status_code)

        content_type = (
            r.headers.get("Content-Type")
            or mimetypes.guess_type(file_path)[0]
            or "application/octet-stream"
        )

        def generate():
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    yield chunk

        return Response(
            generate(),
            content_type=content_type,
            headers={
                "Content-Disposition": "inline"
            },
        )

    except Exception as e:
        print("File error:", e)
        abort(500)


def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True,
    )


# =========================
# TELEGRAM BOT
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send me a file, video, photo, audio or document "
        "and I will generate a direct link for it."
    )


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = update.message

    file_id = None

    # Document
    if message.document:
        file_id = message.document.file_id

    # Video
    elif message.video:
        file_id = message.video.file_id

    # Audio
    elif message.audio:
        file_id = message.audio.file_id

    # Voice
    elif message.voice:
        file_id = message.voice.file_id

    # Animation / GIF
    elif message.animation:
        file_id = message.animation.file_id

    # Video note
    elif message.video_note:
        file_id = message.video_note.file_id

    # Photo - use highest quality version
    elif message.photo:
        file_id = message.photo[-1].file_id

    if not file_id:
        return

    link = f"{BASE_URL}/file/{file_id}"

    await message.reply_text(
        "✅ Your direct link is ready:\n\n"
        f"{link}\n\n"
        "You can save this link."
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("Bot error:", context.error)


# =========================
# START EVERYTHING
# =========================

def main():

    # Start Render web server in background
    web_thread = threading.Thread(
        target=run_web_server,
        daemon=True,
    )

    web_thread.start()

    # Start Telegram bot
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        MessageHandler(
            filters.Document.ALL
            | filters.VIDEO
            | filters.AUDIO
            | filters.PHOTO
            | filters.VOICE
            | filters.ANIMATION
            | filters.VIDEO_NOTE,
            handle_media,
        )
    )

    application.add_error_handler(error_handler)

    print("Bot started...")

    application.run_polling()


if __name__ == "__main__":
    main()
