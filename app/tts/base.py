from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TTSError(RuntimeError):
    """Raised when a TTS provider cannot synthesize audio."""


class TTSProvider(Protocol):
    name: str

    def readiness(self) -> dict: ...

    def synthesize(self, text: str, output: Path, **kwargs) -> Path: ...

    def release(self) -> None: ...
