import json
import os
import re
from PIL import Image
import cv2
import pytesseract

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "map_locations.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
MAPS_DIR = os.path.join(STATIC_DIR, "maps")
OUT_DIR = os.path.join(STATIC_DIR, "generated")

os.makedirs(OUT_DIR, exist_ok=True)

with open(DATA_PATH, "r", encoding="utf-8") as f:
    MAP_DATA = json.load(f)

def find_floor_and_map_for_gallery(gallery_number: str):
    g = str(gallery_number)
    for floor_obj in MAP_DATA:
        floor = str(floor_obj.get("floor", ""))
        map_img_rel = None

        # match galleries list
        for cat in floor_obj.get("galleries", []):
            nums = [str(x) for x in cat.get("numbers", [])]
            if g in nums:
                map_img_rel = cat.get("map_image")  # like "maps/floor2.png"
                return floor, map_img_rel

        # also match stairs/elevators/etc if needed
        for key in ["stairs", "elevators", "coat_checks"]:
            vals = [str(x) for x in floor_obj.get(key, [])]
            if g in vals:
                # use the first map image we can find from any category on that floor
                galleries = floor_obj.get("galleries", [])
                if galleries:
                    map_img_rel = galleries[0].get("map_image")
                    return floor, map_img_rel

        # restrooms: location field
        for rr in floor_obj.get("restrooms", []):
            if str(rr.get("location","")) == g:
                galleries = floor_obj.get("galleries", [])
                if galleries:
                    map_img_rel = galleries[0].get("map_image")
                    return floor, map_img_rel

    return None, None

def ocr_find_number_bbox(image_bgr, target_text: str):
    """
    Returns (x, y, w, h) bbox if found via OCR, else None.
    """
    target = str(target_text).strip()

    # OCR works better on high contrast
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3,3), 0)
    thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 31, 2)

    # pytesseract boxes
    data = pytesseract.image_to_data(
        thr,
        output_type=pytesseract.Output.DICT,
        config="--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    )

    for i, txt in enumerate(data.get("text", [])):
        if not txt:
            continue
        cleaned = re.sub(r"\s+", "", txt)
        if cleaned == target:
            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]
            return (x, y, w, h)

    return None

def draw_star(image_bgr, center, size=55):
    cv2.drawMarker(
        image_bgr,
        center,
        (255, 0, 0),
        markerType=cv2.MARKER_STAR,
        markerSize=size,
        thickness=3,
        line_type=cv2.LINE_AA
    )

def get_gallery_map_image_url(gallery_number: str):
    g = str(gallery_number)
    floor, map_rel = find_floor_and_map_for_gallery(g)
    if not map_rel:
        return None

    # map_rel is like "maps/floor2.png"
    map_path = os.path.join(STATIC_DIR, map_rel.replace("/", os.sep))
    if not os.path.exists(map_path):
        return None

    out_filename = f"gallery_{g}.png"
    out_path = os.path.join(OUT_DIR, out_filename)

    # cache: if already created, reuse
    if os.path.exists(out_path):
        return f"/backend/static/generated/{out_filename}"

    image_bgr = cv2.imread(map_path)
    if image_bgr is None:
        return None

    bbox = ocr_find_number_bbox(image_bgr, g)
    if bbox:
        x, y, w, h = bbox
        cx = int(x + w / 2)
        cy = int(y + h / 2)
        draw_star(image_bgr, (cx, cy), size=55)
    else:
        # fallback: star in center if OCR fails
        h, w = image_bgr.shape[:2]
        draw_star(image_bgr, (w//2, h//2), size=55)

    cv2.imwrite(out_path, image_bgr)
    return f"/backend/static/generated/{out_filename}"
