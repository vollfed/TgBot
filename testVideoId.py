from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, CouldNotRetrieveTranscript
from xml.parsers.expat import ExpatError

def test_transcript(video_id):
    try:
        YouTubeTranscriptApi().fetch(video_id,languages=['en'])
    except TranscriptsDisabled:
        print("Transcripts are disabled for this video.")
    except CouldNotRetrieveTranscript:
        print("Could not retrieve transcript due to network or other error.")
    except ExpatError as e:
        print(f"ExpatError: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def test_transcript1(video_id):
    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
        print("Transcript list fetched successfully.")
        print("Available generated languages:", list(transcript_list._generated_transcripts.keys()))
        print("Available manual languages:", list(transcript_list._manually_created_transcripts.keys()))

        transcript_obj = transcript_list.find_transcript(["en", "ru"])

        if transcript_obj:
            transcript = transcript_obj.fetch()
            print("Transcript fetched successfully.")
            for entry in transcript[:5]:  # print first 5 entries
                print(entry.text)
        else:
            print("No transcript found for 'en' or 'ru'.")

    except TranscriptsDisabled:
        print("Transcripts are disabled for this video.")
    except CouldNotRetrieveTranscript:
        print("Could not retrieve transcript due to network or other error.")
    except ExpatError as e:
        print(f"ExpatError: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    video_id = "wW1hCQEbD24"
    test_transcript(video_id)
