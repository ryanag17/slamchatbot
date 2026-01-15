import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from langdetect import detect
from deep_translator import GoogleTranslator
from rapidfuzz import fuzz, process

import spacy

from map_utils import get_gallery_map_image


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


MUSEUM_INFO = _load_json(os.path.join(DATA_DIR, "museum_info.json"), {})
EXHIBITIONS = _load_json(os.path.join(DATA_DIR, "exhibitions.json"), [])
SLAM_ART = _load_json(os.path.join(DATA_DIR, "slam_art.json"), [])
MAP_LOCATIONS = _load_json(os.path.join(DATA_DIR, "map_locations.json"), [])

# spaCy model (must exist on the VM)
_NLP = spacy.load("en_core_web_sm")

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# -------------------------
# Normalization + utilities
# -------------------------

def _normalize(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s\-']", " ", s)  # keep letters/numbers/_ hyphen apostrophe
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _contains_any(s: str, words: List[str]) -> bool:
    return any(w in s for w in words)


def _extract_gallery_token(text: str) -> Optional[str]:
    """
    Match gallery numbers like:
    - 219
    - 236E
    - 212S
    Also catches "gallery 219" or "room 219"
    """
    t = (text or "").upper()

    m = re.search(r"\bGALLERY\s+([0-9]{2,3}[A-Z]?)\b", t)
    if m:
        return m.group(1)

    m = re.search(r"\b(ROOM|RM)\s+([0-9]{2,3}[A-Z]?)\b", t)
    if m:
        return m.group(2)

    m = re.search(r"\b([0-9]{2,3}[A-Z]?)\b", t)
    if m:
        return m.group(1)

    return None


def _resolve_relative_day(norm: str) -> Optional[str]:
    if "today" in norm:
        return datetime.now().strftime("%A").lower()
    if "tomorrow" in norm:
        return (datetime.now() + timedelta(days=1)).strftime("%A").lower()
    return None


def _extract_weekday(norm: str) -> Optional[str]:
    for wd in WEEKDAYS:
        if wd in norm:
            return wd
    rel = _resolve_relative_day(norm)
    if rel:
        return rel
    return None


# -------------------------
# Museum info + Hours
# -------------------------

def _hours_for_day(day: str) -> Optional[str]:
    hours = (MUSEUM_INFO.get("museum_hours") or {})
    return hours.get(day)


def _format_hours_answer(norm: str) -> Optional[str]:
    wd = _extract_weekday(norm)
    if wd:
        h = _hours_for_day(wd)
        if h:
            return f"Hours on {wd.title()}: {h}."

    # general hours request
    if _contains_any(norm, ["hours", "open", "close", "opening", "closing"]):
        hours = (MUSEUM_INFO.get("museum_hours") or {})
        if hours:
            lines = []
            for d in WEEKDAYS:
                if d in hours:
                    lines.append(f"{d.title()}: {hours[d]}")
            if lines:
                return "Museum hours:\n" + "\n".join(lines)

    return None


def _museum_info_answer(norm: str) -> Optional[str]:
    """
    IMPORTANT: This must be strong + prioritized so it doesn't get hijacked by art fuzzy matching.
    """
    # Address / location
    if _contains_any(norm, ["where is the museum", "museum located", "museum location", "where are you located", "address", "museum address"]):
        loc = MUSEUM_INFO.get("location")
        if loc:
            return f"We are located at {loc}."
        return "I don’t have the museum address available right now."

    # Phone
    if _contains_any(norm, ["phone", "telephone", "tel", "phone number"]):
        phone = MUSEUM_INFO.get("phone_number")
        if phone:
            return f"You can call the museum at {phone}."
        return "I don’t have the phone number available right now."

    # Hours (handles Monday/Friday questions too)
    hours_ans = _format_hours_answer(norm)
    if hours_ans:
        return hours_ans

    # Parking
    if "parking" in norm or "park" in norm:
        parking = (MUSEUM_INFO.get("parking") or {}).get("free")
        if parking:
            return parking
        return "Parking information is not available right now."

    # Museum description / SLAM
    if _contains_any(norm, ["what is slam", "about slam", "tell me about slam", "about the museum", "museum info", "what is the museum", "tell me about the museum"]):
        desc = MUSEUM_INFO.get("description") or MUSEUM_INFO.get("location_description")
        if desc:
            return desc
        return "I don’t have a description for the museum right now."

    return None


# -------------------------
# Exhibitions
# -------------------------

def _exhibitions_answer(norm: str) -> Optional[str]:
    # list on view
    if any(p in norm for p in [
        "on view", "currently on view", "current exhibitions",
        "what exhibitions are on view", "what's on view", "whats on view", "what is on view"
    ]):
        on_view = [e for e in EXHIBITIONS if e.get("on_view") is True]
        if not on_view:
            return "No exhibitions are currently on view."
        names = ", ".join([e.get("name", "Untitled") for e in on_view])
        return f"Exhibitions currently on view: {names}."

    # explicit EXH###
    m = re.search(r"\bEXH\d{3}\b", norm.upper())
    if m:
        ex_id = m.group(0)
        ex = next((e for e in EXHIBITIONS if (e.get("id") or "").upper() == ex_id), None)
        if ex:
            return f"{ex.get('name','Exhibition')} runs from {ex.get('start_date','N/A')} to {ex.get('end_date','N/A')}. {ex.get('description','')}".strip()

    # “When does <name> run?” / “Tell me about <name>”
    intent_run = any(k in norm for k in ["when does", "when is", "run", "runs from", "dates", "until", "end date", "start date"])
    intent_about = any(k in norm for k in ["tell me about", "about", "details", "info on", "information on", "what is"])
    mentions_exhibition = any(k in norm for k in ["exhibition", "exhibit", "show"])

    # Only try fuzzy exhibition match if user intent suggests exhibitions OR the string is long enough
    if (intent_run or mentions_exhibition or intent_about) and len(norm) >= 8:
        names = [e.get("name", "") for e in EXHIBITIONS if e.get("name")]
        if names:
            best = process.extractOne(norm, names, scorer=fuzz.WRatio)
            # Lower threshold than before, but only when intent is strong
            if best and best[1] >= 70:
                ex = next(e for e in EXHIBITIONS if e.get("name") == best[0])
                return f"{ex.get('name','Exhibition')} runs from {ex.get('start_date','N/A')} to {ex.get('end_date','N/A')}. {ex.get('description','')}".strip()

    return None


# -------------------------
# Art (heavily constrained)
# -------------------------

def _art_answer(norm: str) -> Optional[str]:
    """
    IMPORTANT: This used to hijack everything.
    Now it only triggers when:
      - The user clearly asks about an artwork/artist, OR
      - The title match is extremely high
    """
    # Never treat these intents as art:
    if _contains_any(norm, ["hours", "open", "close", "address", "where is the museum", "museum located", "museum location"]):
        return None
    if _contains_any(norm, ["exhibition", "exhibit", "on view", "runs from", "when does", "current exhibitions"]):
        return None

    # Strong art intent keywords
    art_intent = any(k in norm for k in [
        "artwork", "painting", "sculpture", "piece", "work of art",
        "who made", "who painted", "artist", "tell me about", "describe",
        "where is", "located", "what is"
    ])

    titles = [a.get("title", "") for a in SLAM_ART if a.get("title")]
    if not titles:
        return None

    best = process.extractOne(norm, titles, scorer=fuzz.WRatio)
    if not best:
        return None

    title, score = best[0], best[1]

    # If user didn't show art intent, require a very high match to prevent random hits
    if not art_intent and score < 95:
        return None

    # If user did show art intent, still require a decent match
    if art_intent and score < 85:
        return None

    art = next((a for a in SLAM_ART if a.get("title") == title), None)
    if not art:
        return None

    return f"{art.get('title')} by {art.get('artist','Unknown')} ({art.get('date','N/A')}). It’s located in gallery {art.get('gallery','N/A')}. {art.get('description','')}".strip()


# -------------------------
# Map
# -------------------------

def _map_answer(norm: str) -> Optional[Dict[str, Any]]:
    token = _extract_gallery_token(norm)

    if token and any(k in norm for k in ["where", "located", "find", "how do i get", "map", "gallery", "room", "rm"]):
        img_payload = get_gallery_map_image(token, MAP_LOCATIONS)
        if img_payload and img_payload.get("image_url"):
            return {
                "text": f"Here is where gallery {token} is located:",
                "image_url": img_payload["image_url"]
            }
        return {
            "text": f"I couldn’t generate the map image for gallery {token}, but it should be on the correct floor map.",
            "image_url": None
        }

    # Category query like "Where is European Art?"
    if any(k in norm for k in ["where is", "where", "located", "find"]) and len(norm) > 6:
        cats = []
        for floor_obj in MAP_LOCATIONS:
            floor = str(floor_obj.get("floor", "")).strip()
            for g in (floor_obj.get("galleries") or []):
                cat = (g.get("category") or "").strip()
                if cat:
                    cats.append((cat, floor, g.get("numbers") or [], os.path.basename(g.get("map_image", ""))))

        if cats:
            cat_names = [c[0] for c in cats]
            best = process.extractOne(norm, cat_names, scorer=fuzz.WRatio)
            if best and best[1] >= 80:
                cat, floor, nums, img = next(c for c in cats if c[0] == best[0])

                img_url = f"/backend/static/{img}" if img else f"/backend/static/floor{floor}.png"

                return {
                    "text": f"{cat} is on floor {floor} in galleries {', '.join([str(n) for n in nums])}.",
                    "image_url": img_url
                }

    return None


# -------------------------
# Greetings
# -------------------------

def _greeting_answer(norm: str) -> Optional[str]:
    if re.match(r"^(hi|hello|hey|yo|hiya|greetings)\b", norm):
        if len(norm.split()) <= 6:
            return "Hello there! How may I help you today?"
    if any(k in norm for k in ["how are you", "how's it going", "how are u", "how r u"]):
        return "I'm doing well! How can I help you with the museum?"
    return None


# -------------------------
# Translation (FIXED)
# -------------------------

def _pre_detect_greeting_language(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Fixes your German examples even when langdetect is flaky:
      - "Hallo!" should behave like "Hello!" and respond in German
      - "Hallo, wie gehts" should behave like "How are you" and respond in German
    Returns (english_text_override, lang_code_override)
    """
    s = (raw or "").strip().lower()

    # German greetings
    if re.match(r"^(hallo|hi|hey)\b", s) and ("wie" in s and ("geht" in s or "gehts" in s)):
        return "how are you", "de"

    if re.match(r"^(hallo|guten tag|guten morgen|guten abend)\b", s):
        return "hello", "de"

    # Add more languages here if you want later
    return None, None


def _should_skip_langdetect(raw: str) -> bool:
    """
    We only skip langdetect when we are confident it's English.
    For non-English short phrases (like "Hallo!"), we MUST allow detection
    unless our explicit pre-detect already handled it.
    """
    s = (raw or "").strip()
    if not s:
        return True

    # If it's clearly an English greeting, skip to avoid "it" false positives
    if re.match(r"^(hi|hello|hey|yo|hiya|greetings|thanks|thank you)\b", s.lower()):
        return True

    # If it's mostly ASCII and contains common English function words, skip
    if s.isascii() and re.search(r"\b(the|and|is|are|you|i|we|to|of|in|on|for|help|where|what|when|how)\b", s.lower()):
        return True

    # Otherwise, do NOT skip; we want translation to work
    return False


def _translate_in(text: str) -> Tuple[str, Optional[str]]:
    """
    Detect language. If not English, translate to English for processing.
    Returns (english_text, original_lang_or_none)
    """
    raw = (text or "").strip()
    if not raw:
        return raw, None

    # Hard-coded fix for your exact German greeting cases
    override_en, override_lang = _pre_detect_greeting_language(raw)
    if override_en and override_lang:
        return override_en, override_lang

    if _should_skip_langdetect(raw):
        return raw, None

    try:
        lang = detect(raw)
    except Exception:
        # If detect fails, assume English
        return raw, None

    if lang == "en":
        return raw, None

    try:
        en = GoogleTranslator(source="auto", target="en").translate(raw)
        return en, lang
    except Exception:
        return raw, lang


def _translate_out(text: str, target_lang: Optional[str]) -> str:
    if not target_lang or target_lang == "en":
        return text
    try:
        return GoogleTranslator(source="auto", target=target_lang).translate(text)
    except Exception:
        return text


# -------------------------
# Main router (ORDER MATTERS)
# -------------------------

def generate_response(user_text: str) -> Dict[str, Any]:
    en_text, orig_lang = _translate_in(user_text)
    norm = _normalize(en_text)

    # 1) Greetings first
    greeting = _greeting_answer(norm)
    if greeting:
        out_text = _translate_out(greeting, orig_lang)
        return {"text": out_text, "image_url": None, "detected_lang": orig_lang or "en", "translated": bool(orig_lang)}

    # 2) Map next (only triggers when gallery/category intent is present)
    map_payload = _map_answer(norm)
    if map_payload:
        out_text = _translate_out(map_payload["text"], orig_lang)
        return {
            "text": out_text,
            "image_url": map_payload.get("image_url"),
            "detected_lang": orig_lang or "en",
            "translated": bool(orig_lang)
        }

    # 3) Museum info + hours BEFORE art/exhibitions hijack
    mus = _museum_info_answer(norm)
    if mus:
        out_text = _translate_out(mus, orig_lang)
        return {"text": out_text, "image_url": None, "detected_lang": orig_lang or "en", "translated": bool(orig_lang)}

    # 4) Exhibitions
    ex = _exhibitions_answer(norm)
    if ex:
        out_text = _translate_out(ex, orig_lang)
        return {"text": out_text, "image_url": None, "detected_lang": orig_lang or "en", "translated": bool(orig_lang)}

    # 5) Art (constrained)
    art = _art_answer(norm)
    if art:
        out_text = _translate_out(art, orig_lang)
        return {"text": out_text, "image_url": None, "detected_lang": orig_lang or "en", "translated": bool(orig_lang)}

    fallback = "I'm not sure I understand — could you try asking in a different way?"
    out_text = _translate_out(fallback, orig_lang)
    return {"text": out_text, "image_url": None, "detected_lang": orig_lang or "en", "translated": bool(orig_lang)}


def respond(text: str) -> Dict[str, Any]:
    return generate_response(text)
