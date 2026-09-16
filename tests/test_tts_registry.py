from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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


def test_cosyvoice_normalizes_browser_audio_once(tmp_path: Path, monkeypatch):
    provider = CosyVoiceTTS()
    source = tmp_path / "voice-reference.m4a"
    source.write_bytes(b"browser audio")
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"wav audio")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("app.tts.cosyvoice.subprocess.run", fake_run)

    first = provider._normalize_reference_audio(source, tmp_path / "audio")
    second = provider._normalize_reference_audio(source, tmp_path / "audio")

    assert first == second
    assert first.suffix == ".wav"
    assert calls == [
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "24000",
            "-c:a",
            "pcm_s16le",
            str(first),
        ]
    ]
