from __future__ import annotations

import json
from pathlib import Path

from app.course import _frames_for_duration
from app.main import catalog
from app.presets import BUILTIN_PROMPTS, get_avatar_profile, get_prompt_preset
from app.tts import TTSConfig


ROOT = Path(__file__).resolve().parents[1]


def test_prompt_presets_are_longcat_safe():
    ids = [item.id for item in BUILTIN_PROMPTS]
    assert len(ids) == len(set(ids))
    assert "energy_training_studio" in ids
    for item in BUILTIN_PROMPTS:
        assert item.height % 8 == 0
        assert item.width % 8 == 0
        assert (item.num_frames - 1) % 4 == 0
        assert item.prompt


def test_longcat_frame_planner():
    assert _frames_for_duration(1.0, 25) == 61
    assert _frames_for_duration(4.2, 25) == 105
    assert _frames_for_duration(20.0, 25, maximum=125) == 125
    assert (_frames_for_duration(3.7, 25) - 1) % 4 == 0


def test_example_profile_is_discoverable():
    profile = get_avatar_profile("example-instructor")
    assert profile is not None
    assert profile["prompt_preset"] == "energy_training_studio"
    assert Path(profile["image"]).is_absolute()
    assert Path(profile["master_video"]).is_absolute()


def test_catalog_does_not_expose_profile_paths():
    payload = catalog()
    assert payload["prompts"]
    example = next(item for item in payload["profiles"] if item["id"] == "example-instructor")
    assert "image" not in example
    assert "master_video" not in example
    assert "source_file" not in example


def test_course_example_manifest_is_valid_json():
    payload = json.loads((ROOT / "examples" / "course.example.json").read_text(encoding="utf-8"))
    assert payload["segments"]
    assert {item["role"] for item in payload["segments"]} >= {"hero", "body"}


def test_tts_defaults_target_chinese_mlx_audio():
    cfg = TTSConfig()
    assert "Qwen3-TTS" in cfg.model
    assert cfg.language == "Chinese"
    assert cfg.voice
    assert get_prompt_preset("power_market_lab") is not None
