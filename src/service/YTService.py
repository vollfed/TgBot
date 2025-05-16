from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, CouldNotRetrieveTranscript

def get_video_id(url_or_id):
    """
    Extract video ID from a YouTube URL or return ID directly if already provided.
    """
    if "youtube.com" in url_or_id or "youtu.be" in url_or_id:
        import re
        # Extract video ID from common URL formats
        match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url_or_id)
        if match:
            return match.group(1)
        else:
            raise ValueError("Invalid YouTube URL")
    return url_or_id

def fetch_transcript(video_input, lang):
    video_id = get_video_id(video_input)
    try:
        # Fetch transcript for the specific language
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
        # Join all text snippets into one string
        text = "\n".join([entry['text'] for entry in transcript])
        return text
    except TranscriptsDisabled:
        return "Transcripts are disabled for this video."
    except NoTranscriptFound:
        return f"No transcript found for language '{lang}'."
    except CouldNotRetrieveTranscript:
        return "Could not retrieve transcript due to network or other error."
    except Exception as e:
        return f"An error occurred: {e}"

if __name__ == "__main__":
    video = input("Enter YouTube video URL or ID: ")
    language = input("Enter language code (e.g. 'en', 'es'): ")
    result = fetch_transcript(video, language)
    print("\n--- Transcript ---\n")
    print(result)
