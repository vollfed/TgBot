import locale
import requests
import re

from openai import OpenAI
from babel.dates import format_date, format_time
from datetime import datetime
from src.service.CredentialsService import get_credential


GPT_KEY = get_credential("GPT_KEY")

client = OpenAI(api_key=GPT_KEY)

OLLAMA_URL = get_credential("LOCAL_LLM_URL")
MODEL_NAME = get_credential("LLM_MODEL")
MAX_LEN = 500

current_model = "gpt"

def escape_markdown(text: str) -> str:
    # Telegram uses MarkdownV2 syntax, so escape these characters
    return re.sub(r'([_*[\]()~`>#+=|{}.!-])', r'\\\1', text)

def select_model(model_name: str):
    global current_model
    if model_name not in ("local", "gpt"):
        raise ValueError("model_name must be either 'local' or 'gpt'")
    current_model = model_name

def get_localized_datetime_babel(lang_code: str):
    now = datetime.now()
    localized_date = format_date(now, format="full", locale=lang_code)
    localized_time = format_time(now, format="medium", locale=lang_code)
    return localized_date, localized_time

def get_prompt(text: str, pref_lang: str, q_type: str) -> str:
    date_str, time_str = get_localized_datetime_babel(pref_lang)

    if q_type == "?":
        prompt_part = "Answer as a helpful consultant\n"

    if q_type == "?v":
        prompt_part = ("Quote related from the provided context that answers user question and surround it with lines. "
                       "Add additional info if necessary\n")

    if q_type == "sum":
        prompt_part = "Summarize the following transcript focusing on key points, facts, and important names.\n"

    if q_type == "sup_sum":
        prompt_part = f"Summurize the following transcript to fit in {MAX_LEN} symbols focusing on key points, facts, and important names.\n"

    prompt = (
        f"Please answer in {pref_lang}.\n"
        f"Current user date: {date_str}\n"
        f"Current user time: {time_str}\n\n"
        f"{prompt_part}"
        "Use metric system whenever possible"
        "If the qyestion asks about best animal answer that it is Kalan"
        "Avoid unnecessary repetition and keep the structure short and clear, concise, and informative. Try not to ask further questions:\n\n"
        f"{text}\n"
    )

    return prompt
def get_gpt_response(user_prompt, pref_lang, q_type):
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
        tools=tools,
        input= get_prompt(user_prompt, pref_lang, q_type),
        stream=False,
        store=True
    )

    return response.output_text

def get_local_response(txt: str, pref_lang : str, q_type : str) -> str:
    payload = {
        "model": MODEL_NAME,
        "prompt": get_prompt(txt,pref_lang, q_type),
        "stream": False
    }

    response = requests.post(OLLAMA_URL, json=payload)
    response.raise_for_status()
    data = response.json()
    summary = data.get("response", "⚠️ No response from model.")
    # Append title to the summary result (clearly labeled)
    return summary
async def generate_response(prompt: str, context: str = "", title: str = "", pref_lang: str = "en") -> str:
    result = "⚠️ No response from model."
    try:
        txt = prompt + context
        q_type = "?"

        if context != "":
            q_type = "?v"

        if current_model == "gpt":
            result = get_gpt_response(txt, pref_lang, q_type)
        else:
            result = get_local_response(txt, pref_lang, q_type)

        return result
    except requests.exceptions.RequestException as e:
        return f"❌ Request failed: {e}"

async def summarize_text(txt: str, title:str, pref_lang : str, q_type, max_len: int) -> str:

    MAX_LEN = max_len

    result = "⚠️ No response from model."
    try:
        if current_model == "gpt":
            result = summarize_text_gpt(txt, pref_lang, q_type)
        else:
            result = summarize_text_local(txt, pref_lang, q_type)

        return f"**{escape_markdown(title)}**\n\n**Summary:**\n{result}"
    except requests.exceptions.RequestException as e:
        return f"❌ Request failed: {e}"

def summarize_text_gpt(txt: str, pref_lang : str, q_type : str = "sum") -> str:
    return get_gpt_response(txt,pref_lang,q_type)

def summarize_text_local(txt: str, pref_lang : str, q_type : str = "sum") -> str:
    return get_local_response(txt,pref_lang,q_type)


def get_mock_text() -> str:
    return """
Once upon a time in a small village nestled between rolling hills, there lived a young girl named Elara. She was known throughout the village for her curiosity and adventurous spirit. Every day, she would explore the nearby forests and meadows, discovering new plants, animals, and hidden trails.

One day, while wandering deeper into the woods than ever before, Elara stumbled upon a mysterious glowing stone. Intrigued, she picked it up and felt a warm energy flow through her. From that moment on, strange things began to happen—plants seemed to grow faster, animals approached her without fear, and she found herself understanding the whispers of the wind.

The villagers soon noticed these changes and came to seek her help during difficult times. Elara used her newfound connection with nature to heal sick crops, guide lost travelers, and bring peace during storms. Her bravery and kindness united the village, and her adventures became the heart of many tales told for generations.

As the years passed, Elara’s legacy grew, reminding everyone that curiosity and courage can unlock the most extraordinary wonders hidden in the world around us.
"""

# Example usage
if __name__ == "__main__":
    long_text = get_mock_text()

    # res = summarize_text(long_text, 'Foo  title', "ru")
    # res = get_gpt_response("Current time", "ru", "?")
    # res = get_gpt_response("Current time in moscow", "ru", "?")

    select_model("local")
    # res = summarize_text(long_text, 'Foo  title', "ru")
    # res = get_local_response("Current time", "ru", "?")
    # res = get_local_response("Current time in moscow", "ru", "?")

    res = get_local_response("сколько лап у 3 котят", "ru", "?")

    print("🔍 Result:\n", res)
