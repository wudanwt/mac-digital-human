#!/usr/bin/env python3
"""
Generate 4 high-resolution 1080P virtual studio background images.
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def create_preset_backgrounds(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    width, height = 1920, 1080

    # 1. Modern Tech Blue Studio
    # A sleek dark-blue radial gradient with subtle vignette
    tech_arr = np.zeros((height, width, 3), dtype=np.uint8)
    center_x, center_y = width // 2, int(height * 0.45)
    y_coords, x_coords = np.ogrid[:height, :width]
    dist = np.sqrt(((x_coords - center_x) / (width * 0.7)) ** 2 + ((y_coords - center_y) / (height * 0.7)) ** 2)
    dist = np.clip(dist, 0.0, 1.4)
    r = (14 * (1 - dist * 0.6) + 4 * (dist * 0.6)).astype(np.uint8)
    g = (48 * (1 - dist * 0.7) + 8 * (dist * 0.7)).astype(np.uint8)
    b = (96 * (1 - dist * 0.6) + 24 * (dist * 0.6)).astype(np.uint8)
    tech_arr[:, :, 0] = r
    tech_arr[:, :, 1] = g
    tech_arr[:, :, 2] = b
    tech_img = Image.fromarray(tech_arr)
    draw = ImageDraw.Draw(tech_img, "RGBA")
    draw.ellipse([width * 0.2, height * 0.25, width * 0.8, height * 0.65], fill=(30, 90, 170, 30))
    tech_img = tech_img.filter(ImageFilter.GaussianBlur(15))
    tech_img.save(output_dir / "studio_tech_blue.jpg", quality=95)

    # 2. Executive Dark Stage
    exec_arr = np.zeros((height, width, 3), dtype=np.uint8)
    dist_exec = np.sqrt(((x_coords - width // 2) / (width * 0.8)) ** 2 + ((y_coords - height // 2) / (height * 0.8)) ** 2)
    dist_exec = np.clip(dist_exec, 0.0, 1.3)
    r = (28 * (1 - dist_exec * 0.6) + 10 * (dist_exec * 0.6)).astype(np.uint8)
    g = (30 * (1 - dist_exec * 0.6) + 11 * (dist_exec * 0.6)).astype(np.uint8)
    b = (36 * (1 - dist_exec * 0.5) + 15 * (dist_exec * 0.5)).astype(np.uint8)
    exec_arr[:, :, 0] = r
    exec_arr[:, :, 1] = g
    exec_arr[:, :, 2] = b
    exec_img = Image.fromarray(exec_arr)
    draw = ImageDraw.Draw(exec_img, "RGBA")
    draw.ellipse([width * 0.25, height * 0.15, width * 0.75, height * 0.75], fill=(50, 56, 75, 45))
    exec_img = exec_img.filter(ImageFilter.GaussianBlur(25))
    exec_img.save(output_dir / "studio_executive_dark.jpg", quality=95)

    # 3. Academic Warm Hall
    acad_arr = np.zeros((height, width, 3), dtype=np.uint8)
    dist_acad = np.sqrt(((x_coords - width * 0.65) / (width * 0.75)) ** 2 + ((y_coords - height * 0.4) / (height * 0.75)) ** 2)
    dist_acad = np.clip(dist_acad, 0.0, 1.4)
    r = (45 * (1 - dist_acad * 0.7) + 16 * (dist_acad * 0.7)).astype(np.uint8)
    g = (32 * (1 - dist_acad * 0.7) + 14 * (dist_acad * 0.7)).astype(np.uint8)
    b = (28 * (1 - dist_acad * 0.6) + 18 * (dist_acad * 0.6)).astype(np.uint8)
    acad_arr[:, :, 0] = r
    acad_arr[:, :, 1] = g
    acad_arr[:, :, 2] = b
    acad_img = Image.fromarray(acad_arr)
    draw = ImageDraw.Draw(acad_img, "RGBA")
    draw.ellipse([width * 0.35, height * 0.1, width * 0.9, height * 0.7], fill=(80, 50, 30, 40))
    acad_img = acad_img.filter(ImageFilter.GaussianBlur(30))
    acad_img.save(output_dir / "studio_academic_warm.jpg", quality=95)

    # 4. Cyber Neon Minimalist
    cyber_arr = np.zeros((height, width, 3), dtype=np.uint8)
    dist_cyber = np.sqrt(((x_coords - width * 0.35) / (width * 0.7)) ** 2 + ((y_coords - height * 0.5) / (height * 0.7)) ** 2)
    dist_cyber = np.clip(dist_cyber, 0.0, 1.4)
    r = (38 * (1 - dist_cyber * 0.6) + 12 * (dist_cyber * 0.6)).astype(np.uint8)
    g = (16 * (1 - dist_cyber * 0.7) + 8 * (dist_cyber * 0.7)).astype(np.uint8)
    b = (56 * (1 - dist_cyber * 0.6) + 20 * (dist_cyber * 0.6)).astype(np.uint8)
    cyber_arr[:, :, 0] = r
    cyber_arr[:, :, 1] = g
    cyber_arr[:, :, 2] = b
    cyber_img = Image.fromarray(cyber_arr)
    draw = ImageDraw.Draw(cyber_img, "RGBA")
    draw.ellipse([width * 0.1, height * 0.2, width * 0.6, height * 0.7], fill=(70, 20, 95, 45))
    cyber_img = cyber_img.filter(ImageFilter.GaussianBlur(25))
    cyber_img.save(output_dir / "studio_cyber_neon.jpg", quality=95)

    print(f"Successfully generated 4 preset studio backgrounds into {output_dir}")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "workspace" / "backgrounds"
    create_preset_backgrounds(out)
