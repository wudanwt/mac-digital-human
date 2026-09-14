from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class EngineError(RuntimeError):
    """Raised when a local avatar engine cannot prepare or render a job."""


@dataclass
class RenderResult:
    job_id: str
    output: Path
    workspace: Path
    elapsed_seconds: float
    engine: str
    metadata: dict[str, Any] = field(default_factory=dict)
