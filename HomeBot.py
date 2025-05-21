import re
import os
import json
import logging
import tempfile
import asyncio

from pathlib import Path
from logging.handlers import RotatingFileHandler
from telegram import Update, Document
from langdetect import detect
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,filters

from src.service.DBService import init_db, store_message, get_last_messages, save_user_context, get_user_context
from src.service.YTService import get_video_id, fetch_transcript
from src.service.LLMService import summarize_text,generate_response, select_model, escape_markdown, clean_and_trim_text
from src.service.CredentialsService import get_credential
from src.service.FIleService import extract_text, is_valid_url

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
MAX_DIALOG_CTXT = 50  #TODO add command to regulate this
YOUTUBE_REGEX = r"""(?x)
    ^(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/
    (?:
        (?:watch\?v=|embed/|v/|shorts/)?
        [\w\-]{11}
    )
    (?:[&?][^\s]*)?$
"""

# Usage
TOKEN = get_credential("TG_TOKEN")

def contains_cyrillic(text):
    return bool(re.search('[\u0400-\u04FF]', text))

def safe_detect(text: str) -> str:
    try:
        if not text or len(text) < 3:
            return "en"  # default for too short input
        lang = detect(text)

        if contains_cyrillic(text):
            return "ru"

        if lang not in ("en", "ru"):
            return "en"
        return lang
    except Exception:
        return "en"

def append_to_context(new_text: str, user_id: int) -> str:
    user_context = get_user_context(user_id)
    if user_context and user_context.get("continue_context"):
        return (user_context.get("transcript") or "") + "\n" + new_text
    return new_text


def append_to_title(new_title: str, user_id: int) -> str:
    user_context = get_user_context(user_id)
    if user_context and user_context.get("continue_context"):
        return (user_context.get("title") or "") + "\n" + new_title
    return new_title

def get_context_from_dialog(user_id, max_dialog_contex: int = MAX_DIALOG_CTXT) -> str:
    messages = get_last_messages(user_id, limit=max_dialog_contex)
    formatted = []

    for msg, is_from_user in messages:
        prefix = "USER:" if is_from_user == 'Y' else "LLM:"
        formatted.append(f"{prefix} {msg}")

    return "\n".join(formatted)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    message = update.message

    text = message.text
    document: Document = message.document if message.document else None

    context_data = context.user_data.setdefault("context_data", {})

    if text and text.startswith("/"):
        return

    if text:
        # Log the message
        logger.debug(f"Received message from {user.id}: {text}")

        # YouTube link check
        if re.search(YOUTUBE_REGEX, text):
            logger.debug(f"Detected YouTube link from {user.id}")
            store_message(user.id, text)
            return await ts_command(update, context)

        # Web URL check
        if is_valid_url(text):
            try:
                extracted_text = await extract_text(text)
                context_data["transcript"] = extracted_text
                context_data["title"] = text
                context_data["language"] = safe_detect(extracted_text)
                await message.reply_text("✅ Web page content saved for processing.")

                save_user_context(
                    user.id,
                    transcript=append_to_context(context_data['transcript'], user.id),
                    title=append_to_title(context_data['title'], user.id),
                    language=context_data['language']
                )
                store_message(user.id, text)
            except Exception as e:
                logger.exception(f"Error extracting from URL: {e}")
                await message.reply_text("❌ Failed to extract content from the URL.")
            return

    # PDF document handling
    if document and document.file_name.lower().endswith(".pdf"):
        try:
            file = await document.get_file()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                await file.download_to_drive(custom_path=tmp_file.name)
                extracted_text = await extract_text(tmp_file.name)
                context_data["transcript"] = extracted_text
                context_data["title"] = document.file_name
                context_data["language"] = safe_detect(extracted_text)
                await message.reply_text("✅ PDF content saved for processing.")

                save_user_context(
                    user.id,
                    transcript=append_to_context(context_data['transcript'], user.id),
                    title=append_to_title(context_data['title'], user.id),
                    language=context_data['language']
                )

        except Exception as e:
            logger.exception(f"Error extracting from PDF: {e}")
            await message.reply_text("❌ Failed to extract content from the PDF.")
        finally:
            if 'tmp_file' in locals() and os.path.exists(tmp_file.name):
                os.unlink(tmp_file.name)
        return
    lang = safe_detect(text)
    # Fallback response

    context = get_context_from_dialog(user.id)
    response = await generate_response(text or "", context or "", "", lang)
    store_message(user.id, text)
    store_message(user.id, response,'N')

    await message.reply_text(response, parse_mode=ParseMode.MARKDOWN_V2)

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

    messages = get_last_messages(user_id, 10, 'Y')

    yt_url = None
    for msg in reversed(messages):  # Search from most recent
        match = re.search(YOUTUBE_REGEX, msg[0])
        if match:
            yt_url = match.group(0)
            break

    if not yt_url:
        await update.message.reply_text(
            "❌ No recent YouTube link found in your messages. Please paste it first."
        )
        logger.info(f"User {user_id} had no recent YouTube URL.")
        return

    msg_found = await update.message.reply_text(f"✅ Found link: {yt_url}\nProcessing...")

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

    msg_start = await update.message.reply_text("⏳ Fetching transcript...")
    logger.info(f"User {user_id} ({user.username}) requested transcript for video '{video_id}' with lang '{lang}'")

    result = fetch_transcript(video_id, lang)
    logger.debug(result)


    logger.info("Transcript finished")

    if lang not in result["available_languages"]:
        await msg_found.delete()
        await msg_start.delete()
        msg_res = await update.message.reply_text(
            f"⚠️ Transcript for your selected lang - '{lang}' not found.\n")
    else:
        await msg_found.delete()
        await msg_start.delete()
        msg_res = await update.message.reply_text("Transcript saved.")

    msg_lang = await update.message.reply_text(
        f"Available languages: {', '.join(result['available_languages'])}\n"
        f"Selected language: {result['selected_language']}"
    )

    await asyncio.sleep(5)
    await msg_res.delete()
    await msg_lang.delete()

    text = result.get('text')
    if is_valid_transcript(result):
        # Save context to DB
        save_user_context(
            user_id,
            transcript=append_to_context(result['text'], user_id),
            title=append_to_title(result['title'], user_id)
        )
        await update.message.reply_text("✅ Ready to process")
    else:
        logger.warning(f"Transcript invalid or missing. Result: {result}")
        await update.message.reply_text("❌ Failed getting transcript. Please try again")

def is_valid_transcript(result):
    text = result.get('text')
    lang = result.get('selected_language')
    return bool(text and text.strip() and lang and lang.strip())


async def cc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id
    args = context.args

    if not args:
        await update.message.reply_text(escape_markdown("❗ Please provide a value: `y` or `n` (e.g. `/cc y`)"), parse_mode=ParseMode.MARKDOWN_V2)
        return

    value = args[0].lower()
    if value not in ("y", "n"):
        await update.message.reply_text(escape_markdown("❌ Invalid value. Use `y` or `n`."), parse_mode=ParseMode.MARKDOWN_V2)
        return

    save_user_context(user_id, continue_context=(value == "y"))
    await update.message.reply_text(f"🔁 Continue context set to: `{value}`", parse_mode=ParseMode.MARKDOWN_V2)

async def get_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"User {user.id} ({user.username}) requested context text")

    context_data = get_user_context(user.id)

    if not context_data or not context_data.get("transcript"):
        await update.message.reply_text("❌ No context found")
        logger.info(f"No context found for user {user.id}")
        return

    transcript = context_data["transcript"]

    for chunk in split_message(transcript):
        await update.message.reply_text(chunk)

    logger.info(f"Context sent to user {user.id} ({user.username}), length {len(transcript)} chars")


async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"User {user.id} ({user.username}) requested title text")

    context_data = get_user_context(user.id)

    if not context_data or not context_data.get("title"):
        await update.message.reply_text("❌ No title found")
        logger.info(f"No title found for user {user.id}")
        return

    transcript = context_data["title"]

    for chunk in split_message(transcript):
        await update.message.reply_text(chunk)

    logger.info(f"Title sent to user {user.id} ({user.username}), length {len(transcript)} chars")

async def sum_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Also support optional lang override in /sm (e.g. /sm en)
    lang_override = context.args[0].lower() if context.args else None
    if lang_override:
        save_user_context(update.message.from_user.id, language=lang_override)
    return await generate_summary(update, context, "sum", -1)

async def sup_sum_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    max_answer_len = 300
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

    msg_start = await update.message.reply_text("⏳ Generating summary...")

    context_data = get_user_context(user.id)
    if context_data is None:
        await update.message.reply_text("⚠️ No previous video context found. Use /transcript first.")
        return

    context_text = context_data["transcript"]
    title = context_data["title"] or "Unknown Title"
    lang = context_data["language"] or "en"

    context_text, check, tokem_len = clean_and_trim_text(context_text, lang)

    if check:
        await update.message.reply_text(f"⚠️ Input context too long - {tokem_len}. Result may be truncated...")

    result = await summarize_text(context_text,title, lang, q_type, max_answer_len)
    await msg_start.delete()

    store_message(user.id, result, 'N')

    for chunk in split_message(result):
        await update.message.reply_text(chunk,parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Summary sent to user {user.id} ({user.username}), length {len(result)} chars")

async def sel_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /model <gpt|local>")
        return

    model_name = context.args[0].lower()

    try:
        select_model(model_name)
        await update.message.reply_text(f"✅ Model switched to *{model_name}*", parse_mode=ParseMode.MARKDOWN_V2)
    except ValueError:
        await update.message.reply_text("❌ Invalid model. Please choose `gpt` or `local`.", parse_mode=ParseMode.MARKDOWN_V2)

# /q <question>
async def question_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("❗ Please provide a question.")
        return

    question = " ".join(context.args)
    context_data = get_user_context(user.id)

    context_text = context_data["transcript"]
    title = context_data["title"] or "Unknown Title"
    lang = context_data["language"] or "en"

    context = get_context_from_dialog(user.id)
    response = await generate_response(question, context, title, lang)

    store_message(user.id, question)
    store_message(user.id, response, 'N')

    await update.message.reply_text(response,parse_mode=ParseMode.MARKDOWN_V2)

# /qv <question>
async def question_with_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        response = await generate_response(question, context_text, title, lang,"?c")

        store_message(user.id, question)
        store_message(user.id, response, 'N')

        await update.message.reply_text(response,parse_mode=ParseMode.MARKDOWN_V2)
    except KeyError as e:
        await update.message.reply_text("⚠️ No previous video context found. Use /transcript first.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 **Available Commands**:
/start – Start the bot  
/help – Show this help message  
/sl <lang_code> – Set your preferred transcript language (e.g. `/sl en`)  
/ts – Fetch and save transcript from the most recent YouTube link you sent  
/show – Show the last saved transcript  
/sm – Summarize the last saved transcript  
/ssm [max_len] [lang] – Super summarize with optional max length and response language (e.g. `/ssm 300 ru`)  
/select_model <gpt-4|local> – Switch between GPT or local model  
/q <question> – Ask a general question (no video context)  
/qc <question> – Ask a question using saved context  
/cc <y|n> – Enable or disable *context continuation* (e.g. `/cc y`)  
"""
    await update.message.reply_text(escape_markdown(help_text), parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"User {update.message.from_user.id} used /help")

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sl", sl_command))
    application.add_handler(CommandHandler("ts", ts_command))
    application.add_handler(CommandHandler("gt", get_title))
    application.add_handler(CommandHandler("gc", get_context))
    application.add_handler(CommandHandler("cc", cc_command))
    application.add_handler(CommandHandler("sm", sum_command))
    application.add_handler(CommandHandler("ssm", sup_sum_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("select_model", sel_model_command))
    application.add_handler(CommandHandler("q", question_command))
    application.add_handler(CommandHandler("qc", question_with_context))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(MessageHandler(filters.Document.PDF, handle_message))

    print("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    init_db()
    main()