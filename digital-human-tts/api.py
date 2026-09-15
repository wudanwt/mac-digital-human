import io
import os

import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from tts_core import CosyVoiceService


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    reference_audio: str
    reference_text: str
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


app = FastAPI(title="Digital Human TTS Core")
service: CosyVoiceService | None = None


@app.on_event("startup")
def load_model() -> None:
    global service
    service = CosyVoiceService(os.environ.get("TTS_BUNDLE_DIR"))


@app.get("/health")
def health() -> dict:
    return {"ok": service is not None, "engine": "cosyvoice2", "sample_rate": 24000}


@app.post("/synthesize")
def synthesize(request: SynthesisRequest) -> Response:
    if service is None:
        raise HTTPException(status_code=503, detail="model is loading")
    try:
        result = service.synthesize(**request.model_dump())
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    buffer = io.BytesIO()
    sf.write(buffer, result.audio, result.sample_rate, format="WAV", subtype="PCM_16")
    return Response(
        buffer.getvalue(),
        media_type="audio/wav",
        headers={"X-Sample-Rate": str(result.sample_rate), "X-Normalized-Text": result.normalized_text},
    )
