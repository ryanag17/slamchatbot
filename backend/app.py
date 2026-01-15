import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from nlp import get_python_response
from map_utils import get_gallery_map_image_url

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BACKEND_DIR, "static")

app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    static_url_path="/backend/static"
)
CORS(app)

# ---------- serve frontend files from project root ----------
@app.get("/")
def serve_index():
    return send_from_directory(ROOT_DIR, "index.html")

@app.get("/index.html")
def serve_index_explicit():
    return send_from_directory(ROOT_DIR, "index.html")

@app.get("/chat.html")
def serve_chat():
    return send_from_directory(ROOT_DIR, "chat.html")

@app.get("/styles.css")
def serve_css():
    return send_from_directory(ROOT_DIR, "styles.css")

@app.get("/<path:filename>")
def serve_root_files(filename):
    # allow serving images like SLAM_Logo.png at root
    return send_from_directory(ROOT_DIR, filename)

# ---------- API ----------
@app.post("/api/respond")
def respond():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"text": "Please type a question.", "image_url": None, "used_translation": False})

    # 1) If user asked for gallery location: return map image + text
    gallery_num = extract_gallery_number(text)
    if gallery_num is not None and is_location_question(text):
        img_url = get_gallery_map_image_url(gallery_num)
        if img_url:
            return jsonify({
                "text": f"Here is where gallery {gallery_num} is:",
                "image_url": img_url,
                "used_translation": False
            })
        return jsonify({
            "text": f"I found gallery {gallery_num} in the data, but I couldn’t generate the map image yet (OCR missing or map file not found).",
            "image_url": None,
            "used_translation": False
        })

    # 2) Otherwise use Python NLP
    result = get_python_response(text)
    return jsonify(result)

def extract_gallery_number(text: str):
    import re
    m = re.search(r"\bgallery\s*([0-9]{1,3}[A-Za-z]?)\b", text, flags=re.IGNORECASE)
    if not m:
        # allow "where is 219" if they omitted gallery word
        m2 = re.search(r"\b([0-9]{3})\b", text)
        if m2:
            return m2.group(1)
        return None
    return m.group(1)

def is_location_question(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in ["where", "located", "find", "location", "map"])

if __name__ == "__main__":
    # For VM: run `python app.py` then visit http://34.6.19.211/
    app.run(host="0.0.0.0", port=80, debug=False)
