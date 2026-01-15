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
    """
    JSON uses: "maps/floor2.png"
    Your real PNGs (per your structure) are in backend/static/ (and sometimes people put them in project root).
    So we search both places.
    """
    if not map_image_value:
        return None

    base = os.path.basename(map_image_value)  # e.g. floor2.png

    candidates = [
        os.path.join(STATIC_DIR, base),        # backend/static/floor2.png  (your setup)
        os.path.join(PROJECT_ROOT, base),      # project root/floor2.png    (fallback)
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

        # allow stairs/elevators/coat checks to match numeric tokens like "219"
        for key in ["stairs", "elevators", "coat_checks"]:
            nums = [str(x).upper() for x in (floor.get(key) or [])]
            if g in nums:
                galleries = floor.get("galleries") or []
                if galleries:
                    return _map_image_path_from_json(galleries[0].get("map_image"))
    return None

def _draw_star(draw: ImageDraw.ImageDraw, x: int, y: int, r: int = 18):
    # Red target marker
    draw.ellipse((x-r, y-r, x+r, y+r), outline=(255, 0, 0), width=6)
    draw.line((x-r, y, x+r, y), fill=(255, 0, 0), width=6)
    draw.line((x, y-r, x, y+r), fill=(255, 0, 0), width=6)

def _ocr_find_text_box(image_path: str, target: str):
    """
    Uses pytesseract to find bounding boxes for text.
    Returns (cx, cy) center of best match or None.
    """
    target = str(target).upper()

    img = cv2.imread(image_path)
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)

    best = None
    best_score = 0

    for i, txt in enumerate(data.get("text", [])):
        t = (txt or "").strip().upper()
        if not t:
            continue

        score = 100 if t == target else 0
        if score == 0:
            # allow "236E" etc
            if re.sub(r"\W+", "", t) == re.sub(r"\W+", "", target):
                score = 90
            elif target in t:
                score = 70

        if score > best_score:
            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]
            best = (x + w // 2, y + h // 2)
            best_score = score

    return best

def _url_for_known_map_file(map_path: str) -> str:
    """
    Convert a filesystem path (either backend/static/floor2.png or project_root/floor2.png)
    into a URL that the frontend can actually load.
    """
    base = os.path.basename(map_path)

    # If the file lives under backend/static, serve it via /backend/static/<filename>
    static_candidate = os.path.join(STATIC_DIR, base)
    if os.path.exists(static_candidate):
        return f"/backend/static/{base}"

    # If you happened to put it in project root, Flask static will serve it at /<filename>
    return f"/{base}"

def get_gallery_map_image(gallery: str, map_locations: list) -> dict | None:
    """
    Returns:
      { "image_url": "/backend/static/generated/<file>.png" }
    """
    gallery = str(gallery).upper()
    map_path = _find_floor_map_for_gallery(gallery, map_locations)
    if not map_path:
        return None

    marked_path = os.path.join(GEN_DIR, f"gallery_{gallery}_{uuid.uuid4().hex[:8]}.png")

    try:
        center = _ocr_find_text_box(map_path, gallery)

        base = Image.open(map_path).convert("RGBA")
        draw = ImageDraw.Draw(base)

        # If OCR found the text, mark it. If not, still return the plain map (saved copy).
        if center:
            _draw_star(draw, int(center[0]), int(center[1]), r=18)

        base.save(marked_path, "PNG")

        rel = os.path.relpath(marked_path, STATIC_DIR).replace("\\", "/")
        return {"image_url": f"/backend/static/{rel}"}

    except Exception:
        # If Tesseract isn't installed or OCR fails, at least return the floor map image URL.
        return {"image_url": _url_for_known_map_file(map_path)}
