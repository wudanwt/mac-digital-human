"""Backward-compatible imports for the avatar engine package.

New code should import from ``app.engines``. This module remains so existing
scripts/tests using ``app.engine`` continue to work.
"""

from .engines import EngineError, MuseTalkMLXEngine, RenderResult

__all__ = [
    "EngineError",
    "RenderResult",
    "MuseTalkMLXEngine",
]

