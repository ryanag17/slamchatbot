# backend/nlp.py
import json
import os
import random
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from langdetect import detect
from deep_translator import GoogleTranslator
from rapidfuzz import fuzz, process

import spacy

from map_utils import get_gallery_map_image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")


def _load_json_first_existing(candidates: List[str], default):
    for p in candidates:
        try:
            if p and os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            continue
    return default


# Allow JSON files to live in multiple places WITHOUT breaking your file structure:
# - backend/data/<file>.json   (preferred)
# - backend/<file>.json
# - project root/<file>.json
def _json_candidates(filename: str) -> List[str]:
    return [
        os.path.join(DATA_DIR, filename),
        os.path.join(BASE_DIR, filename),
        os.path.join(PROJECT_ROOT, filename),
    ]


MUSEUM_INFO = _load_json_first_existing(_json_candidates("museum_info.json"), {})
EXHIBITIONS = _load_json_first_existing(_json_candidates("exhibitions.json"), [])
SLAM_ART = _load_json_first_existing(_json_candidates("slam_art.json"), [])
MAP_LOCATIONS = _load_json_first_existing(_json_candidates("map_locations.json"), [])

# spaCy model (must exist on the VM)
_NLP = spacy.load("en_core_web_sm")

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# -------------------------
# Indexes (built once)
# -------------------------
_EXH_BY_ID = {str((e.get("id") or "")).upper(): e for e in EXHIBITIONS if e.get("id")}
_EXH_NAMES = [e.get("name", "") for e in EXHIBITIONS if e.get("name")]
_EXH_NAME_TO_OBJ = {e.get("name", ""): e for e in EXHIBITIONS if e.get("name")}

_ART_TITLES = [a.get("title", "") for a in SLAM_ART if a.get("title")]
_ART_TITLE_TO_OBJ = {a.get("title", ""): a for a in SLAM_ART if a.get("title")}

_ARTISTS = sorted({(a.get("artist") or "").strip() for a in SLAM_ART if (a.get("artist") or "").strip()})

# Artist -> pieces
_ARTIST_TO_PIECES: Dict[str, List[Dict[str, Any]]] = {}
for a in SLAM_ART:
    artist = (a.get("artist") or "").strip()
    if artist:
        _ARTIST_TO_PIECES.setdefault(artist.lower(), []).append(a)

# categories from map_locations
_CATEGORY_ENTRIES = []  # (category, floor, numbers)
for floor_obj in MAP_LOCATIONS:
    floor = str(floor_obj.get("floor", "")).strip()
    for g in (floor_obj.get("galleries") or []):
        cat = (g.get("category") or "").strip()
        nums = g.get("numbers") or []
        if cat:
            _CATEGORY_ENTRIES.append((cat, floor, nums))
_CATEGORIES = [c[0] for c in _CATEGORY_ENTRIES]

# -------------------------
# Helpers
# -------------------------
def _normalize(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s\-']", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _contains_any(hay: str, needles: List[str]) -> bool:
    return any(n in hay for n in needles)


def _token_overlap_score(a: str, b: str) -> float:
    a_tokens = {t for t in re.findall(r"[a-z0-9]+", (a or "").lower()) if len(t) >= 3}
    b_tokens = {t for t in re.findall(r"[a-z0-9]+", (b or "").lower()) if len(t) >= 3}
    if not a_tokens or not b_tokens:
        return 0.0
    inter = len(a_tokens & b_tokens)
    denom = max(1, min(len(a_tokens), len(b_tokens)))
    return inter / denom


def _extract_gallery_token(text: str) -> Optional[str]:
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


# -------------------------
# Translation (robust)
# -------------------------
def _pre_detect_language(raw: str) -> Optional[str]:
    s = (raw or "").strip().lower()
    if re.match(r"^(hallo|guten tag|guten morgen|guten abend)\b", s):
        return "de"
    if "wie geht" in s or "wie gehts" in s or "wie geht's" in s:
        return "de"
    if re.match(r"^(bonjour|salut)\b", s):
        return "fr"
    if re.match(r"^(hola|buenas)\b", s):
        return "es"
    if re.match(r"^(ciao|buongiorno|buonasera)\b", s):
        return "it"
    return None


def _should_skip_langdetect(raw: str) -> bool:
    s = (raw or "").strip()
    if not s:
        return True
    if _pre_detect_language(s):
        return False
    if re.match(r"^(hi|hello|hey|yo|hiya|greetings|thanks|thank you)\b", s.lower()):
        return True
    if s.isascii() and re.search(r"\b(the|and|is|are|you|i|we|to|of|in|on|for|help|where|what|when|how)\b", s.lower()):
        return True
    return False


def _translate_in(text: str) -> Tuple[str, Optional[str]]:
    raw = (text or "").strip()
    if not raw:
        return raw, None

    forced = _pre_detect_language(raw)
    if forced and forced != "en":
        try:
            en = GoogleTranslator(source=forced, target="en").translate(raw)
            return en, forced
        except Exception:
            return raw, forced

    if _should_skip_langdetect(raw):
        return raw, None

    try:
        lang = detect(raw)
    except Exception:
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
# Core answers
# -------------------------
def _greeting_answer(norm: str) -> Optional[str]:
    if re.match(r"^(hi|hello|hey|yo|hiya|greetings)\b", norm):
        if len(norm.split()) <= 6:
            return "Hello there! How may I help you today?"
    if any(k in norm for k in ["how are you", "how's it going", "how are u", "how r u", "how is it going"]):
        return "I'm doing well! How can I help you with the museum?"
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


def _hours_for_day(day: str) -> Optional[str]:
    hours = (MUSEUM_INFO.get("museum_hours") or {})
    return hours.get(day)


def _hours_answer(norm: str) -> Optional[str]:
    wd = _extract_weekday(norm)
    if wd:
        h = _hours_for_day(wd)
        if h:
            return f"Hours on {wd.title()}: {h}."
        return None

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
    if any(k in norm for k in ["where is the museum", "museum located", "museum location", "where are you located", "museum address", "address"]):
        loc = MUSEUM_INFO.get("location")
        if loc:
            return f"We are located at {loc}."
        return "I don’t have the museum address available right now."

    if any(k in norm for k in ["phone", "telephone", "tel", "phone number", "call the museum", "contact number"]):
        phone = MUSEUM_INFO.get("phone_number")
        if phone:
            return f"You can call the museum at {phone}."
        return "I don’t have the phone number available right now."

    h = _hours_answer(norm)
    if h:
        return h

    if any(k in norm for k in ["parking", "park", "parking garage", "where do i park"]):
        parking = (MUSEUM_INFO.get("parking") or {}).get("free")
        if parking:
            return parking
        return "Parking information is not available right now."

    if any(k in norm for k in ["what is slam", "about slam", "tell me about the museum", "about the museum", "museum info", "museum description"]):
        desc = MUSEUM_INFO.get("description") or MUSEUM_INFO.get("location_description")
        if desc:
            return desc
        return "I don’t have a description for the museum right now."

    return None


def _format_exhibition(ex: Dict[str, Any]) -> str:
    name = ex.get("name", "Exhibition")
    start = ex.get("start_date", "N/A")
    end = ex.get("end_date", "N/A")
    desc = (ex.get("description") or "").strip()
    curated = (ex.get("curated_by") or "").strip()
    galleries = ex.get("gallery_numbers")

    parts = [f"{name} runs from {start} to {end}."]
    if galleries:
        parts.append(f"Gallery location: {galleries}.")
    if desc:
        parts.append(desc)
    if curated:
        parts.append(curated)
    return " ".join(p for p in parts if p).strip()


def _exhibitions_answer(norm: str) -> Optional[str]:
    # "currently on display" / "on view" etc
    if any(p in norm for p in [
        "on view", "currently on view", "current exhibitions",
        "what exhibitions are on view", "what's on view", "whats on view", "what is on view",
        "currently on display", "on display", "what exhibitions are currently on display"
    ]):
        on_view = [e for e in EXHIBITIONS if e.get("on_view") is True]
        if not on_view:
            return "No exhibitions are currently on view."
        names = ", ".join([e.get("name", "Untitled") for e in on_view])
        return f"Exhibitions currently on view: {names}."

    # By EXH tag
    m = re.search(r"\bEXH\d{3}\b", norm.upper())
    if m:
        ex_id = m.group(0).upper()
        ex = _EXH_BY_ID.get(ex_id)
        if ex:
            return _format_exhibition(ex)

    intent = any(k in norm for k in [
        "exhibition", "exhibit", "show", "on view", "on display",
        "tell me about", "tell me more", "details", "info on", "information on",
        "when does", "when is", "run", "runs", "dates", "until", "end date", "start date"
    ])

    if _EXH_NAMES:
        best = process.extractOne(norm, _EXH_NAMES, scorer=fuzz.WRatio)
        if best:
            name, score = best[0], best[1]
            overlap = _token_overlap_score(norm, name)

            if (intent and score >= 72 and overlap >= 0.30) or (score >= 86 and overlap >= 0.40):
                ex = _EXH_NAME_TO_OBJ.get(name)
                if ex:
                    return _format_exhibition(ex)

    return None


def _format_artwork(a: Dict[str, Any]) -> str:
    title = a.get("title", "Untitled")
    artist = a.get("artist") or "Unknown"
    date = a.get("date") or "N/A"
    gallery = a.get("gallery") or "N/A"
    desc = (a.get("description") or "").strip() or "No description."
    medium = a.get("medium")
    made_in = a.get("made_in")
    bits = [f"{title} by {artist} ({date}).", f"It’s located in gallery {gallery}."]
    if medium:
        bits.append(f"Medium: {medium}.")
    if made_in:
        bits.append(f"Made in: {made_in}.")
    bits.append(desc)
    return " ".join(bits)


def _artist_summary(artist: str) -> Optional[str]:
    pieces = _ARTIST_TO_PIECES.get(artist.lower())
    if not pieces:
        return None
    # show up to 6 works
    items = []
    for p in pieces[:6]:
        items.append(f"{p.get('title','Untitled')} (gallery {p.get('gallery','N/A')})")
    more = "" if len(pieces) <= 6 else f" (and {len(pieces)-6} more)"
    return f"Works by {artist}: " + "; ".join(items) + more + "."


def _art_answer(norm: str) -> Optional[str]:
    # Explicit "works by <artist>"
    if any(k in norm for k in ["works by", "show me works by", "pieces by", "paintings by", "art by"]):
        if not _ARTISTS:
            return None
        best = process.extractOne(norm, _ARTISTS, scorer=fuzz.WRatio)
        if not best or best[1] < 78:
            return None
        artist = best[0]
        return _artist_summary(artist)

    # Artist-only questions (common in demos)
    if any(k in norm for k in ["tell me about", "who is", "about"]) and _ARTISTS:
        best_artist = process.extractOne(norm, _ARTISTS, scorer=fuzz.WRatio)
        if best_artist and best_artist[1] >= 88:
            artist = best_artist[0]
            # avoid hijacking if the user obviously asked about an artwork title
            best_title = process.extractOne(norm, _ART_TITLES, scorer=fuzz.WRatio) if _ART_TITLES else None
            if not best_title or best_title[1] < best_artist[1]:
                summary = _artist_summary(artist)
                if summary:
                    return summary

    # Artwork title matching
    art_intent = any(k in norm for k in ["tell me about", "about", "where is", "where's", "located", "location of", "who made", "who painted", "artist of"])
    if not _ART_TITLES:
        return None

    best = process.extractOne(norm, _ART_TITLES, scorer=fuzz.WRatio)
    if not best:
        return None

    title, score = best[0], best[1]
    overlap = _token_overlap_score(norm, title)

    if art_intent:
        if score < 84 or overlap < 0.40:
            return None
    else:
        if score < 92 or overlap < 0.55:
            return None

    art = _ART_TITLE_TO_OBJ.get(title)
    if not art:
        return None

    return _format_artwork(art)


def _category_location_answer(norm: str) -> Optional[str]:
    if not any(k in norm for k in ["where is", "where are", "located", "find", "location"]):
        return None
    if not _CATEGORIES:
        return None

    best = process.extractOne(norm, _CATEGORIES, scorer=fuzz.WRatio)
    if not best:
        return None

    cat, score = best[0], best[1]
    overlap = _token_overlap_score(norm, cat)

    if score < 80 and overlap < 0.45:
        return None

    hits = [(c, f, nums) for (c, f, nums) in _CATEGORY_ENTRIES if c == cat]
    if not hits:
        return None

    floor_map: Dict[str, List[str]] = {}
    for _, floor, nums in hits:
        floor_map.setdefault(floor, [])
        for n in nums:
            floor_map[floor].append(str(n))

    parts = []
    for floor in sorted(floor_map.keys(), key=lambda x: int(re.sub(r"\D", "", x) or "0")):
        unique_nums = []
        seen = set()
        for n in floor_map[floor]:
            if n not in seen:
                seen.add(n)
                unique_nums.append(n)
        parts.append(f"floor {floor} (galleries {', '.join(unique_nums)})")

    return f"{cat} is located on " + " and ".join(parts) + "."


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

    cat_text = _category_location_answer(norm)
    if cat_text:
        best = process.extractOne(norm, _CATEGORIES, scorer=fuzz.WRatio)
        cat = best[0] if best else None
        floors = [f for (c, f, _) in _CATEGORY_ENTRIES if c == cat] if cat else []
        floor = floors[0] if floors else None
        image_url = f"/backend/static/floor{floor}.png" if floor else None
        return {"text": cat_text, "image_url": image_url}

    return None


# -------------------------
# Suggestions
# -------------------------
_SUGGESTION_TEMPLATES = [
    "What exhibitions are currently on view?",
    "What exhibitions are currently on display?",
    "What are the museum hours today?",
    "Where is gallery 216?",
    "Where is {category}?",
    "Tell me about {art_title}.",
    "Show me works by {artist}.",
    "Where is the museum located?",
    "What time do you close on Friday?",
]


def _make_suggestions(orig_lang: Optional[str]) -> List[str]:
    categories = list({c for (c, _, _) in _CATEGORY_ENTRIES})[:50]
    art_titles = _ART_TITLES[:200]
    artists = _ARTISTS[:200]

    cat_pick = random.choice(categories) if categories else "European Art"
    art_pick = random.choice(art_titles) if art_titles else "A Street in Saint Louis"
    artist_pick = random.choice(artists) if artists else "Henry Lewis"

    candidates = [t.format(category=cat_pick, art_title=art_pick, artist=artist_pick) for t in _SUGGESTION_TEMPLATES]
    random.shuffle(candidates)

    picks = []
    for s in candidates:
        if s not in picks:
            picks.append(s)
        if len(picks) == 3:
            break

    return [_translate_out(s, orig_lang) for s in picks]


# -------------------------
# Main router (order matters)
# -------------------------
def generate_response(user_text: str) -> Dict[str, Any]:
    en_text, orig_lang = _translate_in(user_text)
    norm = _normalize(en_text)

    greeting = _greeting_answer(norm)
    if greeting:
        out_text = _translate_out(greeting, orig_lang)
        return {"text": out_text, "image_url": None, "suggestions": _make_suggestions(orig_lang)}

    map_payload = _map_answer(norm)
    if map_payload:
        out_text = _translate_out(map_payload["text"], orig_lang)
        return {"text": out_text, "image_url": map_payload.get("image_url"), "suggestions": _make_suggestions(orig_lang)}

    ex = _exhibitions_answer(norm)
    if ex:
        out_text = _translate_out(ex, orig_lang)
        return {"text": out_text, "image_url": None, "suggestions": _make_suggestions(orig_lang)}

    art = _art_answer(norm)
    if art:
        out_text = _translate_out(art, orig_lang)
        return {"text": out_text, "image_url": None, "suggestions": _make_suggestions(orig_lang)}

    cat_loc = _category_location_answer(norm)
    if cat_loc:
        out_text = _translate_out(cat_loc, orig_lang)
        return {"text": out_text, "image_url": None, "suggestions": _make_suggestions(orig_lang)}

    mus = _museum_info_answer(norm)
    if mus:
        out_text = _translate_out(mus, orig_lang)
        return {"text": out_text, "image_url": None, "suggestions": _make_suggestions(orig_lang)}

    fallback = "I'm not sure I understand — could you try asking in a different way?"
    out_text = _translate_out(fallback, orig_lang)
    return {"text": out_text, "image_url": None, "suggestions": _make_suggestions(orig_lang)}


def respond(text: str) -> Dict[str, Any]:
    return generate_response(text)
