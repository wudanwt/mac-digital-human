"""Subtitles generator for digital human micro-courses."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SubtitleItem:
    index: int
    start_seconds: float
    end_seconds: float
    text: str

    def to_srt(self) -> str:
        start_fmt = _format_timestamp(self.start_seconds)
        end_fmt = _format_timestamp(self.end_seconds)
        return f"{self.index}\n{start_fmt} --> {end_fmt}\n{self.text}\n\n"

    def to_vtt(self) -> str:
        start_fmt = _format_timestamp(self.start_seconds, separator=".")
        end_fmt = _format_timestamp(self.end_seconds, separator=".")
        return f"{start_fmt} --> {end_fmt}\n{self.text}\n\n"


def _format_timestamp(seconds: float, separator: str = ",") -> str:
    millis = int(round(seconds * 1000))
    hours = millis // 3600000
    millis %= 3600000
    minutes = millis // 60000
    millis %= 60000
    secs = millis // 1000
    millis %= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def split_sentences(text: str) -> list[str]:
    """Split narration text by Chinese and English punctuation into readable subtitle clauses."""
    # Split by major sentence terminators and commas if sentence is long
    raw_clauses = re.split(r"([。！？!?;；\n]+)", text)
    sentences: list[str] = []
    curr = ""
    for token in raw_clauses:
        if re.match(r"[。！？!?;；\n]+", token):
            curr += token.strip()
            if curr:
                sentences.append(curr)
                curr = ""
        else:
            curr += token.strip()
    if curr:
        sentences.append(curr)

    # Subdivide clauses if longer than 22 characters
    final_clauses: list[str] = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if len(s) > 22 and ("，" in s or "," in s):
            sub_parts = re.split(r"([，,])", s)
            sub_curr = ""
            for sub_token in sub_parts:
                if sub_token in {"，", ","}:
                    sub_curr += sub_token
                    if len(sub_curr) >= 10:
                        final_clauses.append(sub_curr)
                        sub_curr = ""
                else:
                    sub_curr += sub_token
            if sub_curr:
                final_clauses.append(sub_curr)
        else:
            final_clauses.append(s)

    return [c.strip() for c in final_clauses if c.strip()]


class SubtitlesGenerator:
    """Generates aligned SRT and WebVTT subtitles for micro-courses."""

    @classmethod
    def generate_segment_subtitles(
        cls,
        text: str,
        duration: float,
        start_offset: float = 0.0,
        start_index: int = 1,
    ) -> list[SubtitleItem]:
        clauses = split_sentences(text)
        if not clauses or duration <= 0:
            return []

        # Weight duration by character count
        total_chars = sum(max(1, len(c)) for c in clauses)
        items: list[SubtitleItem] = []
        curr_time = start_offset

        for idx, clause in enumerate(clauses):
            clause_chars = max(1, len(clause))
            clause_duration = (clause_chars / total_chars) * duration
            # Ensure minimum duration of 0.8s
            clause_duration = max(0.8, clause_duration)
            end_time = min(start_offset + duration, curr_time + clause_duration)

            items.append(
                SubtitleItem(
                    index=start_index + idx,
                    start_seconds=curr_time,
                    end_seconds=end_time,
                    text=clause,
                )
            )
            curr_time = end_time

        return items

    @classmethod
    def build_srt_file(cls, items: list[SubtitleItem], output_path: str | Path) -> Path:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(item.to_srt() for item in items)
        out.write_text(content, encoding="utf-8")
        return out

    @classmethod
    def build_vtt_file(cls, items: list[SubtitleItem], output_path: str | Path) -> Path:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        content = "WEBVTT\n\n" + "".join(item.to_vtt() for item in items)
        out.write_text(content, encoding="utf-8")
        return out
