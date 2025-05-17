import re
import os
import json
import logging

from pathlib import Path
from logging.handlers import RotatingFileHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,filters
from src.service.YTService import get_video_id, fetch_transcript
from src.service.LLMService import summarize_text,generate_response, select_model
from src.service.CredentialsService import get_credential

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Main logger
logger = logging.getLogger("HomeBotLogger")
logger.setLevel(logging.DEBUG)  # Capture everything, handlers will filter

# Formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Info Handler
info_handler = RotatingFileHandler("logs/homebot.log", maxBytes=1_000_000, backupCount=3,encoding='utf-8')
info_handler.setLevel(logging.INFO)
info_handler.setFormatter(formatter)
logger.addHandler(info_handler)

# Debug Handler (separate file)
debug_handler = RotatingFileHandler("logs/homebot.debug.log", maxBytes=1_000_000, backupCount=2,encoding='utf-8')
debug_handler.setLevel(logging.DEBUG)
debug_handler.setFormatter(formatter)
logger.addHandler(debug_handler)

# Optional: also log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
# Store user language preference in memory

user_languages = {}
user_last_ts = {}
user_last_title = {}
recent_messages = {}

MAX_MESSAGE_LENGTH = 4096
YOUTUBE_REGEX = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+"

# Usage
TOKEN = get_credential("TG_TOKEN")

def store_user_message(user_id, text):
    if user_id not in recent_messages:
        recent_messages[user_id] = []
    recent_messages[user_id].append(text)
    if len(recent_messages[user_id]) > 10:
        recent_messages[user_id] = recent_messages[user_id][-10:]

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = update.message.text

    if not text.startswith("/"):
        store_user_message(user.id, text)
        logger.debug(f"Stored message for user {user.id}: {text}")

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
    text = "Hi!"
    await update.message.reply_text(text)
    logger.info(f"User {user.id} ({user.username}) used /start command. Reply: {text}")

async def sl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if context.args:
        lang = context.args[0].lower()
        user_languages[user.id] = lang
        reply = f"Language set to '{lang}'."
        await update.message.reply_text(reply)
        logger.info(f"User {user.id} ({user.username}) set language: {lang}. Reply: {reply}")
    else:
        reply = "Please provide a language code, e.g. /sl en"
        await update.message.reply_text(reply)
        logger.info(f"User {user.id} ({user.username}) failed /sl usage. Reply: {reply}")

async def ts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    messages = recent_messages.get(user.id, [])

    yt_url = None
    for msg in reversed(messages):  # Search from most recent
        match = re.search(YOUTUBE_REGEX, msg)
        if match:
            yt_url = match.group(0)
            break

    if not yt_url:
        await update.message.reply_text(
            "❌ No recent YouTube link found in your messages. Please paste it first."
        )
        logger.info(f"User {user.id} had no recent YouTube URL.")
        return

    await update.message.reply_text(f"✅ Found link: {yt_url}\nProcessing...")

    if user.id not in user_languages:
        user_languages[user.id] = "ru"
        await update.message.reply_text("Language not set. Using 'en'. Set with /sl <code>")

    lang = user_languages[user.id]

    try:
        video_id = get_video_id(yt_url)
    except ValueError:
        reply = "Invalid YouTube URL. Please try again."
        await update.message.reply_text(reply)
        logger.info(f"User {user.id} had invalid URL: {yt_url}")
        return

    await update.message.reply_text("Fetching transcript...")
    logger.info(f"User {user.id} ({user.username}) requested transcript for video '{video_id}' with lang '{lang}'")

    result = fetch_transcript(video_id, lang)
    logger.debug(result)

    user_last_ts[user.id] = result['text']
    user_last_title[user.id] = result['title']
    user_languages[user.id] = result['selected_language']

    logger.info("Transcript finished")

    if lang not in result["available_languages"]:
        await update.message.reply_text(
            f"⚠️ Transcript for your selected lang - '{lang}' not found.\n")
    else:
        await update.message.reply_text("Transcript saved.")

    await update.message.reply_text(
        f"Available languages: {', '.join(result['available_languages'])}\n"
        f"Selected language: {result['selected_language']}"
    )

async def show_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"User {user.id} ({user.username}) requested transcript text'")
    result = user_last_ts[user.id]
    for chunk in split_message(result):
        await update.message.reply_text(chunk)

    logger.info(f"Transcript sent to user {user.id} ({user.username}), length {len(result)} chars")
async def sum_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await generate_summary(update,context,"sum")
async def sup_sum_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await generate_summary(update, context, "sup_sum")
async def generate_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, q_type : str):
    user = update.message.from_user
    logger.info(f"User {user.id} ({user.username}) requested summary'")

    result = user_last_ts[user.id]
    title = user_last_title[user.id]
    lang = user_languages[user.id]

    result = await summarize_text(result,title, lang, q_type)

    for chunk in split_message(result):
        await update.message.reply_text(chunk,parse_mode="Markdown")
    logger.info(f"Summary sent to user {user.id} ({user.username}), length {len(result)} chars")

async def sel_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /model <gpt|local>")
        return

    model_name = context.args[0].lower()

    try:
        select_model(model_name)
        await update.message.reply_text(f"✅ Model switched to *{model_name}*", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Invalid model. Please choose `gpt` or `local`.", parse_mode="Markdown")

# /q <question>
async def question_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("❗ Please provide a question.")
        return

    question = " ".join(context.args)
    response = await generate_response(question,parse_mode="Markdown")
    await update.message.reply_text(response)

# /qv <question>
async def question_with_video_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if not context.args:
        await update.message.reply_text("❗ Please provide a question.")
        return

    question = " ".join(context.args)

    try:
        context_text = user_last_ts[user_id]
        title = user_last_title.get(user_id, "Unknown Title")
        lang = user_languages.get(user_id, "en")

        response = generate_response(question, context_text, title, lang)
        await update.message.reply_text(response,parse_mode="Markdown")
    except KeyError as e:
        await update.message.reply_text("⚠️ No previous video context found. Use /transcript first.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 *Available Commands*:
/start – Start the bot
/help – Show this help message
/sl <lang_code> – Set your preferred language (e.g. `/sl en`)
/ts <YouTube URL> – Fetch and save transcript from a YouTube video
/show – Show the last saved transcript
/sm – Summarize the last saved transcript
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")
    logger.info(f"User {update.message.from_user.id} used /help")

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sl", sl_command))
    application.add_handler(CommandHandler("ts", ts_command))
    application.add_handler(CommandHandler("show", show_command))
    application.add_handler(CommandHandler("sm", sum_command))
    application.add_handler(CommandHandler("supsm", sup_sum_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("select_model", sel_model_command))
    application.add_handler(CommandHandler("q", question_command))
    application.add_handler(CommandHandler("qv", question_with_video_context))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()