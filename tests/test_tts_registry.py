from __future__ import annotations

from pathlib import Path

from app.tts import CosyVoiceTTS, create_tts, infer_provider


def test_cosyvoice2_is_default_provider():
    assert infer_provider({}) == "cosyvoice2"
    provider = create_tts({})
    assert isinstance(provider, CosyVoiceTTS)
    assert provider.name == "cosyvoice2"
    assert provider.config.voice == "wudan"


def test_backward_compatibility_aliases():
    # 历史配置的 audio8、onnx、mlx 等均平滑回退映射到 cosyvoice2
    assert infer_provider({"provider": "audio8"}) == "cosyvoice2"
    assert infer_provider({"provider": "qwen3"}) == "cosyvoice2"
    assert infer_provider({"provider": "cosyvoice"}) == "cosyvoice2"


def test_cosyvoice_reference_audio_is_resolved_from_manifest_base(tmp_path: Path):
    provider = create_tts(
        {
            "provider": "cosyvoice2",
            "voice": "wudan",
            "ref_audio": "voice.wav",
            "ref_text": "参考音频文本",
        },
        base=tmp_path,
    )
    assert isinstance(provider, CosyVoiceTTS)
    assert provider.config.ref_audio == str((tmp_path / "voice.wav").resolve())
    assert provider.config.ref_text == "参考音频文本"

