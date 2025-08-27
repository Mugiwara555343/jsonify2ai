# worker/tests/test_parse_audio_unit.py
from app.services.parse_audio import transcribe_audio


def test_transcribe_audio_dev(tmp_path, monkeypatch):
    # Force dev mode so no model/download/ffmpeg is needed
    monkeypatch.setenv("AUDIO_DEV_MODE", "1")
    p = tmp_path / "a.wav"
    p.write_bytes(b"")  # file is not actually read in dev mode
    out = transcribe_audio(str(p))
    assert "transcript" in out.lower()
    assert "a.wav" in out
