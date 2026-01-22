import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageDraw


BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BACKEND_DIR, "static")
GEN_DIR = os.path.join(STATIC_DIR, "generated")
os.makedirs(GEN_DIR, exist_ok=True)


def _find_floor_map_path(floor: str) -> Optional[str]:
    floor = str(floor).strip()
    candidates = [
        os.path.join(STATIC_DIR, f"floor{floor}.png"),
        os.path.join(STATIC_DIR, "maps", f"floor{floor}.png"),
        os.path.join(STATIC_DIR, f"floor{floor}.PNG"),
        os.path.join(STATIC_DIR, "maps", f"floor{floor}.PNG"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _resolve_floor_for_gallery(gallery: str, map_locations: List[Dict[str, Any]]) -> Optional[str]:
    g = str(gallery).upper().strip()

    for floor_obj in map_locations:
        floor = str(floor_obj.get("floor", "")).strip()
        for block in (floor_obj.get("galleries") or []):
            nums = block.get("numbers") or []
            for n in nums:
                if str(n).upper().strip() == g:
                    return floor
    return None


def _preprocess_variants(img_bgr: np.ndarray) -> List[Tuple[np.ndarray, float]]:
    gray0 = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    variants: List[Tuple[np.ndarray, float]] = []

    for scale in (1.5, 2.0, 2.5, 3.0):
        resized = cv2.resize(gray0, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        _, th_otsu = cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        th_adapt = cv2.adaptiveThreshold(
            resized, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
        )

        k = np.ones((2, 2), np.uint8)
        th_otsu = cv2.morphologyEx(th_otsu, cv2.MORPH_OPEN, k, iterations=1)
        th_adapt = cv2.morphologyEx(th_adapt, cv2.MORPH_OPEN, k, iterations=1)

        variants.append((th_otsu, scale))
        variants.append((th_adapt, scale))

    return variants


def _normalize_ocr_token(t: str) -> str:
    t = (t or "").strip().upper()
    t = "".join(ch for ch in t if ch.isalnum())
    return t


def _score_match(token: str, target: str, conf: float) -> float:
    sim = 100.0 if token == target else 0.0
    if sim == 0.0:
        # allow close matches
        if token and target and (token in target or target in token):
            sim = 85.0
        else:
            sim = 0.0

    return sim * 0.75 + max(0.0, min(conf, 100.0)) * 0.25


def _ocr_find_center(image_path: str, target: str) -> Optional[Tuple[int, int]]:
    target = _normalize_ocr_token(str(target))

    img = cv2.imread(image_path)
    if img is None:
        return None

    best = None 
    config = r"--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    for proc, scale in _preprocess_variants(img):
        data = pytesseract.image_to_data(proc, output_type=pytesseract.Output.DICT, config=config)

        texts = data.get("text", [])
        confs = data.get("conf", [])
        xs = data.get("left", [])
        ys = data.get("top", [])
        ws = data.get("width", [])
        hs = data.get("height", [])

        for i in range(len(texts)):
            tok = _normalize_ocr_token(texts[i])
            if not tok:
                continue

            try:
                conf = float(confs[i])
            except Exception:
                conf = 0.0

            score = _score_match(tok, target, conf)
            if score <= 0:
                continue

            cx_p = xs[i] + ws[i] / 2.0
            cy_p = ys[i] + hs[i] / 2.0

            cx = int(round(cx_p / scale))
            cy = int(round(cy_p / scale))

            if best is None or score > best[0]:
                best = (score, cx, cy)

    if best and best[0] >= 70.0:
        return (best[1], best[2])

    return None


def _draw_marker(draw: ImageDraw.ImageDraw, x: int, y: int, r: int = 18):
    draw.ellipse((x - r, y - r, x + r, y + r), outline=(255, 0, 0, 255), width=6)
    draw.ellipse((x - r // 2, y - r // 2, x + r // 2, y + r // 2), fill=(255, 0, 0, 200))
    draw.line((x - r, y, x + r, y), fill=(255, 255, 255, 255), width=3)
    draw.line((x, y - r, x, y + r), fill=(255, 255, 255, 255), width=3)


def get_gallery_map_image(gallery: str, map_locations: List[Dict[str, Any]]) -> Dict[str, Any]:
    g = str(gallery).upper().strip()

    floor = _resolve_floor_for_gallery(g, map_locations)
    if not floor:
        floor = "2"

    map_path = _find_floor_map_path(floor)
    if not map_path:
        map_path = _find_floor_map_path("2")
        if not map_path:
            return {"image_url": None}

    out_name = f"gallery_{g}_{uuid.uuid4().hex[:10]}.png"
    out_path = os.path.join(GEN_DIR, out_name)

    center = _ocr_find_center(map_path, g)

    base = Image.open(map_path).convert("RGBA")
    draw = ImageDraw.Draw(base)

    if center:
        _draw_marker(draw, int(center[0]), int(center[1]), r=18)

    base.save(out_path, "PNG")

    rel = os.path.relpath(out_path, STATIC_DIR).replace("\\", "/")
    return {"image_url": f"/backend/static/{rel}"}