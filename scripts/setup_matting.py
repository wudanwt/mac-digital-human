from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TORCH_MODEL_REPO = "ZhengPeng7/BiRefNet-portrait"
TORCH_MODEL_REVISION = "b6561965a70070d9143fd9e558f6ca3c481510db"


def main() -> None:
    model = os.getenv("AVATAR_MATTING_MODEL", "birefnet-portrait").strip() or "birefnet-portrait"
    torch_model_dir = Path(
        os.getenv(
            "AVATAR_MATTING_TORCH_MODEL_DIR",
            str(ROOT / "workspace" / "saas-matting-models" / "pytorch" / "BiRefNet-portrait"),
        )
    ).expanduser()
    from huggingface_hub import snapshot_download
    from rembg import new_session

    print(f"Preparing MPS portrait matting model: {TORCH_MODEL_REPO}")
    snapshot_download(
        TORCH_MODEL_REPO,
        revision=TORCH_MODEL_REVISION,
        local_dir=torch_model_dir,
        allow_patterns=["*.py", "*.json", "*.safetensors", "requirements.txt"],
    )
    print(f"MPS portrait matting model is ready: {torch_model_dir}")

    # Keep the ONNX model available as an automatic fallback for non-MPS hosts.
    print(f"Preparing portrait matting model: {model}")
    new_session(model)
    print("ONNX fallback portrait matting model is ready.")


if __name__ == "__main__":
    main()
