from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from .text import preprocess_text, split_for_synthesis


@dataclass(frozen=True)
class SynthesisResult:
    audio: np.ndarray
    sample_rate: int
    normalized_text: str


class CosyVoiceService:
    """Small, reusable CosyVoice 2 adapter for a digital-human runtime."""

    def __init__(self, bundle_dir: str | Path | None = None, pause_seconds: float = 0.22):
        root = Path(bundle_dir or Path(__file__).resolve().parents[1]).resolve()
        cosy_root = root / "vendor" / "CosyVoice"
        matcha_root = cosy_root / "third_party" / "Matcha-TTS"
        sys.path[:0] = [str(cosy_root), str(matcha_root)]
        from cosyvoice.cli.cosyvoice import CosyVoice2

        self.sample_rate = 24000
        self.pause_seconds = pause_seconds
        self.model = CosyVoice2(str(root / "models" / "CosyVoice2-0.5B"), load_jit=False)
        self.model.model.llm.to(torch.float32)

    def synthesize(
        self,
        text: str,
        reference_audio: str | Path,
        reference_text: str = "",
        speed: float = 1.0,
        instruct: str | None = None,
    ) -> SynthesisResult:
        normalized = preprocess_text(text)
        if not normalized:
            raise ValueError("text is empty after preprocessing")

        use_instruct = bool(instruct and instruct.strip())
        if not use_instruct and not reference_text.strip():
            raise ValueError("reference_text must exactly match reference_audio when instruct is not specified")

        instruct_prompt = ""
        if use_instruct:
            instruct_prompt = instruct.strip()
            if not instruct_prompt.endswith("<|endofprompt|>"):
                instruct_prompt += "<|endofprompt|>"

        outputs: list[torch.Tensor] = []
        pause = torch.zeros(1, int(self.sample_rate * self.pause_seconds), dtype=torch.float32)
        for index, chunk in enumerate(split_for_synthesis(normalized)):
            if index:
                outputs.append(pause)
            if instruct_prompt:
                generator = self.model.inference_instruct2(
                    chunk, instruct_prompt, str(reference_audio), speed=float(speed), stream=False
                )
            else:
                generator = self.model.inference_zero_shot(
                    chunk, reference_text.strip(), str(reference_audio), speed=float(speed), stream=False
                )
            for item in generator:
                outputs.append(item["tts_speech"])
        if not outputs:
            raise RuntimeError("CosyVoice produced no audio")
        audio = torch.concat(outputs, dim=1).squeeze(0).cpu().numpy().astype(np.float32)
        return SynthesisResult(audio=audio, sample_rate=self.sample_rate, normalized_text=normalized)

    def synthesize_to_file(self, output_path: str | Path, **kwargs) -> SynthesisResult:
        result = self.synthesize(**kwargs)
        sf.write(str(output_path), result.audio, result.sample_rate, subtype="PCM_16")
        return result
