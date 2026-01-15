import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from langdetect import detect
from deep_translator import GoogleTranslator
from rapidfuzz import fuzz, process

import spacy


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

# spaCy model
# You must install: python -m spacy download en_core_web_sm
_NLP = spacy.load("en_core_web_sm")


WEEKDAYS = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]


def _normalize(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s\-]", " ", s)  # keep letters/numbers/_ and hyphen
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_gallery_token(text: str) -> Optional[str]:
    """
    Match gallery numbers like:
    - 219
    - 236E
    - 212S
    Also catches "gallery 219" or "room 219"
    """
    t = (text or "").upper()

    # Prefer explicit "gallery xxx"
    m = re.search(r"\bGALLERY\s+([0-9]{3}[A-Z]?)\b", t)
    if m:
        return m.group(1)

    # Otherwise any standalone 3-digit(+optional letter)
    m = re.search(r"\b([0-9]{3}[A-Z]?)\b", t)
    if m:
        return m.group(1)

    return None


def _resolve_relative_day(norm: str) -> Optional[str]:
    # today/tomorrow
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
    hours = (MUSEUM_INFO.get("museum_hours") or {}).get(day)
    return hours


def _format_hours_answer(norm: str) -> Optional[str]:
    wd = _extract_weekday(norm)
    if wd:
        hours = _hours_for_day(wd)
        if hours:
            return f"On {wd.title()}, the museum hours are: {hours}."
        return f"I don’t have hours listed for {wd.title()}."

    # If they ask "when do you close on Friday?"
    m = re.search(r"\b(close|closing)\b", norm)
    if m:
        wd2 = _extract_weekday(norm)
        if wd2:
            hours = _hours_for_day(wd2)
            if hours:
                return f"On {wd2.title()}, the museum hours are: {hours}."
            return f"I don’t have closing hours listed for {wd2.title()}."

    # General hours summary ONLY if they ask general “hours”
    if any(k in norm for k in ["hours", "opening hours", "open hours", "when are you open"]):
        mh = MUSEUM_INFO.get("museum_hours") or {}
        parts = []
        for wd in WEEKDAYS:
            if wd in mh:
                parts.append(f"{wd.title()}: {mh[wd]}")
        if parts:
            return "Museum hours — " + "; ".join(parts) + "."
    return None


def _museum_info_answer(norm: str) -> Optional[str]:
    # IMPORTANT: do NOT let "where" auto-trigger address if the user is asking "where is gallery 219"
    # That’s handled earlier in routing.

    if any(k in norm for k in ["address", "located", "location", "where is the museum", "where are you located"]):
        loc = MUSEUM_INFO.get("location")
        if loc:
            return f"We are located at {loc}."
        return "I don’t have the museum address available right now."

    if any(k in norm for k in ["phone", "call", "telephone", "tel", "number"]):
        phone = MUSEUM_INFO.get("phone_number")
        if phone:
            return f"You can call the museum at {phone}."
        return "I don’t have the phone number available right now."

    hours_ans = _format_hours_answer(norm)
    if hours_ans:
        return hours_ans

    if "parking" in norm or "park" in norm:
        parking = (MUSEUM_INFO.get("parking") or {}).get("free")
        if parking:
            return parking
        return "Parking information is not available right now."

    return None


def _exhibitions_answer(norm: str) -> Optional[str]:
    # On view
    if any(p in norm for p in ["on view", "currently on view", "current exhibitions", "what exhibitions are on view", "what's on view", "whats on view"]):
        on_view = [e for e in EXHIBITIONS if e.get("on_view") is True]
        if not on_view:
            return "No exhibitions are currently on view."
        names = ", ".join([e.get("name", "Untitled") for e in on_view])
        return f"Exhibitions currently on view: {names}."

    # By ID EXH###
    m = re.search(r"\bEXH\d{3}\b", norm.upper())
    if m:
        ex_id = m.group(0)
        ex = next((e for e in EXHIBITIONS if (e.get("id") or "").upper() == ex_id), None)
        if ex:
            return f"{ex.get('name','Exhibition')} runs from {ex.get('start_date','N/A')} to {ex.get('end_date','N/A')}. {ex.get('description','')}".strip()

    # Fuzzy name match if they mention exhibition/exhibit
    if "exhibition" in norm or "exhibit" in norm:
        choices = [(e.get("name",""), e) for e in EXHIBITIONS]
        names = [c[0] for c in choices if c[0]]
        if names:
            best = process.extractOne(norm, names, scorer=fuzz.WRatio)
            if best and best[1] >= 75:
                ex = next(e for e in EXHIBITIONS if e.get("name") == best[0])
                return f"{ex.get('name','Exhibition')} runs from {ex.get('start_date','N/A')} to {ex.get('end_date','N/A')}. {ex.get('description','')}".strip()

    return None


def _art_answer(norm: str) -> Optional[str]:
    # Title fuzzy
    titles = [a.get("title","") for a in SLAM_ART if a.get("title")]
    if titles:
        best = process.extractOne(norm, titles, scorer=fuzz.WRatio)
        if best and best[1] >= 80:
            art = next(a for a in SLAM_ART if a.get("title") == best[0])
            return f"{art.get('title')} by {art.get('artist','Unknown')} ({art.get('date','N/A')}). It’s located in gallery {art.get('gallery','N/A')}. {art.get('description','')}".strip()

    # Artist query patterns
    if any(k in norm for k in ["works by", "pieces by", "paintings by", "artist", "show me works by"]):
        artists = list({(a.get("artist") or "") for a in SLAM_ART if a.get("artist")})
        if artists:
            best = process.extractOne(norm, artists, scorer=fuzz.WRatio)
            if best and best[1] >= 80:
                artist_name = best[0]
                pieces = [a for a in SLAM_ART if (a.get("artist") or "").lower() == artist_name.lower()]
                if pieces:
                    short = "; ".join([f"{p.get('title','Untitled')} (gallery {p.get('gallery','N/A')})" for p in pieces[:8]])
                    more = "" if len(pieces) <= 8 else f" (and {len(pieces)-8} more)"
                    return f"Works by {artist_name}: {short}{more}."

    return None


def _find_floor_for_gallery(gallery_token: str) -> Optional[Tuple[str, str]]:
    """
    Returns (floor, map_image_basename) if gallery appears on that floor.
    Also checks stairs/elevators/coat_checks/restrooms locations (like "219").
    """
    gt = str(gallery_token).upper()

    for floor_obj in MAP_LOCATIONS:
        floor = str(floor_obj.get("floor", "")).strip()

        # galleries numbers
        for g in (floor_obj.get("galleries") or []):
            nums = [str(x).upper() for x in (g.get("numbers") or [])]
            if gt in nums:
                img = g.get("map_image", "")
                return (floor, os.path.basename(img) if img else f"floor{floor}.png")

        # stairs/elevators/coat_checks lists can contain "219"
        for key in ["stairs", "elevators", "coat_checks"]:
            vals = [str(x).upper() for x in (floor_obj.get(key) or [])]
            if gt in vals:
                # use floor image
                return (floor, f"floor{floor}.png")

        # restrooms objects {location: "227", type:"female"}
        for r in (floor_obj.get("restrooms") or []):
            loc = str(r.get("location","")).upper()
            if loc == gt:
                return (floor, f"floor{floor}.png")

    return None


def _map_answer(norm: str) -> Optional[Dict[str, Any]]:
    """
    If user asks for where a gallery/room/hall is, return a dict with:
      { "text": "...", "map": { "image": "/floor2.png", "target": "219" } }
    """
    # We treat anything with "gallery" OR explicit 3-digit token as location query.
    token = _extract_gallery_token(norm)
    if token and (("gallery" in norm) or ("where" in norm) or ("find" in norm) or ("located" in norm) or True):
        found = _find_floor_for_gallery(token)
        if found:
            floor, img = found
            # Your images are in the project root: /floor2.png etc.
            # If JSON says floor2.png but you have floor2.png at root -> good.
            # If JSON says maps/floor2.png -> basename -> floor2.png
            return {
                "text": f"Here is where gallery {token} is located (floor {floor}):",
                "map": {"image": f"/{img}", "target": token}
            }
        return {"text": f"I couldn’t find gallery {token} in the map data.", "map": None}

    # Category query like "Where is European Art?"
    if any(k in norm for k in ["where is", "where", "located", "find"]) and len(norm) > 6:
        # Build category list from map_locations
        cats = []
        for floor_obj in MAP_LOCATIONS:
            floor = str(floor_obj.get("floor","")).strip()
            for g in (floor_obj.get("galleries") or []):
                cat = (g.get("category") or "").strip()
                if cat:
                    cats.append((cat, floor, g.get("numbers") or [], os.path.basename(g.get("map_image",""))))

        if cats:
            cat_names = [c[0] for c in cats]
            best = process.extractOne(norm, cat_names, scorer=fuzz.WRatio)
            if best and best[1] >= 80:
                cat, floor, nums, img = next(c for c in cats if c[0] == best[0])
                return {
                    "text": f"{cat} is on floor {floor} in galleries {', '.join([str(n) for n in nums])}.",
                    "map": {"image": f"/{img or f'floor{floor}.png'}", "target": None}
                }

    return None


def _greeting_answer(norm: str) -> Optional[str]:
    if re.match(r"^(hi|hello|hey|yo|hiya|greetings)\b", norm):
        # If it's JUST a greeting-ish message
        if len(norm.split()) <= 3:
            return "Hello there! How may I help you today?"
    if "how are you" in norm or "how's it going" in norm or "how are u" in norm:
        return "I'm doing well! How can I help you with the museum?"
    return None


def _translate_in(text: str) -> Tuple[str, Optional[str]]:
    """
    Detect language. If not English, translate to English for processing.
    Returns (english_text, original_lang_or_none)
    """
    raw = (text or "").strip()
    if not raw:
        return raw, None

    try:
        lang = detect(raw)
    except Exception:
        return raw, None

    # if lang is English, do nothing
    if lang == "en":
        return raw, None

    # translate to English
    try:
        en = GoogleTranslator(source="auto", target="en").translate(raw)
        return en, lang
    except Exception:
        # If translation fails, fall back to raw
        return raw, lang


def _translate_out(text: str, target_lang: Optional[str]) -> str:
    if not target_lang or target_lang == "en":
        return text
    try:
        return GoogleTranslator(source="auto", target=target_lang).translate(text)
    except Exception:
        return text


def generate_response(user_text: str) -> Dict[str, Any]:
    """
    Main entry point used by Flask.
    Returns:
      { "text": "...", "map": {"image": "/floor2.png", "target": "219"} | None, "detected_lang": "...", "translated": true/false }
    """
    en_text, orig_lang = _translate_in(user_text)
    norm = _normalize(en_text)

    # ROUTING ORDER MATTERS:
    # 1) greeting
    # 2) map location (so "where is gallery 219" does NOT become museum address)
    # 3) exhibitions
    # 4) art
    # 5) museum info
    # 6) fallback

    greeting = _greeting_answer(norm)
    if greeting:
        out_text = _translate_out(greeting, orig_lang)
        return {"text": out_text, "map": None, "detected_lang": orig_lang or "en", "translated": bool(orig_lang)}

    map_payload = _map_answer(norm)
    if map_payload:
        out_text = _translate_out(map_payload["text"], orig_lang)
        out_map = map_payload.get("map")
        return {"text": out_text, "map": out_map, "detected_lang": orig_lang or "en", "translated": bool(orig_lang)}

    ex = _exhibitions_answer(norm)
    if ex:
        out_text = _translate_out(ex, orig_lang)
        return {"text": out_text, "map": None, "detected_lang": orig_lang or "en", "translated": bool(orig_lang)}

    art = _art_answer(norm)
    if art:
        out_text = _translate_out(art, orig_lang)
        return {"text": out_text, "map": None, "detected_lang": orig_lang or "en", "translated": bool(orig_lang)}

    mus = _museum_info_answer(norm)
    if mus:
        out_text = _translate_out(mus, orig_lang)
        return {"text": out_text, "map": None, "detected_lang": orig_lang or "en", "translated": bool(orig_lang)}

    fallback = "I'm not sure I understand — could you try asking in a different way?"
    out_text = _translate_out(fallback, orig_lang)
    return {"text": out_text, "map": None, "detected_lang": orig_lang or "en", "translated": bool(orig_lang)}
