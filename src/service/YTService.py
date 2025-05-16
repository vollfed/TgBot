import logging
import re
import requests
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, CouldNotRetrieveTranscript
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

def get_video_id(url_or_id):
    """
    Extract video ID from a YouTube URL or return the ID directly.
    """
    # If it's already 11 characters, assume it's an ID
    if len(url_or_id) == 11 and all(c.isalnum() or c in "-_" for c in url_or_id):
        return url_or_id

    parsed = urlparse(url_or_id)

    # Example: https://www.youtube.com/watch?v=VIDEOID
    if "youtube.com" in parsed.netloc:
        query = parse_qs(parsed.query)
        video_id = query.get("v", [None])[0]
        if video_id:
            return video_id

    # Example: https://youtu.be/VIDEOID
    if "youtu.be" in parsed.netloc:
        return parsed.path.strip("/")

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

def fetch_transcript(video_id, lang):
    title = get_video_title(video_id)
    logger.debug(f"Video title: {title}")

    # Determine language preference order
    if contains_cyrillic(title):
        langs = ["ru", "en"]
    else:
        langs = ["en", "ru"]

    try:
        result_lang = langs[0]

        transcript_list = YouTubeTranscriptApi().list(video_id)
        generated_langs = set(transcript_list._generated_transcripts.keys())
        manual_langs = set(transcript_list._manually_created_transcripts.keys())

        available_langs = list(generated_langs.union(manual_langs))

        transcript_obj = None
        for lang in langs:
            try:
                transcript_obj = transcript_list.find_transcript([lang])
                if transcript_obj:
                    result_lang = lang
                    break
            except NoTranscriptFound:
                continue

        if not transcript_obj:
            return {
                "text": f"No transcript found for languages: {', '.join(langs)}.",
                "available_languages": available_langs,
                "selected_language": result_lang,
                "title": title
            }

        transcript = transcript_obj.fetch()
        full_text = "\n".join(entry.text for entry in transcript)

        return {
            "text": full_text,
            "available_languages": available_langs,
            "selected_language": result_lang,
            "title": title
        }

    except TranscriptsDisabled:
        return {
            "text": "Transcripts are disabled for this video.",
            "available_languages": [],
            "selected_language": "",
            "title": title
        }
    except CouldNotRetrieveTranscript:
        return {
            "text": "Could not retrieve transcript due to network or other error.",
            "available_languages": [],
            "selected_language": "",
            "title": title
        }
    except Exception as e:
        return {
            "text": f"An error occurred: {e}",
            "available_languages": [],
            "selected_language": "",
            "title": title
        }
