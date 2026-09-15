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


settings = Settings()

