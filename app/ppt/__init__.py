"""PPT and presentation processing module for digital human micro-courses."""
from .parser import CourseDeck, PresentationParser, SlideInfo
from .renderer import PPTRenderer, SlideCanvasBuilder

__all__ = [
    "CourseDeck",
    "PresentationParser",
    "SlideInfo",
    "PPTRenderer",
    "SlideCanvasBuilder",
]
