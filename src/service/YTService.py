import logging
import re
import requests
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, CouldNotRetrieveTranscript
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger("HomeBotLogger")
logger.setLevel(logging.DEBUG)

from urllib.parse import urlparse, parse_qs
import re
from urllib.parse import urlparse, parse_qs

YOUTUBE_ID_PATTERN = re.compile(r"^[\w-]{11}$")

def get_video_id(url_or_id):
    """
    Extract video ID from a YouTube URL or return the ID directly.
    Supports:
    - https://www.youtube.com/watch?v=VIDEOID
    - https://youtu.be/VIDEOID
    - https://youtube.com/shorts/VIDEOID
    - https://youtube.com/embed/VIDEOID
    - https://youtube.com/v/VIDEOID
    - https://youtube.com/live/VIDEOID
    - raw video IDs
    """
    if YOUTUBE_ID_PATTERN.match(url_or_id):
        return url_or_id

    parsed = urlparse(url_or_id)
    netloc = parsed.netloc.lower()
    path_parts = parsed.path.strip("/").split("/")

    if "youtube.com" in netloc:
        if parsed.path.startswith("/watch"):
            query = parse_qs(parsed.query)
            video_id = query.get("v", [None])[0]
            if video_id:
                return video_id
        elif path_parts[0] in {"shorts", "embed", "v", "live"} and len(path_parts) > 1:
            return path_parts[1]
    elif "youtu.be" in netloc and path_parts:
        return path_parts[0]

    raise ValueError("Invalid YouTube URL or video ID")


def get_video_title(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    resp = requests.get(url)
    if resp.status_code == 200:
        match = re.search(r"<title>(.*?) - YouTube</title>", resp.text)
        if match:
            return match.group(1)
    return ""

def contains_cyrillic(text):
    return bool(re.search('[\u0400-\u04FF]', text))
import time
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, CouldNotRetrieveTranscript


def fetch_transcript(video_id, lang):
    title = get_video_title(video_id)
    logger.debug(f"Video title: {title}")

    langs = ["en", "ru"]
    if contains_cyrillic(title):
        langs = ["ru", "en"]

    transcript_list = None
    for attempt in range(3):
        try:
            transcript_list = YouTubeTranscriptApi().list(video_id)
            break
        except Exception as e:
            logger.warning(f"Attempt {attempt+1}/3 failed: {e}")
            time.sleep(2 ** attempt)  # exponential backoff

    if transcript_list is None:
        errMsg = "Failed to retrieve transcript list after retries."
        logger.error(errMsg)
        return {
            "text": errMsg,
            "available_languages": [],
            "selected_language": "",
            "title": title
        }

    try:
        generated_langs = set(transcript_list._generated_transcripts.keys())
        manual_langs = set(transcript_list._manually_created_transcripts.keys())
        available_langs = list(generated_langs.union(manual_langs))

        logger.debug("Available langs: " + str(available_langs))

        transcript_obj = transcript_list.find_transcript(langs)

        if not transcript_obj:
            return {
                "text": f"No transcript found for languages: {', '.join(langs)}.",
                "available_languages": available_langs,
                "selected_language": langs[0],
                "title": title
            }

        transcript = transcript_obj.fetch()
        full_text = "\n".join(entry.text for entry in transcript)

        return {
            "text": full_text,
            "available_languages": available_langs,
            "selected_language": transcript_obj.language_code,
            "title": title
        }

    except TranscriptsDisabled:
        errMsg = "Transcripts are disabled for this video."
    except CouldNotRetrieveTranscript:
        errMsg = "Could not retrieve transcript due to network or other error."
    except Exception as e:
        errMsg = f"An error occurred: {str(e)}"

    logger.error(errMsg)
    return {
        "text": errMsg,
        "available_languages": [],
        "selected_language": "",
        "title": title
    }

