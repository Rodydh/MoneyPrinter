from pathlib import Path

import pytest
import speech


def test_german_and_english_voices():
    assert speech.resolve_voice("de_001") == "de-DE-KatjaNeural"
    assert speech.resolve_voice("de_002") == "de-DE-ConradNeural"
    assert speech.resolve_voice("en_us_001") == "en-US-JennyNeural"
    assert speech.resolve_voice("ar_001") == "ar-SY-AmanyNeural"


def test_native_voice_is_supported():
    assert speech.resolve_voice("de-DE-KatjaNeural") == "de-DE-KatjaNeural"


def test_unsupported_voice_is_rejected():
    with pytest.raises(ValueError):
        speech.resolve_voice("en_us_ghostface")


def test_empty_speech_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        speech.tts("   ", filename=str(tmp_path / "empty.mp3"))


def test_audio_saves_without_tiktok_credentials(monkeypatch, tmp_path):
    class FakeCommunicate:
        def __init__(self, text, voice):
            assert text == "Hallo!"
            assert voice == "de-DE-KatjaNeural"

        async def save(self, filename):
            Path(filename).write_bytes(b"fake-mp3-data")

    monkeypatch.setattr(speech.edge_tts, "Communicate", FakeCommunicate)
    monkeypatch.delenv("TIKTOK_SESSION_ID", raising=False)
    target = tmp_path / "voice.mp3"
    speech.tts("Hallo!", voice="de_001", filename=str(target))
    assert target.read_bytes() == b"fake-mp3-data"


def test_unavailable_edge_voice_fails_instead_of_using_robotic_fallback(monkeypatch, tmp_path):
    class FailingCommunicate:
        def __init__(self, *_args, **_kwargs):
            pass

        async def save(self, _filename):
            raise ConnectionError("network unavailable")

    monkeypatch.setattr(speech.edge_tts, "Communicate", FailingCommunicate)
    target = tmp_path / "unavailable.mp3"
    with pytest.raises(RuntimeError, match="rather than using a robotic voice"):
        speech.tts("Guten Tag.", "de_001", str(target))
    assert not target.exists()
