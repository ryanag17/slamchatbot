import os
import re
import uuid

from PIL import Image, ImageDraw
import cv2
import pytesseract

BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BACKEND_DIR, ".."))

STATIC_DIR = os.path.join(BACKEND_DIR, "static")
GEN_DIR = os.path.join(STATIC_DIR, "generated")
os.makedirs(GEN_DIR, exist_ok=True)

def _map_image_path_from_json(map_image_value: str) -> str | None:
    if not map_image_value:
        return None
    base = os.path.basename(map_image_value)  # floor2.png
    candidates = [
        os.path.join(STATIC_DIR, base),        # backend/static/floor2.png
        os.path.join(PROJECT_ROOT, base),      # fallback
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def _find_floor_map_for_gallery(gallery: str, map_locations: list) -> str | None:
    g = str(gallery).upper()
    for floor in map_locations:
        for sec in (floor.get("galleries") or []):
            nums = [str(x).upper() for x in (sec.get("numbers") or [])]
            if g in nums:
                return _map_image_path_from_json(sec.get("map_image"))
    return None

def _draw_star(draw: ImageDraw.ImageDraw, x: int, y: int, r: int = 18):
    draw.ellipse((x-r, y-r, x+r, y+r), outline=(255, 0, 0), width=6)
    draw.line((x-r, y, x+r, y), fill=(255, 0, 0), width=6)
    draw.line((x, y-r, x, y+r), fill=(255, 0, 0), width=6)

def _norm_token(s: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", (s or "").upper())

def _ocr_try(gray_img, target: str):
    """
    Run pytesseract.image_to_data with different PSMs and char whitelists.
    Return best (cx, cy) or None.
    """
    target_u = _norm_token(target)
    if not target_u:
        return None

    # If it's purely numeric, use a digits whitelist to help.
    digits_only = target_u.isdigit()
    whitelist = "0123456789" if digits_only else "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    # Try multiple PSM modes (6 and 11 are commonly good for maps/labels)
    psms = [6, 11, 4, 3]

    best_center = None
    best_score = 0

    for psm in psms:
        config = f'--oem 3 --psm {psm} -c tessedit_char_whitelist={whitelist}'
        data = pytesseract.image_to_data(gray_img, output_type=pytesseract.Output.DICT, config=config)

        for i, txt in enumerate(data.get("text", [])):
            t = _norm_token(txt)
            if not t:
                continue

            score = 0
            if t == target_u:
                score = 100
            elif target_u in t or t in target_u:
                score = 80

            # extra: numeric label often recognized with junk, so partial match is useful
            if digits_only and score == 0:
                # e.g. "216." or "2l6" sometimes; handle common OCR confusion lightly
                t2 = t.replace("I", "1").replace("L", "1").replace("O", "0")
                if t2 == target_u:
                    score = 95
                elif target_u in t2:
                    score = 75

            if score > best_score:
                x = data["left"][i]
                y = data["top"][i]
                w = data["width"][i]
                h = data["height"][i]
                best_center = (int(x + w // 2), int(y + h // 2))
                best_score = score

        if best_score >= 100:
            break

    return best_center

def _preprocess_variants(img_bgr):
    """
    Yield multiple preprocessed grayscale images to improve OCR hit rate.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # 1) plain gray
    yield gray

    # 2) scaled up 2x (helps small text)
    yield cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    # 3) Otsu threshold
    yield cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    # 4) inverted Otsu (sometimes text is light)
    inv = cv2.bitwise_not(gray)
    yield cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    # 5) adaptive threshold
    yield cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 35, 11)

    # 6) scaled + Otsu
    gray2 = cv2.resize(gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
    yield cv2.threshold(gray2, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

def _find_label_center(image_path: str, target: str):
    img = cv2.imread(image_path)
    if img is None:
        return None

    # Try multiple preprocess pipelines until we get a hit
    for variant in _preprocess_variants(img):
        try:
            center = _ocr_try(variant, target)
            if center:
                return center
        except Exception:
            continue

    return None

def get_gallery_map_image(gallery: str, map_locations: list) -> dict | None:
    gallery = str(gallery).upper()
    map_path = _find_floor_map_for_gallery(gallery, map_locations)
    if not map_path:
        return None

    marked_path = os.path.join(GEN_DIR, f"gallery_{gallery}_{uuid.uuid4().hex[:8]}.png")

    # Always output a generated file so the frontend has something stable to load
    base = Image.open(map_path).convert("RGBA")

    center = None
    try:
        center = _find_label_center(map_path, gallery)
    except Exception:
        center = None

    draw = ImageDraw.Draw(base)
    if center:
        _draw_star(draw, int(center[0]), int(center[1]), r=18)

    base.save(marked_path, "PNG")

    rel = os.path.relpath(marked_path, STATIC_DIR).replace("\\", "/")
    return {"image_url": f"/backend/static/{rel}"}
