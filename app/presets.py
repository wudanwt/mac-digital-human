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


def _resolve_profile_path(file: Path, value: str | None) -> str:
    if not value:
        return ""
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    p1 = (file.parent / path).resolve()
    if p1.exists():
        return str(p1)
    p2 = (settings.root / path).resolve()
    if p2.exists():
        return str(p2)
    return str(p1)


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
            tts = dict(payload.get("tts") or {})
            if tts.get("ref_audio"):
                tts["ref_audio"] = _resolve_profile_path(file, str(tts["ref_audio"]))
            profiles.append(
                {
                    "id": profile_id,
                    "name": str(payload.get("name") or profile_id),
                    "image": _resolve_profile_path(file, payload.get("image")),
                    "master_video": _resolve_profile_path(file, payload.get("master_video")),
                    "prompt_preset": payload.get("prompt_preset", "energy_training_studio"),
                    "prompt": payload.get("prompt", ""),
                    "tts": tts,
                    "source_file": str(file.resolve()),
                }
            )
        except (OSError, ValueError, TypeError):
            continue
    return profiles


import re
import shutil
import subprocess
import time
import uuid


def create_avatar_profile(
    name: str,
    image_bytes: bytes,
    image_filename: str,
    profile_id: str | None = None,
    audio_bytes: bytes | None = None,
    audio_filename: str | None = None,
    ref_text: str = "",
    master_video_bytes: bytes | None = None,
    master_video_filename: str | None = None,
    prompt_preset: str = "energy_training_studio",
    prompt: str = "",
    provider: str = "audio8",
) -> dict:
    """Create a new persistent digital human avatar profile with custom image and voice."""
    raw_name = name.strip() or "未命名讲师"
    if profile_id:
        clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", profile_id).strip().lower()
    else:
        # Generate safe slug from timestamp and uuid
        clean_id = f"avatar_{int(time.time())}_{uuid.uuid4().hex[:4]}"

    if not clean_id:
        clean_id = f"avatar_{int(time.time())}_{uuid.uuid4().hex[:4]}"

    profiles_root = _profiles_dir()
    assets_dir = profiles_root / "assets" / clean_id
    assets_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save Avatar Image
    img_ext = Path(image_filename or "portrait.png").suffix.lower() or ".png"
    if img_ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        img_ext = ".png"
    portrait_file = assets_dir / f"portrait{img_ext}"
    portrait_file.write_bytes(image_bytes)

    # 2. Save Reference Voice Audio
    saved_ref_audio = ""
    if audio_bytes and len(audio_bytes) > 0:
        raw_audio_ext = Path(audio_filename or "voice.wav").suffix.lower() or ".wav"
        temp_audio_file = assets_dir / f"temp_voice{raw_audio_ext}"
        temp_audio_file.write_bytes(audio_bytes)

        # Standardize to 24kHz single-channel WAV for TTS voice cloning
        target_wav = assets_dir / "voice.wav"
        try:
            cmd = ["ffmpeg", "-y", "-i", str(temp_audio_file), "-ar", "24000", "-ac", "1", str(target_wav)]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if res.returncode == 0 and target_wav.exists():
                saved_ref_audio = f"./assets/{clean_id}/voice.wav"
                if temp_audio_file != target_wav:
                    temp_audio_file.unlink(missing_ok=True)
            else:
                saved_ref_audio = f"./assets/{clean_id}/{temp_audio_file.name}"
        except Exception:
            saved_ref_audio = f"./assets/{clean_id}/{temp_audio_file.name}"

    # 3. Master Video: User uploaded OR auto-generated breathing anchor from portrait image
    saved_master_video = ""
    if master_video_bytes and len(master_video_bytes) > 0:
        vid_ext = Path(master_video_filename or "master.mp4").suffix.lower() or ".mp4"
        vid_file = assets_dir / f"master{vid_ext}"
        vid_file.write_bytes(master_video_bytes)
        saved_master_video = f"./assets/{clean_id}/{vid_file.name}"
    elif portrait_file.exists():
        # Auto-create lightweight breathing anchor video for MuseTalk MLX hardware acceleration
        anchor_mp4 = assets_dir / "master.mp4"
        try:
            import cv2
            import numpy as np
            from PIL import Image

            im = Image.open(portrait_file).convert("RGB")
            w, h = im.size
            target_h = 1280
            target_w = int(w * (target_h / h))
            target_w = target_w - (target_w % 2)
            im_resized = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            vw = cv2.VideoWriter(str(anchor_mp4), fourcc, 25, (target_w, target_h))
            np_base = np.array(im_resized)
            for _ in range(50):
                vw.write(cv2.cvtColor(np_base, cv2.COLOR_RGB2BGR))
            vw.release()
            if anchor_mp4.exists():
                saved_master_video = f"./assets/{clean_id}/master.mp4"
        except Exception:
            saved_master_video = ""

    # 4. Construct JSON Payload
    payload = {
        "id": clean_id,
        "name": raw_name,
        "image": f"./assets/{clean_id}/{portrait_file.name}",
        "master_video": saved_master_video,
        "prompt_preset": prompt_preset or "energy_training_studio",
        "prompt": prompt.strip(),
        "tts": {
            "provider": provider or "audio8",
            "voice": clean_id if saved_ref_audio else "default",
            "threads": 5,
            "ref_audio": saved_ref_audio,
            "ref_text": ref_text.strip(),
        },

    }

    profile_json_file = profiles_root / f"{clean_id}.json"
    profile_json_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return get_avatar_profile(clean_id) or payload


def delete_avatar_profile(profile_id: str) -> bool:
    """Delete a custom avatar profile and its associated media assets."""
    if profile_id == "dan":
        return False  # Protect builtin profile

    profiles_root = _profiles_dir()
    profile_json_file = profiles_root / f"{profile_id}.json"
    if not profile_json_file.exists():
        return False

    profile_json_file.unlink(missing_ok=True)
    assets_dir = profiles_root / "assets" / profile_id
    if assets_dir.exists():
        shutil.rmtree(assets_dir, ignore_errors=True)
    return True


def get_avatar_profile(profile_id: str | None) -> dict | None:
    if not profile_id:
        return None
    return next((item for item in list_avatar_profiles() if item["id"] == profile_id), None)


def update_avatar_profile(
    profile_id: str,
    name: str | None = None,
    image_bytes: bytes | None = None,
    image_filename: str | None = None,
    audio_bytes: bytes | None = None,
    audio_filename: str | None = None,
    ref_text: str | None = None,
    master_video_bytes: bytes | None = None,
    master_video_filename: str | None = None,
    prompt_preset: str | None = None,
    prompt: str | None = None,
    provider: str | None = None,
) -> dict:
    """Update existing avatar profile metadata and media assets."""
    clean_id = (profile_id or "").strip()
    if not clean_id:
        raise ValueError("Profile ID 不能为空")

    profiles_root = _profiles_dir()
    profile_json_file = profiles_root / f"{clean_id}.json"
    if not profile_json_file.exists():
        raise FileNotFoundError(f"未找到数字人人设: {clean_id}")

    try:
        payload = json.loads(profile_json_file.read_text(encoding="utf-8"))
    except Exception as err:
        raise ValueError(f"人设配置文件损坏: {err}")

    assets_dir = profiles_root / "assets" / clean_id
    assets_dir.mkdir(parents=True, exist_ok=True)

    # 1. Update Name
    if name is not None and name.strip():
        payload["name"] = name.strip()

    # 2. Update Prompt / Preset
    if prompt_preset is not None and prompt_preset.strip():
        payload["prompt_preset"] = prompt_preset.strip()
    if prompt is not None:
        payload["prompt"] = prompt.strip()

    # 3. Update Image
    if image_bytes and len(image_bytes) > 0:
        img_ext = Path(image_filename or "portrait.png").suffix.lower() or ".png"
        if img_ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            img_ext = ".png"
        portrait_file = assets_dir / f"portrait{img_ext}"
        portrait_file.write_bytes(image_bytes)
        payload["image"] = f"./assets/{clean_id}/{portrait_file.name}"

    # 4. Update Master Video (Key Feature)
    if master_video_bytes and len(master_video_bytes) > 0:
        vid_ext = Path(master_video_filename or "master.mp4").suffix.lower() or ".mp4"
        if vid_ext not in {".mp4", ".mov", ".mkv", ".webm"}:
            vid_ext = ".mp4"
        vid_file = assets_dir / f"master{vid_ext}"
        vid_file.write_bytes(master_video_bytes)
        payload["master_video"] = f"./assets/{clean_id}/{vid_file.name}"

    # 5. Update Voice Clone / Audio & TTS
    tts = payload.setdefault("tts", {})
    if provider is not None and provider.strip():
        tts["provider"] = provider.strip()
    if ref_text is not None:
        tts["ref_text"] = ref_text.strip()

    if audio_bytes and len(audio_bytes) > 0:
        raw_audio_ext = Path(audio_filename or "voice.wav").suffix.lower() or ".wav"
        temp_audio_file = assets_dir / f"temp_voice{raw_audio_ext}"
        temp_audio_file.write_bytes(audio_bytes)

        target_wav = assets_dir / "voice.wav"
        try:
            cmd = ["ffmpeg", "-y", "-i", str(temp_audio_file), "-ar", "24000", "-ac", "1", str(target_wav)]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if res.returncode == 0 and target_wav.exists():
                tts["ref_audio"] = f"./assets/{clean_id}/voice.wav"
                tts["voice"] = clean_id
                if temp_audio_file != target_wav:
                    temp_audio_file.unlink(missing_ok=True)
            else:
                tts["ref_audio"] = f"./assets/{clean_id}/{temp_audio_file.name}"
                tts["voice"] = clean_id
        except Exception:
            tts["ref_audio"] = f"./assets/{clean_id}/{temp_audio_file.name}"
            tts["voice"] = clean_id

    profile_json_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return get_avatar_profile(clean_id) or payload

