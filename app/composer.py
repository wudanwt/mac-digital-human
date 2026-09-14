from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ComposeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ComposeConfig:
    width: int = 1920
    height: int = 1080
    fps: int = 25
    crf: int = 18
    audio_rate: int = 48000


def media_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ComposeError(f"ffprobe failed for {path}: {proc.stderr.strip()}")
    try:
        payload = json.loads(proc.stdout)
        return float(payload["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ComposeError(f"unable to read duration: {path}") from exc


class CourseComposer:
    def __init__(self, config: ComposeConfig | None = None) -> None:
        self.config = config or ComposeConfig()

    @staticmethod
    def _run(cmd: list[str]) -> None:
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            raise ComposeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")

    def normalize(self, source: Path, target: Path) -> Path:
        if not source.exists():
            raise ComposeError(f"clip not found: {source}")
        cfg = self.config
        target.parent.mkdir(parents=True, exist_ok=True)
        vf = (
            f"scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease,"
            f"pad={cfg.width}:{cfg.height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps={cfg.fps},format=yuv420p"
        )
        self._run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-vf",
                vf,
                "-af",
                f"aresample={cfg.audio_rate}",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                str(cfg.crf),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(target),
            ]
        )
        return target

    def concat(self, clips: list[Path], output: Path, workdir: Path) -> Path:
        if not clips:
            raise ComposeError("no clips to compose")
        normalized_dir = workdir / "normalized"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        normalized: list[Path] = []
        for index, clip in enumerate(clips, start=1):
            target = normalized_dir / f"{index:03d}.mp4"
            normalized.append(self.normalize(clip, target))

        concat_file = workdir / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{path.resolve().as_posix()}'\n" for path in normalized),
            encoding="utf-8",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        return output
