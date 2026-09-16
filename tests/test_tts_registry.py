from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import importlib.util

from app.tts import CosyVoiceTTS, create_tts, infer_provider


def test_cosyvoice2_is_default_provider():
    assert infer_provider({}) == "cosyvoice2"
    provider = create_tts({})
    assert isinstance(provider, CosyVoiceTTS)
    assert provider.name == "cosyvoice2"
    assert provider.config.voice == "wudan"


def test_backward_compatibility_aliases():
    # 历史配置的 audio8、onnx、mlx 等均平滑回退映射到 CosyVoice 2.0
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


def _assert_reference_audio_normalized(tmp_path: Path, monkeypatch, suffix: str) -> None:
    provider = CosyVoiceTTS()
    source = tmp_path / f"voice-reference{suffix}"
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
            str(source.resolve()),
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


def test_cosyvoice_normalizes_browser_audio_once(tmp_path: Path, monkeypatch):
    _assert_reference_audio_normalized(tmp_path, monkeypatch, ".m4a")


def test_cosyvoice_normalizes_wav_reference_too(tmp_path: Path, monkeypatch):
    # Keep SaaS behavior aligned with the proven local profile workflow: even a
    # WAV upload may be 44.1/48 kHz stereo and must be standardized first.
    _assert_reference_audio_normalized(tmp_path, monkeypatch, ".wav")


def test_cosyvoice_service_does_not_pre_split_zero_shot_target_text():
    # Avoid importing the heavy CosyVoice runtime in CI; this source-level guard
    # protects the important integration contract. CosyVoice performs its own
    # language-aware segmentation inside inference_zero_shot/instruct2.
    service_file = Path(__file__).resolve().parents[1] / "digital-human-tts" / "tts_core" / "service.py"
    source = service_file.read_text(encoding="utf-8")
    assert "from .text import preprocess_text, split_for_synthesis" not in source
    assert "for index, chunk in enumerate(split_for_synthesis(" not in source
    assert "inference_zero_shot(" in source
    assert "inference_instruct2(" in source


def test_tts_text_preprocessing_never_invents_business_explanations():
    text_file = Path(__file__).resolve().parents[1] / "digital-human-tts" / "tts_core" / "text.py"
    spec = importlib.util.spec_from_file_location("tts_text_contract", text_file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    source = "我们要学的是一条判断链——变、影、痛、值、证。"
    assert module.preprocess_text(source) == source
