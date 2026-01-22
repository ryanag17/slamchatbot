from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os

from nlp import respond

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")
CORS(app)

@app.get("/api/health")
def api_health():
    return jsonify({"status": "ok"})

@app.post("/api/respond")
def api_respond():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"text": "Please type a message.", "image_url": None, "suggestions": []})

    out = respond(text)

    if isinstance(out, str):
        return jsonify({"text": out, "image_url": None, "suggestions": []})

    return jsonify({
        "text": out.get("text", ""),
        "image_url": out.get("image_url"),
        "suggestions": out.get("suggestions", [])
    })

# Serve backend
@app.get("/backend/static/<path:filename>")
def serve_backend_static(filename):
    static_dir = os.path.join(BACKEND_DIR, "static")
    return send_from_directory(static_dir, filename)

if __name__ == "__main__": 
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
