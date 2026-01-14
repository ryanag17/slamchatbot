import json
import re
import spacy
from langdetect import detect
from transformers import MarianMTModel, MarianTokenizer

nlp = spacy.load("en_core_web_sm")

# -------- Load JSON DATA --------
with open("backend/data/museum_info.json") as f:
    MUSEUM_INFO = json.load(f)

with open("backend/data/exhibitions.json") as f:
    EXHIBITIONS = json.load(f)

with open("backend/data/slam_art.json") as f:
    ARTWORKS = json.load(f)

# -------- Translation Models --------
TRANSLATION_MODELS = {
    "de": "Helsinki-NLP/opus-mt-de-en",
    "fr": "Helsinki-NLP/opus-mt-fr-en",
    "es": "Helsinki-NLP/opus-mt-es-en"
}
_loaded_models = {}

def translate_to_english(text, lang):
    if lang == "en" or lang not in TRANSLATION_MODELS:
        return text

    if lang not in _loaded_models:
        tokenizer = MarianTokenizer.from_pretrained(TRANSLATION_MODELS[lang])
        model = MarianMTModel.from_pretrained(TRANSLATION_MODELS[lang])
        _loaded_models[lang] = (tokenizer, model)

    tokenizer, model = _loaded_models[lang]
    tokens = tokenizer(text, return_tensors="pt", padding=True)
    translated = model.generate(**tokens)
    return tokenizer.decode(translated[0], skip_special_tokens=True)

# -------- Main NLP Entry --------
def process_user_input(text):
    try:
        lang = detect(text)
    except:
        lang = "en"

    text_en = translate_to_english(text, lang)
    doc = nlp(text_en.lower())

    # -------- Gallery / Map --------
    match = re.search(r"\b\d{3}\b", text_en)
    if match:
        return {
            "type": "map",
            "gallery": match.group()
        }

    # -------- Exhibitions --------
    for ex in EXHIBITIONS:
        if ex["name"].lower() in text_en.lower():
            return {
                "type": "text",
                "reply": f"{ex['name']} runs from {ex['start_date']} to {ex['end_date']}. {ex['description']}"
            }

    # -------- Artworks --------
    for art in ARTWORKS:
        if art["title"].lower() in text_en.lower():
            return {
                "type": "text",
                "reply": f"'{art['title']}' by {art['artist']} ({art['date']}). Located in gallery {art['gallery']}."
            }

    # -------- Museum Info --------
    if "hours" in text_en:
        hours = MUSEUM_INFO["museum_hours"]
        reply = "Museum hours:\n"
        for day, h in hours.items():
            reply += f"{day.capitalize()}: {h}\n"
        return {"type": "text", "reply": reply}

    if "parking" in text_en:
        return {"type": "text", "reply": MUSEUM_INFO["parking"]["free"]}

    if any(word in text_en for word in ["hello", "hi", "hey"]):
        return {"type": "text", "reply": "Hello! How may I help you today?"}

    return {
        "type": "text",
        "reply": "I’m not completely sure I understood. Could you rephrase your question?"
    }
