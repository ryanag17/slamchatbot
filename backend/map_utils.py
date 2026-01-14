import json
import cv2
import os

DATA_PATH = "backend/data/map_locations.json"
MAPS_DIR = "backend/static/maps"
OUT_DIR = "backend/static/generated"

os.makedirs(OUT_DIR, exist_ok=True)

with open(DATA_PATH) as f:
    MAP_DATA = json.load(f)

def generate_gallery_map(gallery_number):
    gallery_number = str(gallery_number)

    for floor in MAP_DATA:
        for group in floor["galleries"]:
            if gallery_number in group["numbers"]:
                img_path = os.path.join(MAPS_DIR, os.path.basename(group["map_image"]))
                image = cv2.imread(img_path)

                h, w, _ = image.shape
                center = (w // 2, h // 2)

                cv2.drawMarker(
                    image,
                    center,
                    (255, 0, 0),
                    cv2.MARKER_STAR,
                    markerSize=45,
                    thickness=3
                )

                out_file = f"generated/gallery_{gallery_number}.png"
                cv2.imwrite(f"backend/static/{out_file}", image)

                return f"static/{out_file}"

    return None
