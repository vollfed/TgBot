import json
import logging

from pathlib import Path
from logging.handlers import RotatingFileHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from src.service.YTService import get_video_id, fetch_transcript
from src.service.LLMService import summarize_text


# Setup rotating logger
logger = logging.getLogger("HomeBotLogger")
logger.setLevel(logging.INFO)

handler = RotatingFileHandler("homebot.log", maxBytes=1_000_000, backupCount=3)  # 1MB per file, keep 3 backups
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Store user language preference in memory
user_languages = {}
user_last_ts = {}

MAX_MESSAGE_LENGTH = 4096
def get_token():
    config_path = Path("src/resources/config.json")
    if not config_path.exists():
        raise FileNotFoundError(f"{config_path} not found. Please create it with your TOKEN.")

    with config_path.open() as f:
        config = json.load(f)
    return config.get("TOKEN")

# Usage
TOKEN = get_token()

def split_message(text, max_length=MAX_MESSAGE_LENGTH):
    """Split text into chunks smaller than max_length without breaking words."""
    chunks = []
    while len(text) > max_length:
        # Find last newline before max_length
        split_pos = text.rfind('\n', 0, max_length)
        if split_pos == -1:
            split_pos = max_length  # No newline found, split at max_length
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip('\n')
    chunks.append(text)
    return chunks

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = "Hi! Use /setlang <language_code> to set your transcript language.\nThen use /transcript <youtube_url> to get the transcript."
    await update.message.reply_text(text)
    logger.info(f"User {user.id} ({user.username}) used /start command. Reply: {text}")

async def setlang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if context.args:
        lang = context.args[0].lower()
        user_languages[user.id] = lang
        reply = f"Language set to '{lang}'. Now send /transcript <youtube_url>"
        await update.message.reply_text(reply)
        logger.info(f"User {user.id} ({user.username}) set language: {lang}. Reply: {reply}")
    else:
        reply = "Please provide a language code, e.g. /setlang en"
        await update.message.reply_text(reply)
        logger.info(f"User {user.id} ({user.username}) failed /setlang usage. Reply: {reply}")

async def transcript(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if user.id not in user_languages:
        reply = "Better set your language first using /setlang <language_code>. en will be used"
        await update.message.reply_text(reply)
        logger.info(f"User {user.id} ({user.username}) tried /transcript without language set. Reply: {reply}")
        user_languages[user.id] = "en"

    if not context.args:
        reply = "Please provide a YouTube video URL, e.g. /transcript https://youtu.be/abc123"
        await update.message.reply_text(reply)
        logger.info(f"User {user.id} ({user.username}) used /transcript without URL. Reply: {reply}")
        return

    url_or_id = context.args[0]
    lang = user_languages[user.id]

    try:
        video_id = get_video_id(url_or_id)
    except ValueError:
        reply = "Invalid YouTube URL or ID. Please try again."
        await update.message.reply_text(reply)
        logger.info(f"User {user.id} ({user.username}) provided invalid URL: {url_or_id}. Reply: {reply}")
        return

    await update.message.reply_text("Fetching transcript...")
    logger.info(f"User {user.id} ({user.username}) requested transcript for video '{video_id}' with lang '{lang}'")

    result = fetch_transcript(video_id, lang)
    logger.debug(result)
    user_last_ts[user.id] = result
    logger.info(f"Transcript finished")
    await update.message.reply_text("Transcript saved")

async def showTranscript(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"User {user.id} ({user.username}) requested transcript text'")
    result = user_last_ts[user.id]
    for chunk in split_message(result):
        await update.message.reply_text(chunk)

    logger.info(f"Transcript sent to user {user.id} ({user.username}), length {len(result)} chars")

async def summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"User {user.id} ({user.username}) requested summary'")

    result = user_last_ts[user.id]
    result = summarize_text(result)

    for chunk in split_message(result):
        await update.message.reply_text(chunk)
    logger.info(f"Summary sent to user {user.id} ({user.username}), length {len(result)} chars")


def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sl", setlang))
    application.add_handler(CommandHandler("ts", transcript))
    application.add_handler(CommandHandler("show", showTranscript))
    application.add_handler(CommandHandler("sm", summarize))

    print("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()