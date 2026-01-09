import os
import io
from google.cloud import speech
from google.cloud import texttospeech
from openai import OpenAI
from pydub import AudioSegment

def get_credentials_path():
    # Try current directory first
    if os.path.exists("gcp-sa.json"):
        return os.path.abspath("gcp-sa.json")
    # Try subdirectory
    if os.path.exists("google_stt_tts/gcp-sa.json"):
        return os.path.abspath("google_stt_tts/gcp-sa.json")
    return None

def init_google_clients():
    creds_path = get_credentials_path()
    # allow soft failure if only using OpenAI
    if not creds_path:
        print("Warning: gcp-sa.json not found. Google Cloud STT/TTS will not work.")
        return None, None
    
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
    
    speech_client = speech.SpeechClient()
    tts_client = texttospeech.TextToSpeechClient()
    return speech_client, tts_client

def init_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Warning: OPENAI_API_KEY not found. OpenAI STT/TTS will not work.")
        return None
    return OpenAI(api_key=api_key)

def speech_to_text(client, audio_bytes, provider="google", language_code="cmn-Hant-TW"):
    """
    Transcribes audio bytes to text.
    provider: "google" or "openai"
    client: either google speech_client or openai_client
    """
    if provider == "google":
        return _google_stt(client, audio_bytes, language_code)
    elif provider == "openai":
        return _openai_stt(client, audio_bytes, language_code)
    return None

def text_to_speech(client, text, provider="google", language_code="zh-TW", voice_name=None):
    """
    Synthesizes text to audio bytes (MP3).
    provider: "google" or "openai"
    client: either google tts_client or openai_client
    """
    if provider == "google":
        return _google_tts(client, text, language_code, voice_name)
    elif provider == "openai":
        return _openai_tts(client, text, voice_name)
    return None

# --- Internal Google Impl ---

def _google_stt(speech_client, audio_bytes, language_code):
    try:
        # Convert audio to LINEAR16 PCM, 16kHz, mono
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        pcm_bytes = audio.raw_data

        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=language_code,
            enable_automatic_punctuation=True,
        )
        audio_req = speech.RecognitionAudio(content=pcm_bytes)

        response = speech_client.recognize(config=config, audio=audio_req)
        
        if not response.results:
            return None
            
        transcript = " ".join([result.alternatives[0].transcript for result in response.results])
        return transcript
    except Exception as e:
        print(f"Google STT Error: {e}")
        return None

def _google_tts(tts_client, text, language_code, voice_name):
    try:
        synthesis_input = texttospeech.SynthesisInput(text=text)
        if voice_name:
            voice = texttospeech.VoiceSelectionParams(language_code=language_code, name=voice_name)
        else:
            voice = texttospeech.VoiceSelectionParams(language_code=language_code)

        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

        response = tts_client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        return response.audio_content
    except Exception as e:
        print(f"Google TTS Error: {e}")
        return None

# --- Internal OpenAI Impl ---

def _openai_stt(client, audio_bytes, language_code):
    """
    Uses OpenAI Whisper (transcriptions).
    Note: OpenAI API requires a filename in the tuple for the file upload.
    """
    try:
        # OpenAI Whisper accepts mp3, wav, etc. audio_bytes from st.audio_input usually wav.
        # We wrap it in a named BytesIO
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.wav" 

        # Map language_code if needed. Whisper auto-detects well, 
        # but we can pass 'zh' or 'en' if we want to force it.
        # Strict mapping: cmn-Hant-TW -> zh, en-US -> en
        iso_lang = "zh" if "zh" in language_code or "cmn" in language_code else "en"

        transcript = client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file,
            language=iso_lang
        )
        return transcript.text
    except Exception as e:
        print(f"OpenAI STT Error: {e}")
        return None

def _openai_tts(client, text, voice_name="alloy"):
    """
    Uses OpenAI TTS (tts-1).
    voice_name defaults to 'alloy'. Options: alloy, echo, fable, onyx, nova, shimmer.
    """
    try:
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice_name if voice_name else "alloy",
            input=text
        )
        # return bytes
        return response.content
    except Exception as e:
        print(f"OpenAI TTS Error: {e}")
        return None

