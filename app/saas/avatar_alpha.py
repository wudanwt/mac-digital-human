from __future__ import annotations

import subprocess
from pathlib import Path


class AlphaCycleCache:
    """Decode one precomputed master alpha and reuse it across course slides."""

    def __init__(self) -> None:
        self._frames: dict[str, list] = {}

    @staticmethod
    def cycle_index(length: int, index: int) -> int:
        if length <= 1:
            return 0
        cycle = length * 2
        pos = index % cycle
        return pos if pos < length else cycle - pos - 1

    def _load_frames(self, source: Path):
        import cv2

        key = str(source.resolve())
        if key in self._frames:
            return self._frames[key]
        cap = cv2.VideoCapture(str(source))
        if not cap.isOpened():
            raise RuntimeError(f"cannot open avatar alpha asset: {source}")
        frames = []
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        finally:
            cap.release()
        if not frames:
            raise RuntimeError("avatar alpha asset contains no frames")
        self._frames[key] = frames
        return frames

    def build_for_output(self, source_alpha: Path, avatar_video: Path, target: Path) -> Path:
        import cv2

        source_frames = self._load_frames(source_alpha)
        cap = cv2.VideoCapture(str(avatar_video))
        if not cap.isOpened():
            raise RuntimeError(f"cannot inspect generated avatar video: {avatar_video}")
        frame_count = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or source_frames[0].shape[1])
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or source_frames[0].shape[0])
        cap.release()

        target.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{width}x{height}",
            "-r", f"{fps:.6f}", "-i", "pipe:0",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "8", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(target),
        ]
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if proc.stdin is None:
            raise RuntimeError("failed to open alpha encoder")
        try:
            for i in range(frame_count):
                frame = source_frames[self.cycle_index(len(source_frames), i)]
                if frame.shape[:2] != (height, width):
                    frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)
                proc.stdin.write(frame.tobytes())
        finally:
            proc.stdin.close()
        stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        code = proc.wait()
        if code != 0 or not target.exists():
            target.unlink(missing_ok=True)
            raise RuntimeError(stderr.strip() or f"alpha cycle encoder failed ({code})")
        return target
