from pathlib import Path

from tts_core import CosyVoiceService


root = Path(__file__).resolve().parent
tts = CosyVoiceService(root)
tts.synthesize_to_file(
    root / "output.wav",
    text="大家好。欢迎来到数字人演示。",
    reference_audio=root / "voices" / "wudan" / "reference.wav",
    reference_text="今天欢迎来到会议的现场，我很开心，也很荣幸的给大家介绍我们最新的产品。",
    speed=1.0,
)
