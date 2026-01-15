import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from nlp import generate_response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

app = Flask(__name__, static_folder=PROJECT_ROOT, static_url_path="")
CORS(app)


@app.get("/")
def index():
    return send_from_directory(PROJECT_ROOT, "index.html")


@app.get("/chat.html")
def chat():
    return send_from_directory(PROJECT_ROOT, "chat.html")


@app.post("/api/respond")
def api_respond():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"text": "Please type a message first.", "map": None, "detected_lang": "en", "translated": False})
    out = generate_response(text)
    return jsonify(out)


if __name__ == "__main__":
    # Listen on all interfaces so the VM public IP can reach it.
    app.run(host="0.0.0.0", port=8080, debug=False)
