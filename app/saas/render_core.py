from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RenderWorkspace:
    root: Path
    slide_dir: Path
    audio_dir: Path
    avatar_dir: Path
    segment_dir: Path

    @classmethod
    def create(cls, root: Path) -> "RenderWorkspace":
        workspace = cls(
            root=root,
            slide_dir=root / "slides",
            audio_dir=root / "audio",
            avatar_dir=root / "avatars",
            segment_dir=root / "segments",
        )
        for path in (workspace.slide_dir, workspace.audio_dir, workspace.avatar_dir, workspace.segment_dir):
            path.mkdir(parents=True, exist_ok=True)
        return workspace


@dataclass(frozen=True)
class PageRenderPlan:
    index: int
    title: str
    narration: str
    layout: str
    override: dict[str, Any]
    slide: Any


@dataclass(frozen=True)
class PageRenderResult:
    index: int
    segment_path: Path
    audio_path: Path
    audio_seconds: float
    audio_source: str
    render_seconds: float | None = None


def build_page_plans(deck, script_entries: list[dict[str, Any]], settings_payload: dict[str, Any]) -> list[PageRenderPlan]:
    """Build immutable per-page execution plans from a prepared deck and snapshot.

    This function is deliberately free of database and queue state.  The same
    page plan can therefore be executed sequentially on the current Mac or later
    leased to any compatible remote worker.
    """

    script_map = {
        int(item.get("index", idx + 1)): item
        for idx, item in enumerate(script_entries)
        if isinstance(item, dict)
    }
    plans: list[PageRenderPlan] = []
    for slide in deck.slides:
        override = dict(script_map.get(slide.index, {}))
        narration = str(
            override.get("narration")
            or override.get("script")
            or slide.narration
            or slide.title
            or f"第{slide.index}页"
        ).strip()
        layout = str(override.get("layout") or settings_payload.get("layout") or slide.layout or "pip")
        plans.append(
            PageRenderPlan(
                index=int(slide.index),
                title=str(slide.title or ""),
                narration=narration,
                layout=layout,
                override=override,
                slide=slide,
            )
        )
    return plans
