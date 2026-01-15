import os
import re
import time
from typing import Optional, Tuple, Dict, Any

from PIL import Image, ImageDraw
import numpy as np

# OpenCV + Tesseract are optional at runtime (we handle failures gracefully)
try:
    import cv2  # opencv-python-headless
except Exception:
    cv2 = None

try:
    import pytesseract
except Exception:
    pytesseract = None


# ------------------------------------------------------------
# Path helpers (robust even if _file_ is undefined)
# ------------------------------------------------------------
def _safe_base_dir() -> str:
    """
    Returns the directory this file is in, even if run in environments
    where _file_ is not defined (VS Code interactive, etc.)
    """
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()


def get_project_root() -> str:
    """
    Your structure:
      project_root/
        index.html, chat.html, styles.css, floor1.png, floor2.png, floor3.png
        backend/
          app.py
          map_utils.py  <- this file
          static/
            generated/
          data/
            ...
    """
    base = _safe_base_dir()

    # If we're inside ".../backend", root is parent
    if os.path.basename(base).lower() == "backend":
        return os.path.dirname(base)

    # If we are somehow deeper, try to climb until we find backend folder
    cur = base
    for _ in range(5):
        if os.path.isdir(os.path.join(cur, "backend")):
            return cur
        cur = os.path.dirname(cur)

    # fallback
    return base


def get_backend_dir() -> str:
    root = get_project_root()
    return os.path.join(root, "backend")


def get_generated_dir() -> str:
    backend = get_backend_dir()
    gen = os.path.join(backend, "static", "generated")
    os.makedirs(gen, exist_ok=True)
    return gen


def find_map_image_on_disk(map_basename: str) -> Optional[str]:
    """
    Your floor images are in the project root (e.g., /floor2.png).
    Sometimes JSON may reference "maps/floor2.png" -> basename still floor2.png.
    """
    root = get_project_root()

    # Look in root first (your real location)
    p1 = os.path.join(root, map_basename)
    if os.path.isfile(p1):
        return p1

    # Also allow root/maps if you ever move them
    p2 = os.path.join(root, "maps", map_basename)
    if os.path.isfile(p2):
        return p2

    # Also allow backend/static/maps
    p3 = os.path.join(get_backend_dir(), "static", "maps", map_basename)
    if os.path.isfile(p3):
        return p3

    return None


# ------------------------------------------------------------
# Drawing utilities
# ------------------------------------------------------------
def _draw_star(draw: ImageDraw.ImageDraw, center: Tuple[int, int], radius: int = 18):
    """
    Draw a solid 5-point star.
    """
    cx, cy = center
    points = []
    # 5-point star coordinates
    for i in range(10):
        angle = i * 36  # degrees
        r = radius if i % 2 == 0 else radius // 2
        rad = np.deg2rad(angle - 90)
        x = cx + int(r * np.cos(rad))
        y = cy + int(r * np.sin(rad))
        points.append((x, y))

    # fill star + outline
    draw.polygon(points, fill=(255, 215, 0), outline=(0, 0, 0))  # gold w/ black outline


def _draw_marker(img: Image.Image, center: Tuple[int, int]) -> Image.Image:
    """
    Adds a star marker + halo circle to make it obvious.
    """
    out = img.copy()
    draw = ImageDraw.Draw(out)

    cx, cy = center

    # halo circle
    halo_r = 28
    draw.ellipse((cx - halo_r, cy - halo_r, cx + halo_r, cy + halo_r),
                 outline=(255, 0, 0), width=5)

    # star
    _draw_star(draw, (cx, cy), radius=18)
    return out


# ------------------------------------------------------------
# OCR search
# ------------------------------------------------------------
def _normalize_gallery_token(token: str) -> str:
    return (token or "").strip().upper()


def _ocr_find_token_center(image_path: str, token: str) -> Optional[Tuple[int, int]]:
    """
    Uses pytesseract to locate token on image.
    Returns center (x,y) if found.
    """
    if pytesseract is None or cv2 is None:
        return None