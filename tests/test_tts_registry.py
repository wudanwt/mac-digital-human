from __future__ import annotations

from pathlib import Path

from app.tts import Audio8ONNXTTS, MLXAudioTTS, create_tts, infer_provider


def test_audio8_is_default_provider():
    assert infer_provider({}) == "audio8"
    provider = create_tts({})
    assert isinstance(provider, Audio8ONNXTTS)
    assert provider.name == "audio8"
    assert provider.config.voice == "default"


def test_explicit_qwen3_provider():
    provider = create_tts({"provider": "qwen3", "voice": "Dylan"})
    assert isinstance(provider, MLXAudioTTS)
    assert provider.name == "qwen3"
    assert provider.config.voice == "Dylan"


def test_old_qwen_model_manifest_stays_compatible():
    payload = {"model": "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"}
    assert infer_provider(payload) == "qwen3"
    assert isinstance(create_tts(payload), MLXAudioTTS)


def test_audio8_reference_audio_is_resolved_from_manifest_base(tmp_path: Path):
    provider = create_tts(
        {
            "provider": "audio8",
            "voice": "dan",
            "ref_audio": "voice.wav",
            "ref_text": "参考音频文本",
        },
        base=tmp_path,
    )
    assert isinstance(provider, Audio8ONNXTTS)
    assert provider.config.ref_audio == str((tmp_path / "voice.wav").resolve())
    assert provider.config.ref_text == "参考音频文本"
