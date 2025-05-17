import re
import os
import json
import logging

import asyncio
from pathlib import Path
from logging.handlers import RotatingFileHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,filters

from src.service.DBService import init_db, store_message, get_last_messages, save_user_context, get_user_context
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


MAX_MESSAGE_LENGTH = 4096
YOUTUBE_REGEX = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+"

# Usage
TOKEN = get_credential("TG_TOKEN")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = update.message.text

    if not text.startswith("/"):
        store_message(user.id, text)
        logger.debug(f"Stored message for user {user.id}: {text}")

        match = re.search(YOUTUBE_REGEX, text)
        if match:
            return await ts_command(update, context)

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

        # Save only the language, keep transcript/title as is
        save_user_context(user.id, language=lang)

        reply = f"Language set to '{lang}'."
        await update.message.reply_text(reply)
        logger.info(f"User {user.id} ({user.username}) set language: {lang}. Reply: {reply}")
    else:
        reply = "Please provide a language code, e.g. /sl en"
        await update.message.reply_text(reply)
        logger.info(f"User {user.id} ({user.username}) failed /sl usage. Reply: {reply}")


async def ts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id

    messages = get_last_messages(user_id, limit=10)

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
        logger.info(f"User {user_id} had no recent YouTube URL.")
        return

    await update.message.reply_text(f"✅ Found link: {yt_url}\nProcessing...")

    try:
        video_id = get_video_id(yt_url)
    except ValueError:
        reply = "Invalid YouTube URL. Please try again."
        await update.message.reply_text(reply)
        logger.info(f"User {user_id} had invalid URL: {yt_url}")
        return

    # Get user language from context DB or fallback
    context_data = get_user_context(user_id)
    lang = context_data["language"] if context_data and context_data.get("language") else "en"

    msg_start = await update.message.reply_text("Fetching transcript...")
    logger.info(f"User {user_id} ({user.username}) requested transcript for video '{video_id}' with lang '{lang}'")

    result = fetch_transcript(video_id, lang)
    logger.debug(result)

    # Save context to DB
    save_user_context(
        user_id,
        transcript=result['text'],
        title=result['title'],
        language=result['selected_language']
    )

    logger.info("Transcript finished")

    if lang not in result["available_languages"]:
        await update.message.reply_text(
            f"⚠️ Transcript for your selected lang - '{lang}' not found.\n")
    else:
        await msg_start.delete()
        msg_res = await update.message.reply_text("Transcript saved.")

    msg_lang = await update.message.reply_text(
        f"Available languages: {', '.join(result['available_languages'])}\n"
        f"Selected language: {result['selected_language']}"
    )
    await asyncio.sleep(5)
    await msg_res.delete()
    await msg_lang.delete()


async def show_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"User {user.id} ({user.username}) requested transcript text")

    context_data = get_user_context(user.id)

    if not context_data or not context_data.get("transcript"):
        await update.message.reply_text("❌ No transcript found. Use /ts after sending a YouTube link.")
        logger.info(f"No transcript found for user {user.id}")
        return

    transcript = context_data["transcript"]

    for chunk in split_message(transcript):
        await update.message.reply_text(chunk)

    logger.info(f"Transcript sent to user {user.id} ({user.username}), length {len(transcript)} chars")

async def sum_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Also support optional lang override in /sm (e.g. /sm en)
    lang_override = context.args[0].lower() if context.args else None
    if lang_override:
        save_user_context(update.message.from_user.id, language=lang_override)
    return await generate_summary(update, context, "sum", -1)

async def sup_sum_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    max_answer_len = 500
    lang_override = None

    for arg in context.args:
        if arg.isdigit():
            max_answer_len = int(arg)
        elif re.fullmatch(r"[a-z]{2}", arg.lower()):
            lang_override = arg.lower()

    if lang_override:
        save_user_context(update.message.from_user.id, language=lang_override)

    return await generate_summary(update, context, "sup_sum", max_answer_len)


async def generate_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, q_type : str, max_answer_len: int):
    user = update.message.from_user
    logger.info(f"User {user.id} ({user.username}) requested summary'")

    context_data = get_user_context(user.id)
    if context_data is None:
        await update.message.reply_text("⚠️ No previous video context found. Use /transcript first.")
        return

    context_text = context_data["transcript"]
    title = context_data["title"] or "Unknown Title"
    lang = context_data["language"] or "en"

    result = await summarize_text(context_text,title, lang, q_type, max_answer_len)

    for chunk in split_message(result):
        await update.message.reply_text(chunk,parse_mode="MarkdownV2")
    logger.info(f"Summary sent to user {user.id} ({user.username}), length {len(result)} chars")

async def sel_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /model <gpt|local>")
        return

    model_name = context.args[0].lower()

    try:
        select_model(model_name)
        await update.message.reply_text(f"✅ Model switched to *{model_name}*", parse_mode="MarkdownV2")
    except ValueError:
        await update.message.reply_text("❌ Invalid model. Please choose `gpt` or `local`.", parse_mode="MarkdownV2")

# /q <question>
async def question_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("❗ Please provide a question.")
        return

    question = " ".join(context.args)
    response = await generate_response(question,)
    context_data = get_user_context(user.id)

    if context_data is None:
        await update.message.reply_text("⚠️ No previous video context found. Use /transcript first.")
        return

    context_text = context_data["transcript"]
    title = context_data["title"] or "Unknown Title"
    lang = context_data["language"] or "en"

    response = await generate_response(question, "", title, lang)

    await update.message.reply_text(response,parse_mode="MarkdownV2")

# /qv <question>
async def question_with_video_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if not context.args:
        await update.message.reply_text("❗ Please provide a question.")
        return

    question = " ".join(context.args)

    try:
        context_data = get_user_context(user_id)
        if context_data is None:
            await update.message.reply_text("⚠️ No previous video context found. Use /transcript first.")
            return

        context_text = context_data["transcript"]
        title = context_data["title"] or "Unknown Title"
        lang = context_data["language"] or "en"

        response = await generate_response(question, context_text, title, lang)
        await update.message.reply_text(response,parse_mode="MarkdownV2")
    except KeyError as e:
        await update.message.reply_text("⚠️ No previous video context found. Use /transcript first.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 *Available Commands*:
/start – Start the bot
/help – Show this help message
/sl <lang_code> – Set your preferred transcript language (e.g. `/sl en`)
/ts – Fetch and save transcript from the most recent YouTube link you sent
/show – Show the last saved transcript
/sm – Summarize the last saved transcript
/ssm [max_len] [lang]– Super summarize with optional max length and responce lang (e.g. `/supsm 300 ru`)
/select_model <gpt|local> – Switch between GPT or local model
/q <question> – Ask a general question (no video context)
/qv <question> – Ask a question using saved transcript context
"""
    await update.message.reply_text(help_text, parse_mode="MarkdownV2")
    logger.info(f"User {update.message.from_user.id} used /help")

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sl", sl_command))
    application.add_handler(CommandHandler("ts", ts_command))
    application.add_handler(CommandHandler("show", show_command))
    application.add_handler(CommandHandler("sm", sum_command))
    application.add_handler(CommandHandler("ssm", sup_sum_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("select_model", sel_model_command))
    application.add_handler(CommandHandler("q", question_command))
    application.add_handler(CommandHandler("qv", question_with_video_context))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    init_db()
    main()