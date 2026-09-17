from __future__ import annotations

import os


def main() -> None:
    model = os.getenv("AVATAR_MATTING_MODEL", "birefnet-portrait").strip() or "birefnet-portrait"
    from rembg import new_session

    print(f"Preparing portrait matting model: {model}")
    new_session(model)
    print("Portrait matting model is ready.")


if __name__ == "__main__":
    main()
