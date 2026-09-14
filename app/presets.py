from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import settings


@dataclass(frozen=True)
class PromptPreset:
    id: str
    name: str
    prompt: str
    description: str = ""
    height: int = 480
    width: int = 832
    num_frames: int = 93


BUILTIN_PROMPTS: tuple[PromptPreset, ...] = (
    PromptPreset(
        id="energy_training_studio",
        name="能源科技培训演播室",
        description="正式培训、课程开场，科技感但不过度炫技。",
        prompt=(
            "A professional Chinese male energy-industry instructor speaking naturally to camera, "
            "confident and approachable, subtle head movement, restrained natural hand gestures, "
            "standing in a clean modern energy technology training studio, large subtle power-grid "
            "data visualization in the background, realistic cinematic soft lighting, medium shot, "
            "stable camera, natural skin texture, professional corporate training style."
        ),
    ),
    PromptPreset(
        id="executive_briefing",
        name="高管汇报 / 正式简报",
        description="稳重、克制、适合管理层汇报和政策解读。",
        prompt=(
            "A professional Chinese male executive presenter delivering a concise briefing to camera, "
            "calm confident expression, minimal controlled gestures, dark modern corporate briefing room, "
            "soft key light, clean background, medium close-up, stable camera, realistic business documentary style."
        ),
    ),
    PromptPreset(
        id="power_market_lab",
        name="电力市场数字专家",
        description="电力交易、现货市场、AI Agent 产品介绍。",
        prompt=(
            "A Chinese male power-market expert presenting to camera inside a realistic digital power trading lab, "
            "subtle electricity market charts and grid topology screens behind him, natural speaking motion, "
            "small purposeful hand gestures, confident analytical expression, cinematic but realistic lighting, "
            "medium shot, stable camera, premium enterprise technology presentation."
        ),
    ),
    PromptPreset(
        id="warm_classroom",
        name="亲和课堂",
        description="更轻松、有交流感的内部培训。",
        prompt=(
            "A friendly Chinese male instructor teaching naturally to camera in a warm modern classroom, "
            "gentle smile, relaxed subtle head movement, occasional natural hand gestures, warm soft daylight, "
            "clean wood and neutral interior, medium shot, stable camera, realistic educational video style."
        ),
    ),
    PromptPreset(
        id="neutral_closeup",
        name="中性稳定近景",
        description="最少场景干扰，优先身份一致性。",
        prompt=(
            "A professional Chinese male presenter speaking directly to camera, neutral clean studio background, "
            "calm expression, very subtle head movement, minimal gestures, soft even lighting, chest-up framing, "
            "stable camera, photorealistic natural skin texture, no dramatic motion."
        ),
        height=432,
        width=768,
        num_frames=61,
    ),
)


def list_prompt_presets() -> list[dict]:
    return [asdict(preset) for preset in BUILTIN_PROMPTS]


def get_prompt_preset(preset_id: str | None) -> PromptPreset | None:
    if not preset_id:
        return None
    return next((item for item in BUILTIN_PROMPTS if item.id == preset_id), None)


def _profiles_dir() -> Path:
    path = settings.root / "profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_avatar_profiles() -> list[dict]:
    """Read local profile JSON files.

    Profiles intentionally stay outside Git by default because they usually
    point at private portrait / voice-reference files.
    """
    profiles: list[dict] = []
    for file in sorted(_profiles_dir().glob("*.json")):
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
            profile_id = str(payload.get("id") or file.stem)
            image = Path(str(payload.get("image", ""))).expanduser()
            if image and not image.is_absolute():
                image = (file.parent / image).resolve()
            profiles.append(
                {
                    "id": profile_id,
                    "name": str(payload.get("name") or profile_id),
                    "image": str(image) if str(payload.get("image", "")) else "",
                    "prompt_preset": payload.get("prompt_preset", "energy_training_studio"),
                    "prompt": payload.get("prompt", ""),
                    "tts": payload.get("tts", {}),
                    "source_file": str(file),
                }
            )
        except (OSError, ValueError, TypeError):
            continue
    return profiles


def get_avatar_profile(profile_id: str | None) -> dict | None:
    if not profile_id:
        return None
    return next((item for item in list_avatar_profiles() if item["id"] == profile_id), None)
