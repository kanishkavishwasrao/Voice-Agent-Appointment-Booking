"""Thin wrapper around Sarvam speech APIs (per docs.sarvam.ai, checked Oct 2026).

Model names are env-overridable because Sarvam's docs mention both v3 and v4;
if you get a "model not found" error, set STT_MODEL=saaras:v3 / TTS_MODEL=bulbul:v3.

    export SARVAM_API_KEY=...
"""
import os
import tempfile
from dotenv import load_dotenv
load_dotenv()

STT_MODEL = os.getenv("STT_MODEL", "saaras:v4")
TTS_MODEL = os.getenv("TTS_MODEL", "bulbul:v4-flash")
STT_MODE = os.getenv("STT_MODE", "codemix")  # transcribe | codemix | translit | verbatim
LANGUAGE = os.getenv("LANGUAGE", "hi-IN")
SPEAKER = os.getenv("TTS_SPEAKER", "shubh")

_client = None


def _get_client():
    global _client
    if _client is None:
        from sarvamai import SarvamAI  # imported lazily so offline tests don't need it

        key = os.environ.get("SARVAM_API_KEY")
        if not key:
            raise RuntimeError("Set SARVAM_API_KEY first (https://dashboard.sarvam.ai)")
        _client = SarvamAI(api_subscription_key=key)
    return _client


def stt(audio_path: str, mode: str | None = None) -> str:
    """Speech -> text. REST endpoint accepts clips up to 30 s, plenty for one turn."""
    with open(audio_path, "rb") as f:
        resp = _get_client().speech_to_text.transcribe(
            file=f,
            model=STT_MODEL,
            mode=mode or STT_MODE,
            language_code=LANGUAGE,
        )
    return resp.transcript


def tts(text: str) -> str:
    """Text -> mp3 file path."""
    out = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    with open(out, "wb") as f:
        for chunk in _get_client().text_to_speech.convert_stream(
            text=text,
            language_code=LANGUAGE,
            speaker=SPEAKER,
            model=TTS_MODEL,
            output_audio_codec="mp3",
        ):
            f.write(chunk)
    return out