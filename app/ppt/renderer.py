import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Sequence

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from .parser import CourseDeck, SlideInfo

logger = logging.getLogger("mac_digital_human.ppt.renderer")


FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Find the best available TrueType font or fallback to default."""
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, max_chars_per_line: int = 34) -> list[str]:
    """Wrap Chinese/English text cleanly into lines."""
    lines: list[str] = []
    paragraphs = text.split("\n")
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        while len(para) > max_chars_per_line:
            lines.append(para[:max_chars_per_line])
            para = para[max_chars_per_line:]
        if para:
            lines.append(para)
    return lines


class SlideCanvasBuilder:
    """Generates modern, professional 1920x1080 slide cards from slide metadata (fallback)."""

    @staticmethod
    def draw_slide(
        slide: SlideInfo,
        course_title: str,
        total_slides: int,
        width: int = 1920,
        height: int = 1080,
    ) -> Image.Image:
        # Base canvas with elegant dark navy gradient background
        canvas = Image.new("RGB", (width, height), (13, 19, 33))
        draw = ImageDraw.Draw(canvas)

        # Draw subtle gradient backdrop
        for y in range(height):
            ratio = y / height
            r = int(13 + ratio * 8)
            g = int(19 + ratio * 12)
            b = int(33 + ratio * 18)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Fonts
        badge_font = _get_font(22)
        title_font = _get_font(52)
        bullet_font = _get_font(34)
        footer_font = _get_font(20)

        # Header decorative bar & badge
        draw.rectangle([(80, 60), (width - 80, 64)], fill=(45, 60, 85))
        draw.rectangle([(80, 60), (220, 64)], fill=(59, 130, 246))  # Accent line

        badge_text = f"微课课件  |  SLIDE {slide.index:02d} / {total_slides:02d}"
        draw.text((80, 80), badge_text, font=badge_font, fill=(148, 163, 184))

        # Main slide title
        slide_title = slide.title or f"第 {slide.index} 节 核心要点"
        draw.text((80, 130), slide_title, font=title_font, fill=(248, 250, 252))

        # Card container for slide content
        card_x0, card_y0 = 80, 230
        card_x1, card_y1 = width - 80, height - 120

        # Semi-transparent card body
        card_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card_overlay)
        card_draw.rounded_rectangle(
            [(card_x0, card_y0), (card_x1, card_y1)],
            radius=20,
            fill=(22, 32, 54, 180),
            outline=(51, 65, 85, 220),
            width=2,
        )
        canvas.paste(card_overlay, (0, 0), card_overlay)
        draw = ImageDraw.Draw(canvas)

        # Render bullet points inside card
        curr_y = card_y0 + 50
        bullets = slide.bullets if slide.bullets else ([slide.raw_text] if slide.raw_text else ["本页重点内容讲解"])

        # Display bullets (up to 7 items/lines)
        items_drawn = 0
        for item in bullets:
            if items_drawn >= 7 or curr_y > card_y1 - 80:
                break
            wrapped = _wrap_text(item, max_chars_per_line=40)
            for line_idx, line in enumerate(wrapped):
                if curr_y > card_y1 - 60:
                    break
                if line_idx == 0:
                    # Bullet accent dot
                    dot_radius = 6
                    dot_cx = card_x0 + 60
                    dot_cy = curr_y + 18
                    draw.ellipse(
                        [(dot_cx - dot_radius, dot_cy - dot_radius), (dot_cx + dot_radius, dot_cy + dot_radius)],
                        fill=(59, 130, 246),
                    )
                    draw.text((card_x0 + 90, curr_y), line, font=bullet_font, fill=(226, 232, 240))
                else:
                    draw.text((card_x0 + 90, curr_y), line, font=bullet_font, fill=(203, 213, 225))
                curr_y += 56
                items_drawn += 1
            curr_y += 18

        # Footer
        draw.text((80, height - 70), course_title, font=footer_font, fill=(100, 116, 139))
        page_indicator = f"PAGE {slide.index} OF {total_slides}"
        draw.text((width - 240, height - 70), page_indicator, font=footer_font, fill=(100, 116, 139))

        return canvas


def _export_pptx_via_powerpoint(pptx_path: Path, temp_work_dir: Path) -> Path | None:
    """Export authentic PPTX visual slides into PDF using macOS Microsoft PowerPoint."""
    if not Path("/Applications/Microsoft PowerPoint.app").exists():
        return None

    temp_pdf_name = f"_dh_ppt_export_{uuid.uuid4().hex[:8]}.pdf"
    desktop_pdf = Path(os.path.expanduser("~/Desktop")) / temp_pdf_name
    final_pdf = temp_work_dir / f"{pptx_path.stem}_full.pdf"

    # AppleScript for PowerPoint export with macOS standard sandbox path
    script = f'''
tell application "Microsoft PowerPoint"
    set theFile to (POSIX file "{pptx_path.resolve()}")
    open theFile
    delay 1.5
    set outHfs to ((path to desktop folder as text) & "{temp_pdf_name}")
    save active presentation in outHfs as save as PDF
    close active presentation saving no
end tell
'''
    try:
        logger.info(f"Exporting full visual slides from {pptx_path.name} via PowerPoint...")
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=25)
        if res.returncode == 0 and desktop_pdf.exists():
            temp_work_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(desktop_pdf), str(final_pdf))
            logger.info(f"Successfully exported full visual PDF: {final_pdf}")
            return final_pdf
        else:
            logger.warning(f"PowerPoint export failed (code {res.returncode}): {res.stderr.strip()}")
    except Exception as exc:
        logger.warning(f"PowerPoint automation exception: {exc}")
    finally:
        if desktop_pdf.exists():
            try:
                desktop_pdf.unlink()
            except Exception:
                pass
    return None


def _export_pptx_via_libreoffice(pptx_path: Path, temp_work_dir: Path) -> Path | None:
    """Export PPTX to PDF using LibreOffice headless if available."""
    soffice_cmd = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice_cmd:
        return None

    temp_work_dir.mkdir(parents=True, exist_ok=True)
    try:
        # API preview requests and the render center may export concurrently.
        # A shared LibreOffice profile serializes those processes and can make a
        # perfectly valid deck exceed the old 30-second timeout.
        with tempfile.TemporaryDirectory(prefix="lo-profile-", dir=temp_work_dir) as profile_dir:
            profile_url = Path(profile_dir).resolve().as_uri()
            logger.info("Exporting PPTX via LibreOffice: %s", soffice_cmd)
            res = subprocess.run(
                [
                    soffice_cmd,
                    f"-env:UserInstallation={profile_url}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(temp_work_dir),
                    str(pptx_path.resolve()),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
        expected_pdf = temp_work_dir / f"{pptx_path.stem}.pdf"
        if res.returncode == 0 and expected_pdf.exists() and expected_pdf.stat().st_size > 0:
            return expected_pdf
        logger.warning(
            "LibreOffice export failed (code %s): %s %s",
            res.returncode,
            res.stdout.strip(),
            res.stderr.strip(),
        )
    except Exception as exc:
        logger.warning(f"LibreOffice conversion failed: {exc}")
    return None


class PPTRenderer:
    """Renders authentic presentation slides into 1920x1080 full visual video-ready images."""

    @classmethod
    def _render_pdf_pages_to_images(
        cls,
        pdf_path: Path,
        slides: list[SlideInfo],
        output_dir: Path,
        course_title: str,
        total_slides: int,
        width: int = 1920,
        height: int = 1080,
    ) -> list[Path]:
        """Renders vector PDF pages directly into 1920x1080 PNG images using PyMuPDF."""
        doc = pymupdf.open(str(pdf_path))
        rendered_paths: list[Path] = []
        for slide in slides:
            page_idx = slide.index - 1
            target = output_dir / f"slide_{slide.index:03d}.png"
            if page_idx < len(doc):
                page = doc[page_idx]
                scale_x = width / page.rect.width
                scale_y = height / page.rect.height
                mat = pymupdf.Matrix(scale_x, scale_y)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                pix.save(str(target))
            else:
                img = SlideCanvasBuilder.draw_slide(slide, course_title, total_slides, width, height)
                img.save(str(target), format="PNG")
            slide.image_path = target
            rendered_paths.append(target)
        return rendered_paths

    @classmethod
    def render_deck(
        cls,
        deck: CourseDeck,
        output_dir: str | Path,
        width: int = 1920,
        height: int = 1080,
        require_authentic: bool = False,
    ) -> list[Path]:
        """Renders authentic 1920x1080 slide images for all slides in the deck."""
        out = Path(output_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)

        # Strategy 1: Source file is already a PDF
        if deck.source_file.suffix.lower() == ".pdf":
            logger.info("Rendering directly from source PDF with 100% vector fidelity...")
            return cls._render_pdf_pages_to_images(deck.source_file, deck.slides, out, deck.title, deck.total_slides, width, height)

        # Strategy 2: Check for companion PDF (e.g., lecture.pdf alongside lecture.pptx)
        companion_pdf = deck.source_file.with_suffix(".pdf")
        if companion_pdf.exists():
            logger.info(f"Found companion PDF: {companion_pdf.name}, rendering authentic full slide images...")
            return cls._render_pdf_pages_to_images(companion_pdf, deck.slides, out, deck.title, deck.total_slides, width, height)

        def render_exported_pdf(pdf_path: Path) -> list[Path]:
            if require_authentic:
                with pymupdf.open(str(pdf_path)) as pdf:
                    if len(pdf) != deck.total_slides:
                        raise RuntimeError(
                            f"Exported slide count {len(pdf)} does not match source slide count {deck.total_slides}"
                        )
            return cls._render_pdf_pages_to_images(pdf_path, deck.slides, out, deck.title, deck.total_slides, width, height)

        # Strategy 3: Export authentic visual slides via PowerPoint automation on macOS
        exported_pdf = _export_pptx_via_powerpoint(deck.source_file, out)
        if exported_pdf and exported_pdf.exists():
            logger.info("Successfully extracted full visual slides via PowerPoint export.")
            return render_exported_pdf(exported_pdf)

        # Strategy 4: LibreOffice headless export fallback
        lo_pdf = _export_pptx_via_libreoffice(deck.source_file, out)
        if lo_pdf and lo_pdf.exists():
            logger.info("Successfully extracted full visual slides via LibreOffice export.")
            return render_exported_pdf(lo_pdf)

        # Strategy 5: Safety Fallback to synthetic modern Canvas card
        if require_authentic:
            raise RuntimeError("Could not export authentic PPT slides; refusing to replace them with synthetic cards")
        logger.warning("No office/PDF renderer available. Falling back to synthetic modern Canvas cards.")
        rendered_paths: list[Path] = []
        for slide in deck.slides:
            target = out / f"slide_{slide.index:03d}.png"
            img = SlideCanvasBuilder.draw_slide(slide, deck.title, deck.total_slides, width, height)
            img.save(str(target), format="PNG")
            slide.image_path = target
            rendered_paths.append(target)

        return rendered_paths
