"""Text-to-speech without TikTok logins or session cookies.

Uses Edge's online neural TTS (no API key). If it is unreachable and
espeak-ng plus FFmpeg are installed, falls back to local speech synthesis.
"""

import asyncio
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import edge_tts

from logstream import log


# Preserve the existing UI's language/voice identifiers.
VOICE_MAP = {
    "en_au_001": "en-AU-NatashaNeural",
    "en_au_002": "en-AU-WilliamNeural",
    "en_uk_001": "en-GB-RyanNeural",
    "en_uk_003": "en-GB-SoniaNeural",
    "en_us_001": "en-US-JennyNeural",
    "en_us_002": "en-US-AriaNeural",
    "en_us_006": "en-US-GuyNeural",
    "en_us_007": "en-US-DavisNeural",
    "en_us_009": "en-US-TonyNeural",
    "en_us_010": "en-US-ChristopherNeural",
    "fr_001": "fr-FR-HenriNeural",
    "fr_002": "fr-FR-DeniseNeural",
    "de_001": "de-DE-KatjaNeural",
    "de_002": "de-DE-ConradNeural",
    "es_002": "es-ES-AlvaroNeural",
    "es_mx_002": "es-MX-JorgeNeural",
    "br_001": "pt-BR-FranciscaNeural",
    "br_005": "pt-BR-AntonioNeural",
    "id_001": "id-ID-GadisNeural",
    "jp_001": "ja-JP-NanamiNeural",
    "jp_003": "ja-JP-KeitaNeural",
    "kr_002": "ko-KR-InJoonNeural",
    "kr_003": "ko-KR-SunHiNeural",
    "ar_001": "ar-SY-AmanyNeural",
    "ar_002": "ar-SY-LaithNeural",
}

NATIVE_VOICE_PATTERN = re.compile(r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z0-9]+Neural$")


def resolve_voice(voice: str) -> str:
    """Resolve a legacy selection or an Edge voice into an Edge voice name."""
    voice = (voice or "en_us_001").strip()
    if voice in VOICE_MAP:
        return VOICE_MAP[voice]
    if NATIVE_VOICE_PATTERN.fullmatch(voice):
        return voice
    raise ValueError(
        f"Unsupported voice '{voice}'. Select a supported voice in the UI."
    )


def _fallback_espeak(text: str, voice: str, target: Path) -> None:
    """Offline fallback for GitHub runners with espeak-ng and FFmpeg."""
    if not shutil.which("espeak-ng") or not shutil.which("ffmpeg"):
        raise RuntimeError("Edge-TTS unavailable; install espeak-ng and FFmpeg for a local fallback.")
    language = voice.split("-")[0]
    with tempfile.TemporaryDirectory(prefix="moneyprinter-speech-") as directory:
        wav_path = Path(directory) / "speech.wav"
        subprocess.run(
            ["espeak-ng", "-v", language, "-w", str(wav_path), text],
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(wav_path),
             "-codec:a", "libmp3lame", "-q:a", "4", str(target)],
            check=True, capture_output=True, text=True,
        )


def tts(
    text: str,
    voice: str = "en_us_001",
    filename: str = "output.mp3",
    play_sound: bool = False,
) -> None:
    """Create an MP3 recording of text; raise on failures instead of silently continuing."""
    if not text or not text.strip():
        raise ValueError("No speech text was provided.")

    target = Path(filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    selected_voice = resolve_voice(voice)
    target.unlink(missing_ok=True)

    try:
        asyncio.run(edge_tts.Communicate(text.strip(), selected_voice).save(str(target)))
        if not target.exists() or target.stat().st_size == 0:
            raise RuntimeError("Edge-TTS returned no audio.")
        log(f"[+] Neural voice saved: {target}", "success")
    except Exception as exc:
        target.unlink(missing_ok=True)
        log(f"[!] Edge-TTS not available ({exc}); trying local fallback.", "warning")
        try:
            _fallback_espeak(text, selected_voice, target)
        except Exception as fallback_error:
            target.unlink(missing_ok=True)
            raise RuntimeError(
                "Speech synthesis failed with Edge-TTS and local fallback."
            ) from fallback_error
        if not target.exists() or target.stat().st_size == 0:
            raise RuntimeError("Offline speech engine created an empty audio file.")
        log(f"[+] Offline voice saved: {target}", "success")

    if play_sound:
        from playsound import playsound
        playsound(str(target))
