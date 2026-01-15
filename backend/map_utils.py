# backend/map_utils.py
import json
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

# In-memory cache: floor_map_path -> { "216": [x,y], ... }
_FLOOR_INDEX_CACHE: Dict[str, Dict[str, Tuple[int, int]]] = {}

# Persisted cache on disk (so reboot doesn’t reset speed)
_CACHE_FILE = os.path.join(GEN_DIR, "ocr_gallery_centers_cache.json")


def _load_disk_cache() -> Dict[str, Dict[str, Tuple[int, int]]]:
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        out: Dict[str, Dict[str, Tuple[int, int]]] = {}
        for k, v in raw.items():
            if isinstance(v, dict):
                out[k] = {}
                for tok, xy in v.items():
                    if (
                        isinstance(tok, str)
                        and isinstance(xy, list)
                        and len(xy) == 2
                        and isinstance(xy[0], int)
                        and isinstance(xy[1], int)
                    ):
                        out[k][tok] = (xy[0], xy[1])
        return out
    except Exception:
        return {}


def _save_disk_cache(cache: Dict[str, Dict[str, Tuple[int, int]]]) -> None:
    try:
        serial = {k: {tok: [xy[0], xy[1]] for tok, xy in v.items()} for k, v in cache.items()}
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(serial, f)
    except Exception:
        pass


# Load disk cache once at import
_FLOOR_INDEX_CACHE.update(_load_disk_cache())


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


def _normalize_ocr_token(t: str) -> str:
    t = (t or "").strip().upper()
    t = "".join(ch for ch in t if ch.isalnum())
    return t


def _build_floor_index(map_path: str) -> Dict[str, Tuple[int, int]]:
    """
    FAST path:
    - OCR once per floor map
    - store centers for all gallery numbers we detect
    """
    # Already cached?
    if map_path in _FLOOR_INDEX_CACHE:
        return _FLOOR_INDEX_CACHE[map_path]

    img = cv2.imread(map_path)
    if img is None:
        _FLOOR_INDEX_CACHE[map_path] = {}
        return {}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # One good, fast preprocessing pass (much faster than many variants)
    scale = 2.0
    resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, th = cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Light morphology to help digits
    k = np.ones((2, 2), np.uint8)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, k, iterations=1)

    config = r"--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    data = pytesseract.image_to_data(th, output_type=pytesseract.Output.DICT, config=config)

    texts = data.get("text", [])
    confs = data.get("conf", [])
    xs = data.get("left", [])
    ys = data.get("top", [])
    ws = data.get("width", [])
    hs = data.get("height", [])

    best_for_token: Dict[str, Tuple[float, int, int]] = {}  # tok -> (conf, x, y)

    for i in range(len(texts)):
        tok = _normalize_ocr_token(texts[i])
        if not tok:
            continue

        # We mostly care about gallery-ish tokens: 2-3 digits, possibly trailing letter (216, 216A)
        if not (len(tok) in (2, 3, 4)):
            continue
        if not any(ch.isdigit() for ch in tok):
            continue

        try:
            conf = float(confs[i])
        except Exception:
            conf = 0.0

        # center in processed space
        cx_p = xs[i] + ws[i] / 2.0
        cy_p = ys[i] + hs[i] / 2.0

        # scale back to original image coords
        cx = int(round(cx_p / scale))
        cy = int(round(cy_p / scale))

        old = best_for_token.get(tok)
        if (old is None) or (conf > old[0]):
            best_for_token[tok] = (conf, cx, cy)

    index = {tok: (v[1], v[2]) for tok, v in best_for_token.items() if v[0] >= 40.0}

    _FLOOR_INDEX_CACHE[map_path] = index
    _save_disk_cache(_FLOOR_INDEX_CACHE)
    return index


def _slow_fallback_find_center(map_path: str, target: str) -> Optional[Tuple[int, int]]:
    """
    Slow fallback (your original style):
    Only used if the cached index doesn't find the token.
    """
    target = _normalize_ocr_token(str(target))
    img = cv2.imread(map_path)
    if img is None:
        return None

    gray0 = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    config = r"--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    best = None  # (score, cx, cy)

    for scale in (1.5, 2.0, 2.5, 3.0):
        resized = cv2.resize(gray0, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        _, th_otsu = cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        th_adapt = cv2.adaptiveThreshold(
            resized, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
        )

        k = np.ones((2, 2), np.uint8)
        th_otsu = cv2.morphologyEx(th_otsu, cv2.MORPH_OPEN, k, iterations=1)
        th_adapt = cv2.morphologyEx(th_adapt, cv2.MORPH_OPEN, k, iterations=1)

        for proc in (th_otsu, th_adapt):
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

                sim = 100.0 if tok == target else (85.0 if (tok in target or target in tok) else 0.0)
                score = sim * 0.75 + max(0.0, min(conf, 100.0)) * 0.25
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
    """
    Returns {"image_url": "/backend/static/generated/<file>.png"}
    Now fast:
      - deterministic output name per floor+gallery (reused)
      - OCR index cached per floor
      - slow fallback only if needed
    """
    g = str(gallery).upper().strip()

    floor = _resolve_floor_for_gallery(g, map_locations) or "2"
    map_path = _find_floor_map_path(floor) or _find_floor_map_path("2")
    if not map_path:
        return {"image_url": None}

    # Deterministic output filename (reuse instead of re-generating endlessly)
    safe_g = "".join(ch for ch in g if ch.isalnum())
    out_name = f"gallery_{safe_g}_floor{floor}.png"
    out_path = os.path.join(GEN_DIR, out_name)

    # If we've already generated it, return instantly
    if os.path.exists(out_path):
        return {"image_url": f"/backend/static/generated/{out_name}"}

    # Find center quickly via cached index
    index = _build_floor_index(map_path)
    center = index.get(g)

    # Try normalized variants (216 vs 216A etc)
    if not center:
        g_norm = _normalize_ocr_token(g)
        center = index.get(g_norm)

    # Slow fallback once if not found
    if not center:
        center = _slow_fallback_find_center(map_path, g)
        if center:
            # update cache so next time it's instant
            index[_normalize_ocr_token(g)] = center
            _FLOOR_INDEX_CACHE[map_path] = index
            _save_disk_cache(_FLOOR_INDEX_CACHE)

    base = Image.open(map_path).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    if center:
        _draw_marker(draw, center[0], center[1], r=18)

    out = Image.alpha_composite(base, overlay)
    out.save(out_path)

    return {"image_url": f"/backend/static/generated/{out_name}"}
