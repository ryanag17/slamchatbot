import json
import os
from langdetect import detect
from deep_translator import GoogleTranslator
from rapidfuzz import process as rf_process, fuzz
import spacy

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

def load_json(name):
    path = os.path.join(DATA_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

MUSEUM = load_json("museum_info.json")
EXHIBITIONS = load_json("exhibitions.json")
SLAM_ART = load_json("slam_art.json")
MAP_LOCS = load_json("map_locations.json")

# spaCy
try:
    nlp = spacy.load("en_core_web_sm")
except Exception:
    nlp = spacy.blank("en")

def safe_detect_language(text: str) -> str:
    try:
        lang = detect(text)
        return lang
    except Exception:
        return "en"

def translate(text: str, source: str, target: str) -> str:
    if not text or source == target:
        return text
    try:
        return GoogleTranslator(source=source, target=target).translate(text)
    except Exception:
        return text

def normalize(text: str) -> str:
    return " ".join((text or "").lower().strip().split())

def get_python_response(user_text: str):
    # detect language
    user_lang = safe_detect_language(user_text)
    used_translation = False

    # translate to English for matching if needed
    text_en = user_text
    if user_lang != "en":
        text_en = translate(user_text, source=user_lang, target="en")
        used_translation = True

    reply_en = answer_in_english(text_en)

    # translate back if needed
    reply_out = reply_en
    if used_translation:
        reply_out = translate(reply_en, source="en", target=user_lang)

    return {
        "text": reply_out,
        "image_url": None,
        "used_translation": used_translation
    }

def answer_in_english(text: str) -> str:
    t = normalize(text)
    doc = nlp(t)

    # ---------- greetings ----------
    if t in ["hi", "hello", "hey", "yo", "hiya", "greetings"]:
        return "Hello there! How may I help you today?"

    # ---------- museum name ----------
    if "museum" in t and ("name" in t or "called" in t):
        return f"We are called the {MUSEUM.get('name','St. Louis Art Museum')}."

    # ---------- location/address ----------
    if ("where" in t and ("museum" in t or "located" in t)) or "address" in t or "location" in t:
        return f"We are located at: {MUSEUM.get('location','(location not available)')}."

    # ---------- phone ----------
    if "phone" in t or ("call" in t and "number" in t):
        return f"You can call the museum at {MUSEUM.get('phone_number','(phone not available)')}."

    # ---------- hours ----------
    if any(w in t for w in ["hours", "open", "closing", "close", "when"]):
        hours = MUSEUM.get("museum_hours", {})
        weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        for wd in weekdays:
            if wd in t:
                return f"The museum is open on {wd.capitalize()}: {hours.get(wd,'Hours not available')}."

        if "today" in t:
            import datetime
            wd = weekdays[datetime.datetime.now().weekday()]
            return f"Today ({wd.capitalize()}), the museum hours are: {hours.get(wd,'Hours not available')}."
        if "tomorrow" in t:
            import datetime
            wd = weekdays[(datetime.datetime.now().weekday()+1) % 7]
            return f"Tomorrow ({wd.capitalize()}), the museum hours will be: {hours.get(wd,'Hours not available')}."

        # weekly summary
        if hours:
            summary = "; ".join([f"{wd.capitalize()}: {hours.get(wd,'N/A')}" for wd in weekdays])
            return f"Museum hours — {summary}."
        return "Which day would you like the hours for?"

    # ---------- parking ----------
    if "parking" in t or "park" in t:
        parking = MUSEUM.get("parking", {})
        if isinstance(parking, dict):
            return parking.get("free", "Parking information is not available right now.")
        return "Parking information is not available right now."

    # ---------- exhibitions on view ----------
    if "exhibition" in t or "exhibitions" in t or "exhibit" in t:
        if "on view" in t or "current" in t:
            on_view = [e for e in EXHIBITIONS if e.get("on_view") is True]
            if not on_view:
                return "No exhibitions are currently on view."
            names = ", ".join([e.get("name","") for e in on_view])
            return f"Exhibitions currently on view: {names}"

        # by ID
        import re
        m = re.search(r"\bEXH\d{3}\b", text, flags=re.IGNORECASE)
        if m:
            exid = m.group(0).upper()
            ex = next((e for e in EXHIBITIONS if (e.get("id","").upper() == exid)), None)
            if ex:
                return f"{ex.get('name')} runs from {ex.get('start_date','N/A')} to {ex.get('end_date','N/A')}. {ex.get('description','')}"
            return "I couldn’t find that exhibition ID."

        # fuzzy by name
        names = [e.get("name","") for e in EXHIBITIONS]
        best = rf_process.extractOne(t, names, scorer=fuzz.WRatio)
        if best and best[1] >= 75:
            ex = next((e for e in EXHIBITIONS if e.get("name","") == best[0]), None)
            if ex:
                return f"{ex.get('name')}: {ex.get('description','')}"
        return "I couldn’t find that exhibition."

    # ---------- artwork search ----------
    if any(w in t for w in ["art", "artwork", "painting", "work", "artist", "title"]):
        titles = [a.get("title","") for a in SLAM_ART]
        artists = list(set([a.get("artist","") for a in SLAM_ART if a.get("artist")]))

        best_title = rf_process.extractOne(t, titles, scorer=fuzz.WRatio)
        if best_title and best_title[1] >= 78:
            art = next((a for a in SLAM_ART if a.get("title","") == best_title[0]), None)
            if art:
                return f"{art.get('title')} by {art.get('artist')} ({art.get('date','N/A')}). Located in gallery {art.get('gallery','N/A')}. {art.get('description','')}"
        best_artist = rf_process.extractOne(t, artists, scorer=fuzz.WRatio)
        if best_artist and best_artist[1] >= 80:
            artist = best_artist[0]
            pieces = [a for a in SLAM_ART if (a.get("artist","") == artist)]
            if pieces:
                return "Works by " + artist + ": " + "; ".join([f"{p.get('title')} (gallery {p.get('gallery','N/A')})" for p in pieces])

    # ---------- fallback ----------
    return "I'm not sure I understand — could you try asking in a different way?"
