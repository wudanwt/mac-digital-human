import html
import re


def preprocess_text(text: str) -> str:
    cleaned = html.unescape(text or "")
    cleaned = cleaned.replace("\u00a0", " ").replace("\u3000", " ")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[—–]{1,2}\s*(?=\n|$)", "：", cleaned)
    cleaned = re.sub(r"\s+([，。！？；：、])", r"\1", cleaned)
    return cleaned.strip()


def split_for_synthesis(text: str, max_chars: int = 48) -> list[str]:
    pieces = [p.strip() for p in re.findall(r"[^。！？；!?\n]+[。！？；!?]?", text) if p.strip()]
    chunks: list[str] = []
    for piece in pieces:
        if len(piece) <= max_chars:
            chunks.append(piece)
            continue
        clauses = [p.strip() for p in re.findall(r"[^，,：:]+[，,：:]?", piece) if p.strip()]
        current = ""
        for clause in clauses:
            if current and len(current) + len(clause) > max_chars:
                chunks.append(current)
                current = clause
            else:
                current += clause
        if current:
            chunks.append(current)
    return chunks or [text]
