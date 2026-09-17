from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app.saas.speech_preview_service import synthesis_fingerprint


def _voice(**overrides):
    values = {
        "id": "voice-1",
        "provider": "cosyvoice",
        "reference_asset_id": "asset-1",
        "transcript": "参考逐字稿",
        "settings_json": json.dumps({"pause_seconds": 0.22}),
        "updated_at": datetime(2026, 9, 18, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_speech_preview_hash_ignores_layout_but_tracks_tts_inputs() -> None:
    voice = _voice()
    base = synthesis_fingerprint(
        text="今天优优认识了谁？",
        scope="page",
        voice=voice,
        course_settings={"layout": "pip", "wizard_step": 2, "speed": 1.0},
    )
    layout_changed = synthesis_fingerprint(
        text="今天优优认识了谁？",
        scope="page",
        voice=voice,
        course_settings={"layout": "split", "wizard_step": 4, "speed": 1.0},
    )
    corrected = synthesis_fingerprint(
        text="今天优优认识了谁？",
        scope="page",
        voice=voice,
        course_settings={
            "layout": "split",
            "speed": 1.0,
            "tts": {"pronunciation_replacements": {"优优": "悠悠"}},
        },
    )
    assert layout_changed == base
    assert corrected != base
    assert synthesis_fingerprint(
        text="今天优优认识了谁？",
        scope="selection",
        voice=voice,
        course_settings={"speed": 1.0},
    ) != base
