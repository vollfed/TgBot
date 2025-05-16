import requests

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL_NAME = "dolphin-llama3"

def summarize_text(large_text: str) -> str:
    prompt = (
        "Summarize the following text into 1-2 pages, focusing on key points and important facts. "
        "Avoid unnecessary repetition and keep the structure clear and informative:\n\n"
        f"{large_text}\n\n"
        "Summary:"
    )

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "⚠️ No response from model.")
    except requests.exceptions.RequestException as e:
        return f"❌ Request failed: {e}"

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
    summary = summarize_text(long_text)
    print("🔍 Summary:\n", summary)
