from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from ..config import settings


THEMES = (
    {
        "id": "deep-space-grid",
        "name": "深空矩阵",
        "description": "克制的深蓝网格与冷色侧光，适合技术、AI、能源课程。",
        "filename": "builtin-deep-space-grid.png",
    },
    {
        "id": "aurora-cyan",
        "name": "极光青蓝",
        "description": "柔和青蓝极光与深色空间感，画面高级但不抢主体。",
        "filename": "builtin-aurora-cyan.png",
    },
    {
        "id": "executive-blue",
        "name": "商务蓝厅",
        "description": "企业级演播厅质感，适合汇报、培训与正式课程。",
        "filename": "builtin-executive-blue.png",
    },
    {
        "id": "graphite-tech",
        "name": "石墨科技",
        "description": "低饱和石墨灰与金属线条，适合高端商务和专业内容。",
        "filename": "builtin-graphite-tech.png",
    },
    {
        "id": "data-horizon",
        "name": "数据地平线",
        "description": "远景数据光带与地平线层次，适合数据、经营和趋势主题。",
        "filename": "builtin-data-horizon.png",
    },
    {
        "id": "energy-network",
        "name": "能源网络",
        "description": "抽象电网节点与能量连接，适合能源、电力、双碳课程。",
        "filename": "builtin-energy-network.png",
    },
    {
        "id": "halo-stage",
        "name": "未来环幕",
        "description": "大型环形光带与演播厅纵深，适合数字人主讲场景。",
        "filename": "builtin-halo-stage.png",
    },
    {
        "id": "silver-future",
        "name": "银灰未来",
        "description": "明亮银灰科技空间，适合需要更轻、更高级的企业视觉。",
        "filename": "builtin-silver-future.png",
    },
)


_THEME_MAP = {item["id"]: item for item in THEMES}


def background_dir() -> Path:
    path = settings.workspace_dir / "backgrounds"
    path.mkdir(parents=True, exist_ok=True)
    return path


def theme_path(theme_id: str) -> Path:
    item = _THEME_MAP.get(theme_id)
    if item is None:
        raise KeyError(theme_id)
    return background_dir() / item["filename"]


def _vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line((0, y, width, y), fill=color)
    return image


def _glow(image: Image.Image, xy: tuple[int, int], radius: int, color: tuple[int, int, int, int]) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x, y = xy
    draw.ellipse((x - radius // 3, y - radius // 3, x + radius // 3, y + radius // 3), fill=color)
    layer = layer.filter(ImageFilter.GaussianBlur(radius // 3))
    image.alpha_composite(layer)


def _render(theme_id: str, width: int, height: int) -> Image.Image:
    if theme_id == "silver-future":
        base = _vertical_gradient((width, height), (225, 231, 238), (174, 188, 204)).convert("RGBA")
        draw = ImageDraw.Draw(base, "RGBA")
        draw.polygon([(0, height), (0, int(height * .62)), (width, int(height * .83)), (width, height)], fill=(86, 111, 137, 35))
        for x in range(-width // 3, width * 2, max(80, width // 14)):
            draw.line((x, 0, x + width // 3, height), fill=(61, 91, 124, 18), width=2)
        _glow(base, (int(width * .78), int(height * .2)), int(width * .22), (86, 164, 238, 90))
        return base.convert("RGB")

    palette = {
        "deep-space-grid": ((5, 10, 18), (8, 24, 39)),
        "aurora-cyan": ((4, 12, 20), (5, 29, 39)),
        "executive-blue": ((7, 15, 28), (10, 32, 58)),
        "graphite-tech": ((12, 14, 18), (28, 32, 38)),
        "data-horizon": ((4, 10, 19), (11, 25, 43)),
        "energy-network": ((3, 16, 20), (5, 34, 40)),
        "halo-stage": ((5, 8, 16), (13, 20, 35)),
    }
    top, bottom = palette.get(theme_id, palette["deep-space-grid"])
    base = _vertical_gradient((width, height), top, bottom).convert("RGBA")
    draw = ImageDraw.Draw(base, "RGBA")

    if theme_id == "deep-space-grid":
        step = max(42, width // 24)
        for x in range(0, width + 1, step):
            draw.line((x, 0, x, height), fill=(92, 151, 205, 22), width=1)
        for y in range(0, height + 1, step):
            draw.line((0, y, width, y), fill=(92, 151, 205, 18), width=1)
        draw.line((int(width * .08), int(height * .78), int(width * .92), int(height * .78)), fill=(89, 192, 255, 70), width=2)
        _glow(base, (int(width * .82), int(height * .18)), int(width * .20), (46, 134, 255, 75))

    elif theme_id == "aurora-cyan":
        aurora = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ad = ImageDraw.Draw(aurora, "RGBA")
        ad.polygon([(0, int(height * .18)), (int(width * .35), int(height * .05)), (int(width * .78), int(height * .36)), (width, int(height * .16)), (width, int(height * .44)), (int(width * .7), int(height * .56)), (int(width * .28), int(height * .26)), (0, int(height * .42))], fill=(68, 223, 235, 62))
        ad.polygon([(0, int(height * .48)), (int(width * .42), int(height * .25)), (width, int(height * .52)), (width, int(height * .68)), (int(width * .46), int(height * .45)), (0, int(height * .72))], fill=(57, 111, 255, 50))
        base.alpha_composite(aurora.filter(ImageFilter.GaussianBlur(max(20, width // 32))))
        _glow(base, (int(width * .22), int(height * .82)), int(width * .17), (44, 210, 220, 55))

    elif theme_id == "executive-blue":
        draw.rectangle((int(width * .055), int(height * .08), int(width * .945), int(height * .91)), outline=(102, 167, 224, 42), width=2)
        draw.rectangle((int(width * .075), int(height * .11), int(width * .925), int(height * .88)), outline=(127, 189, 242, 18), width=1)
        for x in (int(width * .17), int(width * .83)):
            draw.polygon([(x - width * .035, 0), (x + width * .02, 0), (x - width * .07, height), (x - width * .13, height)], fill=(55, 118, 181, 26))
        _glow(base, (int(width * .5), int(height * .08)), int(width * .20), (75, 146, 224, 60))

    elif theme_id == "graphite-tech":
        for k in range(-height, width, max(70, width // 20)):
            draw.line((k, 0, k + height, height), fill=(195, 210, 225, 15), width=1)
        draw.line((int(width * .08), int(height * .16), int(width * .46), int(height * .16)), fill=(170, 201, 226, 38), width=2)
        draw.line((int(width * .54), int(height * .84), int(width * .92), int(height * .84)), fill=(94, 167, 221, 35), width=2)
        _glow(base, (int(width * .9), int(height * .08)), int(width * .13), (95, 155, 210, 38))

    elif theme_id == "data-horizon":
        horizon = int(height * .68)
        _glow(base, (int(width * .5), horizon), int(width * .28), (50, 150, 255, 65))
        draw.line((0, horizon, width, horizon), fill=(86, 192, 255, 95), width=2)
        for x in range(0, width, max(55, width // 24)):
            for y in range(horizon + 30, height, max(42, height // 16)):
                alpha = max(8, 32 - int((y - horizon) / max(1, height - horizon) * 22))
                draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(100, 192, 255, alpha))

    elif theme_id == "energy-network":
        points = [
            (.12, .22), (.26, .34), (.39, .19), (.52, .42), (.66, .24), (.82, .35),
            (.18, .68), (.35, .61), (.57, .72), (.73, .58), (.88, .76),
        ]
        px = [(int(width * x), int(height * y)) for x, y in points]
        edges = ((0,1),(1,2),(1,6),(2,3),(3,4),(3,7),(3,8),(4,5),(5,9),(6,7),(7,8),(8,9),(9,10))
        for a, b in edges:
            draw.line((*px[a], *px[b]), fill=(61, 214, 204, 42), width=2)
        for x, y in px:
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(94, 232, 218, 100))
        _glow(base, (int(width * .55), int(height * .48)), int(width * .22), (31, 181, 171, 48))

    elif theme_id == "halo-stage":
        cx, cy = int(width * .5), int(height * .5)
        for scale, alpha in ((.84, 22), (.68, 35), (.52, 48)):
            rx, ry = int(width * scale / 2), int(height * scale / 2)
            draw.ellipse((cx-rx, cy-ry, cx+rx, cy+ry), outline=(100, 182, 255, alpha), width=max(1, width // 700))
        draw.polygon([(0,height),(0,int(height*.82)),(width,height*.72),(width,height)], fill=(14, 31, 51, 95))
        _glow(base, (cx, int(height * .38)), int(width * .18), (64, 136, 238, 55))

    return base.convert("RGB")


@lru_cache(maxsize=32)
def render_preview_bytes(theme_id: str, width: int = 640, height: int = 360) -> bytes:
    from io import BytesIO

    if theme_id not in _THEME_MAP:
        raise KeyError(theme_id)
    image = _render(theme_id, width, height)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def ensure_builtin_backgrounds(force: bool = False) -> dict[str, Path]:
    output: dict[str, Path] = {}
    for item in THEMES:
        target = theme_path(item["id"])
        if force or not target.exists():
            image = _render(item["id"], 1920, 1080)
            image.save(target, format="PNG", optimize=True)
        output[item["id"]] = target
    return output


def list_themes() -> list[dict[str, str]]:
    return [dict(item) for item in THEMES]
