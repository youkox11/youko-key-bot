
import os
from urllib.parse import urlparse

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔑 YOUKO KEY BOT V1\n\n"
        "Welcome to YOUKO HUB!\n"
        "📩 Send your Delta / LootLabs link.\n\n"
        "⚙️ Link validation is active.\n"
        "🔑 Automatic key retrieval is not connected yet."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 HOW TO USE\n\n"
        "1. Copy your link.\n"
        "2. Send it to this bot.\n"
        "3. Wait for validation.\n\n"
        "YOUKO HUB 🔑"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text.strip()
    parsed = urlparse(message)

    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or any(c.isspace() for c in message)
    ):
        await update.message.reply_text(
            "❌ Invalid URL. Please send a valid HTTPS link."
        )
        return

    await update.message.reply_text(
        "✅ Link received!\n\n"
        f"🌐 Host: {parsed.hostname}\n"
        "⚙️ Status: Awaiting authorized API integration\n\n"
        "🔑 Automatic key generation is not available yet."
    )

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)
    )

    print("YOUKO KEY BOT started!")
    app.run_polling()

if __name__ == "__main__":
    main()
