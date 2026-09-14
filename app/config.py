from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    vendor_dir: Path = ROOT / "vendor"
    workspace_dir: Path = ROOT / "workspace"
    outputs_dir: Path = ROOT / "outputs"

    # MuseTalk fast lip-sync engine.
    musetalk_mlx_dir: Path = ROOT / "vendor" / "musetalk-mlx"
    musetalk_upstream_dir: Path = ROOT / "vendor" / "MuseTalk"
    default_musetalk_variant: str = os.getenv("MUSETALK_VARIANT", "q8")
    musetalk_target_fps: int = 25

    # LongCat Avatar 1.5 high-quality generation engine.
    longcat_mlx_dir: Path = ROOT / "vendor" / "longcat-avatar-mlx"
    longcat_weights_dir: Path = ROOT / "models" / "longcat"
    longcat_adapter_script: Path = ROOT / "scripts" / "longcat_infer.py"
    default_longcat_variant: str = os.getenv("LONGCAT_VARIANT", "q4-merged")
    longcat_height: int = int(os.getenv("LONGCAT_HEIGHT", "480"))
    longcat_width: int = int(os.getenv("LONGCAT_WIDTH", "832"))
    longcat_num_frames: int = int(os.getenv("LONGCAT_NUM_FRAMES", "93"))
    longcat_fps: int = int(os.getenv("LONGCAT_FPS", "25"))
    longcat_default_prompt: str = os.getenv(
        "LONGCAT_PROMPT",
        "A professional Chinese male instructor speaking naturally to camera, "
        "subtle head movement, natural hand gestures, calm confident expression, "
        "clean modern training studio, realistic lighting.",
    )

    @property
    def default_variant(self) -> str:
        """Compatibility alias for the original MuseTalk-only code."""
        return self.default_musetalk_variant

    @property
    def target_fps(self) -> int:
        """Compatibility alias for the original MuseTalk-only code."""
        return self.musetalk_target_fps

    def ensure_runtime_dirs(self) -> None:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.longcat_weights_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
