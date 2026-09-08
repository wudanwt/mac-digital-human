from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    vendor_dir: Path = ROOT / "vendor"
    musetalk_mlx_dir: Path = ROOT / "vendor" / "musetalk-mlx"
    musetalk_upstream_dir: Path = ROOT / "vendor" / "MuseTalk"
    workspace_dir: Path = ROOT / "workspace"
    outputs_dir: Path = ROOT / "outputs"
    default_variant: str = "q8"
    target_fps: int = 25

    def ensure_runtime_dirs(self) -> None:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
