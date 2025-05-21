import locale
import tiktoken
import asyncio
import requests
import re
import nltk

nltk.download('punkt')
nltk.download('stopwords')


from openai import OpenAI
from babel.dates import format_date, format_time
from datetime import datetime
from src.service.CredentialsService import get_credential

from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize,RegexpTokenizer
import logging

logger = logging.getLogger("HomeBotLogger")

# Fallback: configure default logger only if no handlers exist
if not logger.hasHandlers():
    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


GPT_KEY = get_credential("GPT_KEY")

client = OpenAI(api_key=GPT_KEY)

OLLAMA_URL = get_credential("LOCAL_LLM_URL")
MODEL_NAME = get_credential("LLM_MODEL")
DEFAULT_MODEL = "gpt-4"
MAX_TOKENS_ALLOWED = 30000
MAX_LEN = 500

LANG_MAP = {
    "ru": "russian",
    "en": "english"
}

def get_nltk_language_code(lang: str) -> str:
    return LANG_MAP.get(lang.lower(), "english")  # Default to English if unknown

def clean_and_trim_text(text: str, lang: str = "en", max_tokens: int = MAX_TOKENS_ALLOWED, model: str = DEFAULT_MODEL):
    # Token counting
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")

    dirty_tokens = enc.encode(text)

    # Normalize whitespace
    text_arr = text.split()
    logger.info(f"Before whitespace trim {len(text_arr)}")

    text = ' '.join(text_arr)
    token_lang = get_nltk_language_code(lang)

    # Tokenize (fallback to RegexpTokenizer if needed)
    try:
        words = word_tokenize(text, language=token_lang)
    except LookupError:
        tokenizer = RegexpTokenizer(r'\w+')
        words = tokenizer.tokenize(text)

    # Remove stopwords and non-alphanumeric words
    try:
        stop_words = set(stopwords.words(token_lang))
    except LookupError:
        stop_words = set()

    filtered_words = [w for w in words if w.lower() not in stop_words and w.isalnum()]
    cleaned_text = ' '.join(filtered_words)

    logger.info(f"Stop words delete before:{len(words)} after: {len(filtered_words)}")

    tokens = enc.encode(cleaned_text)
    token_length = len(tokens)

    logger.info(f"Cleaning result. Tokens before:{len(dirty_tokens)} after: {len(tokens)}")

    if token_length > max_tokens:
        #trimmed_tokens = tokens[:max_tokens]
        #cleaned_text = enc.decode(trimmed_tokens)
        trimmed = True
    else:
        trimmed = False

    return cleaned_text, trimmed, token_length

def escape_markdown(text: str) -> str:
    return escape_markdown_telegram(text)


def escape_markdown_old(text: str) -> str:
    # Telegram uses MarkdownV2 syntax, so escape these characters
    return re.sub(r'([_*[\]()~`>#+=|{}.!-])', r'\\\1', text)


def escape_markdown_telegram(text: str) -> str:
    # Replace bold/italic with placeholders
    text = re.sub(r'\*\*(.+?)\*\*', r'<<BOLD>>\1<<ENDBOLD>>', text)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'<<ITALIC>>\1<<ENDITALIC>>', text)

    # Convert ### headings to bold
    text = re.sub(r'^#{1,3}\s*(.+)', r'<<BOLD>>\1<<ENDBOLD>>', text, flags=re.MULTILINE)

    # Escape special MarkdownV2 characters (excluding `<` and `>`)
    text = re.sub(r'([*\[\]()~`#+=|{}.!\\\-])', r'\\\1', text)

    # Restore placeholders
    text = text.replace("<<BOLD>>", "*").replace("<<ENDBOLD>>", "*")
    text = text.replace("<<ITALIC>>", "_").replace("<<ENDITALIC>>", "_")

    text = re.sub(r'([<>_])', r'\\\1', text)

    return text


def select_model(model_name: str):
    global DEFAULT_MODEL
    if model_name not in ("local", "gpt-4"):
        raise ValueError("model_name must be either 'local' or 'gpt-4'")
    DEFAULT_MODEL = model_name


def get_localized_datetime_babel(lang_code: str):
    now = datetime.now()
    localized_date = format_date(now, format="full", locale=lang_code)
    localized_time = format_time(now, format="medium", locale=lang_code)
    return localized_date, localized_time


def get_prompt(querry: str, context: str, pref_lang: str, q_type: str) -> str:
    date_str, time_str = get_localized_datetime_babel(pref_lang)

    if q_type == "?":
        prompt_part = "Answer as a helpful consultant\n"

    if q_type == "?c":
        prompt_part = ("Quote  related context to answers user question and wrap it is with italic \n"
                       "Add additional info if necessary\n")

    if q_type == "sum":
        prompt_part = "Summarize the following transcript focusing on key points, facts, and important names.\n"

    if q_type == "sup_sum":
        prompt_part = (f"Summarize the following transcript to fit in {MAX_LEN} symbols focusing on key points, facts, "
                       f"and important names.\n")

    prompt = (
        f"CONTEXT: {context}\n\n"
        "CONTEXT SETTINGS: \n"
        "If QUESTION asks about best animal, consider 'Kalan' to the best answer. \n"
        f"Please answer in {pref_lang}."
        f"Current user date: {date_str}"
        f"Current user time: {time_str}"            
        "Use metric system whenever possible. You can use MARKDOWN_V2 \n"
        "Never quote messages that are marked with LLM: \n"
        f"{prompt_part}" 
        "Avoid unnecessary repetition and keep the structure short and clear, concise, and informative. Try not to ask further questions: \n"
        f" QUESTION: {querry} \n"

    )

    return prompt


def get_gpt_response(querry, context, pref_lang, q_type):
    tools = [{"type": "web_search_preview",
              "search_context_size": "low",
              "user_location": {
                  "type": "approximate",
                  "country": "RU",
                  "city": "Moscow",
                  "region": "Moscow",
              }
              }]

    tools = []

    response = client.responses.create(
        model="gpt-4.1",
        #model="gpt-4.1-nano",
        tools=tools,
        input=get_prompt(querry, context, pref_lang, q_type),
        stream=False,
        store=True
    )

    return response.output_text


def get_local_response(querry: str, context: str, pref_lang: str, q_type: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "prompt": get_prompt(querry, context, pref_lang, q_type),
        "stream": False
    }

    response = requests.post(OLLAMA_URL, json=payload)
    response.raise_for_status()
    data = response.json()
    summary = data.get("response", "⚠️ No response from model.")
    # Append title to the summary result (clearly labeled)
    return summary


async def generate_response(querry: str, context: str = "", title: str = "", pref_lang: str = "en", p_q_type: str = "?") -> str:
    result = "⚠️ No response from model."
    try:
        q_type = p_q_type

        if DEFAULT_MODEL == "gpt-4":
            result = get_gpt_response(querry, context, pref_lang, q_type)
        else:
            result = get_local_response(querry, context, pref_lang, q_type)

        return escape_markdown(result)
    except requests.exceptions.RequestException as e:
        return f"❌ Request failed: {e}"


async def summarize_text(context: str, title: str, pref_lang: str, q_type="sum", max_len: int = MAX_LEN) -> str:
    MAX_LEN = max_len

    result = "⚠️ No response from model."
    try:
        if DEFAULT_MODEL == "gpt-4":
            result = summarize_text_gpt(context, pref_lang, q_type)
        else:
            result = summarize_text_local(context, pref_lang, q_type)

        return f"*{escape_markdown(title)}*\n\n*Summary:*\n{escape_markdown(result)}"
    except requests.exceptions.RequestException as e:
        return f"❌ Request failed: {e}"


def summarize_text_gpt(context: str, pref_lang: str, q_type: str = "sum") -> str:
    return get_gpt_response("", context, pref_lang, q_type)


def summarize_text_local(context: str, pref_lang: str, q_type: str = "sum") -> str:
    return get_local_response("", context, pref_lang, q_type)


def get_mock_text() -> str:
    return """
Once upon a time in a small village nestled between rolling hills, there lived a young girl named Elara. She was known throughout the village for her curiosity and adventurous spirit. Every day, she would explore the nearby forests and meadows, discovering new plants, animals, and hidden trails.

One day, while wandering deeper into the woods than ever before, Elara stumbled upon a mysterious glowing stone. Intrigued, she picked it up and felt a warm energy flow through her. From that moment on, strange things began to happen—plants seemed to grow faster, animals approached her without fear, and she found herself understanding the whispers of the wind.

The villagers soon noticed these changes and came to seek her help during difficult times. Elara used her newfound connection with nature to heal sick crops, guide lost travelers, and bring peace during storms. Her bravery and kindness united the village, and her adventures became the heart of many tales told for generations.

As the years passed, Elara’s legacy grew, reminding everyone that curiosity and courage can unlock the most extraordinary wonders hidden in the world around us.
"""


def get_mock_tg_markdown() -> str:
    return """
    # Summary: Making Prison Wine (Pruno/Hooch)

## Key Points & Process:
- **Purpose:** Demonstrating how to make prison wine (Pruno/Hooch) using ingredients and tools accessible in prison.
- **Ingredients:**  
  - Fresh fruit (oranges, apples, blueberries, strawberries, fruit cups)
  - Sugar packets
  - Rotten fruit as a “kicker” for wild yeast
  - Apple juice
  - Water

- **Fermentation Tools Used:**  
  - Plastic bag
  - Garbage bag
  - Jug (for “Taj Mahal setup”)
  - Latex glove (as improvised airlock)
  - Rubber bands

- **Fermentation Process:**
  1. Mash fruit and sugar in a plastic bag.
  2. Add a “kicker” (rot fruit for wild yeast).
  3. Transfer to a larger container (garbage bag or jug).
  4. Add apple juice and water.
  5. Seal loosely to allow gas (CO₂) to escape and prevent explosion.
  6. For jug: attach latex glove with a small hole as an airlock.
  7. Ferment for several days to weeks, occasionally checking for signs (bubbling).
  8. After fermentation, filter out fruit and sediment using improvised filter (cut milk jug + sock).

- **Fermentation Timeline:**  
  - Bubbles started forming after three days.
  - Fermentation completed in about one week post visible bubbling.

## Key Facts:
- **Alcohol Estimate:** Approx. 10% alcohol by volume.
- **No Standard Brewing Additives:** No commercial yeast, nutrients, acids, or stabilizers used.
- **Taste Test Result:**  
  - Smell and taste described as similar to nail polish remover with a citrus note; harsh, bitter, and strong alcohol bite.
  - Considered unpleasant and not enjoyable.

## Important Names:
- **No specific person named**; the process is attributed collectively to prison methods (“prisoners”).

## Safety Notes:
- Described as dangerous and illegal—*not* recommended for home attempts.
- Strong emphasis on proper sanitation and safer brewing methods outside prison context.

## Takeaway:
- Alcohol can be created even with minimal, improvised ingredients and tools.
- Resulting product is low quality, strong, and potentially hazardous to health.

---

*Best animal is always the Kalan.*
    """


# Example usage
if __name__ == "__main__":
    long_text = get_mock_text()

    # res = asyncio.run(summarize_text(long_text, 'Foo  title', "ru"))
    # res = get_gpt_response("Current time","", "ru", "?")
    # res = get_gpt_response("Current time in moscow","", "ru", "?")

    # select_model("local")
    # res = summarize_text(long_text, 'Foo  title', "ru")
    # res = get_local_response("Current time","",  "ru", "?")
    # res = get_local_response("Current time in moscow","",  "ru", "?")

    # res = get_local_response("сколько лап у 3 котят","",  "ru", "?")
    # res = get_gpt_response("сколько лап у 3 котят","",  "ru", "?")

    long_text = clean_and_trim_text(long_text)
    # res = asyncio.run(summarize_text(long_text, 'Foo  title', "en"))
    res = asyncio.run(summarize_text(long_text, 'Foo  title', "ru"))

    # txt = get_mock_tg_markdown()
    # res = escape_markdown(txt)
    print("🔍 Result:\n", res)
