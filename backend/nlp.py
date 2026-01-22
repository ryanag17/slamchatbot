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


def _json_candidates(filename: str) -> List[str]:
    candidates = [
        os.path.join(DATA_DIR, filename),
        os.path.join(BASE_DIR, filename),
        os.path.join(PROJECT_ROOT, filename),
        os.path.join(PROJECT_ROOT, "backend", filename),
        os.path.join(PROJECT_ROOT, "backend", "data", filename),
        os.path.join(PROJECT_ROOT, "data", filename),
        os.path.abspath(os.path.join(os.getcwd(), filename)),
        os.path.abspath(os.path.join(os.getcwd(), "backend", filename)),
        os.path.abspath(os.path.join(os.getcwd(), "backend", "data", filename)),
        os.path.abspath(os.path.join(os.getcwd(), "data", filename)),
    ]

    env_dir = os.environ.get("SLAMCHATBOT_DATA_DIR")
    if env_dir:
        candidates.insert(0, os.path.join(env_dir, filename))

    seen = set()
    out = []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


MUSEUM_INFO = _load_json_first_existing(_json_candidates("museum_info.json"), {})
EXHIBITIONS = _load_json_first_existing(_json_candidates("exhibitions.json"), [])
SLAM_ART = _load_json_first_existing(_json_candidates("slam_art.json"), [])
MAP_LOCATIONS = _load_json_first_existing(_json_candidates("map_locations.json"), [])

_NLP = spacy.load("en_core_web_sm")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

BOT_NAME = "SLAM Chatbot"


def _get_any(a: Dict[str, Any], *keys: str, default=None):
    """Return the first matching key from a dict, trying multiple possible key spellings."""
    if not isinstance(a, dict):
        return default
    for k in keys:
        if k in a and a.get(k) not in (None, ""):
            return a.get(k)
    return default


# Indexes
# -------------------------
_EXH_BY_ID = {str((e.get("id") or "")).upper(): e for e in EXHIBITIONS if e.get("id")}
_EXH_NAMES = [e.get("name", "") for e in EXHIBITIONS if e.get("name")]
_EXH_NAME_TO_OBJ = {e.get("name", ""): e for e in EXHIBITIONS if e.get("name")}

_ART_TITLES: List[str] = []
_ART_TITLE_TO_OBJ: Dict[str, Dict[str, Any]] = {}
_ARTISTS_SET = set()
_ARTIST_TO_PIECES: Dict[str, List[Dict[str, Any]]] = {}

for a in SLAM_ART:
    title = (_get_any(a, "title", "Title") or "").strip()
    artist = (_get_any(a, "artist", "Artist") or "").strip()

    if title:
        _ART_TITLES.append(title)
        _ART_TITLE_TO_OBJ[title] = a

    if artist:
        _ARTISTS_SET.add(artist)
        _ARTIST_TO_PIECES.setdefault(artist.lower(), []).append(a)

_ARTISTS = sorted(_ARTISTS_SET)

_CATEGORY_ENTRIES = [] 
for floor_obj in MAP_LOCATIONS:
    floor = str(floor_obj.get("floor", "")).strip()
    for g in (floor_obj.get("galleries") or []):
        cat = (g.get("category") or "").strip()
        nums = g.get("numbers") or []
        if cat:
            _CATEGORY_ENTRIES.append((cat, floor, [str(n).upper().strip() for n in nums]))

_CATEGORIES = sorted(list({c for (c, _, _) in _CATEGORY_ENTRIES}))

_GALLERY_TO_CATEGORY: Dict[str, str] = {}
for cat, _, nums in _CATEGORY_ENTRIES:
    for n in nums:
        _GALLERY_TO_CATEGORY[n] = cat



# Helpers
# -------------------------
def _normalize(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s\-']", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


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


def _extract_subject(norm: str) -> Optional[str]:
    m = re.search(r"\b(?:tell me about|tell me more about|tell me regarding|info on|information on)\s+(.+)$", norm)
    if m:
        subj = m.group(1).strip()
        subj = re.sub(r"^(the\s+|an?\s+)", "", subj).strip()
        return subj if subj else None
    return None


def _extract_after_by(norm: str) -> Optional[str]:
    m = re.search(r"\b(?:works|art|pieces|paintings)\s+by\s+(.+)$", norm)
    if m:
        return m.group(1).strip()
    m = re.search(r"\bby\s+([a-z0-9\s\-\']+)$", norm)
    if m:
        return m.group(1).strip()
    return None


def _format_list(items: List[str], max_items: int = 8) -> str:
    if not items:
        return ""
    if len(items) <= max_items:
        return ", ".join(items)
    return ", ".join(items[:max_items]) + f", and {len(items) - max_items} more"



# Translation
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


# Small talk / general
# -------------------------
def _smalltalk_answer(norm: str) -> Optional[str]:
    if re.match(r"^(hi|hello|hey|yo|hiya|greetings)\b", norm):
        return "Hello! How can I help you today?"

    if re.search(r"\bhow are you\b|\bhow r you\b|\bhow's it going\b|\bhow is it going\b", norm):
        return "I’m doing well! What can I help you with at the museum?"

    if re.search(r"\b(what is your name|what's your name|who are you|what are you called)\b", norm):
        return f"I’m {BOT_NAME}. Ask me about exhibitions, artworks, artists, or where galleries are!"

    if re.search(r"\b(thanks|thank you|thx)\b", norm):
        return "You’re welcome! Want to ask about an exhibition, an artwork, or where something is located?"

    if re.search(r"\b(help|what can you do|how do i use this|commands)\b", norm):
        return (
            "I can help with:\n"
            "- Current exhibitions (and details/dates)\n"
            "- Artwork info (title/artist/medium/location)\n"
            "- Finding galleries or collection areas on a map\n"
            "- Museum hours, location, parking"
        )

    return None


# Museum info:
# -------------------------
def _resolve_relative_day(norm: str) -> Optional[str]:
    if re.search(r"\btoday\b", norm):
        return datetime.now().strftime("%A").lower()
    if re.search(r"\btomorrow\b", norm):
        return (datetime.now() + timedelta(days=1)).strftime("%A").lower()
    return None


def _extract_weekday(norm: str) -> Optional[str]:
    for wd in WEEKDAYS:
        if re.search(rf"\b{wd}\b", norm):
            return wd
    rel = _resolve_relative_day(norm)
    if rel:
        return rel
    return None


def _hours_for_day(day: str) -> Optional[str]:
    hours = (MUSEUM_INFO.get("museum_hours") or {})
    return hours.get(day)


def _museum_info_answer(norm: str) -> Optional[str]:
    # Address
    if re.search(r"\b(address|located|location)\b", norm) and re.search(r"\bmuseum\b|\bslam\b", norm):
        loc = MUSEUM_INFO.get("location")
        if loc:
            return f"We are located at {loc}."
        return "I don’t have the museum address available right now."

    # Phone #
    if re.search(r"\b(phone|telephone)\b", norm) or re.search(r"\bphone number\b", norm) or (
        re.search(r"\bcall\b", norm) and re.search(r"\bmuseum\b|\bslam\b", norm)
    ):
        phone = MUSEUM_INFO.get("phone_number")
        if phone:
            return f"You can call the museum at {phone}."
        return "I don’t have the phone number available right now."

    # Hours
    wd = _extract_weekday(norm)
    if wd:
        h = _hours_for_day(wd)
        if h:
            return f"Hours on {wd.title()}: {h}."
    if re.search(r"\b(hours|open|close|opening|closing)\b", norm):
        hours = (MUSEUM_INFO.get("museum_hours") or {})
        if hours:
            lines = []
            for d in WEEKDAYS:
                if d in hours:
                    lines.append(f"{d.title()}: {hours[d]}")
            if lines:
                return "Museum hours:\n" + "\n".join(lines)

    # Parking
    if re.search(r"\bparking|park\b", norm):
        parking = (MUSEUM_INFO.get("parking") or {}).get("free")
        if parking:
            return parking

    # Museum description
    if re.search(r"\b(about|description|info)\b", norm) and re.search(r"\bmuseum\b|\bslam\b", norm):
        desc = MUSEUM_INFO.get("description") or MUSEUM_INFO.get("location_description")
        if desc:
            return desc

    return None


# Exhibitions:
# -------------------------
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
    if re.search(r"\b(on view|currently on view|current exhibitions|currently on display|on display|what's on view|whats on view)\b", norm):
        on_view = [e for e in EXHIBITIONS if e.get("on_view") is True]
        if not on_view:
            return "No exhibitions are currently on view."
        names = [e.get("name", "Untitled") for e in on_view]
        return "Exhibitions currently on view: " + ", ".join(names) + "."

    m = re.search(r"\bEXH\d{3}\b", norm.upper())
    if m:
        ex = _EXH_BY_ID.get(m.group(0).upper())
        if ex:
            return _format_exhibition(ex)

    if not _EXH_NAMES:
        return None

    subj = _extract_subject(norm) or norm
    best = process.extractOne(subj, _EXH_NAMES, scorer=fuzz.WRatio)
    if not best:
        return None

    name, score = best[0], best[1]
    overlap = _token_overlap_score(subj, name)

    intent = re.search(r"\b(exhibition|exhibit|show|on view|on display|runs|dates|until|start date|end date)\b", norm) is not None

    if (score >= 80 and overlap >= 0.35) or (intent and score >= 70 and overlap >= 0.25):
        ex = _EXH_NAME_TO_OBJ.get(name)
        if ex:
            return _format_exhibition(ex)

    return None


# Artworks/Artists:
# -------------------------
def _format_artwork(a: Dict[str, Any]) -> str:
    title = _get_any(a, "title", "Title", default="Untitled")
    artist = _get_any(a, "artist", "Artist", default="Unknown")
    date = _get_any(a, "date", "Date", default="N/A")
    gallery = _get_any(a, "gallery", "Gallery", default="N/A")

    desc = (_get_any(a, "description", "Description") or "").strip() or "No description available."

    medium = _get_any(a, "medium", "Medium")
    made_in = _get_any(a, "made_in", "Made_in", "Made In", "madeIn", "MadeIn")
    culture = _get_any(a, "culture", "Culture")
    collection = _get_any(a, "collection", "Collection")
    on_view = _get_any(a, "on_view", "On_view", "On View", "onView")

    lines = []
    lines.append(f"{title}")
    lines.append(f"Artist: {artist}")
    lines.append(f"Date: {date}")
    lines.append(f"Location: Gallery {gallery}")

    if collection:
        lines.append(f"Collection: {collection}")
    if medium:
        lines.append(f"Medium: {medium}")
    if made_in:
        lines.append(f"Made in: {made_in}")
    if culture:
        lines.append(f"Culture: {culture}")

    if isinstance(on_view, bool):
        lines.append("On view: Yes" if on_view else "On view: No")

    lines.append("")
    lines.append("Description:")
    lines.append(desc)

    return "\n".join(lines)


def _artist_list_works(artist: str) -> str:
    pieces = _ARTIST_TO_PIECES.get(artist.lower(), [])
    if not pieces:
        return f"I couldn't find any works by {artist}."

    def _title(p):
        return (_get_any(p, "title", "Title", default="Untitled") or "Untitled")

    def _gallery(p):
        return (_get_any(p, "gallery", "Gallery", default="N/A") or "N/A")

    def _on_view(p):
        return _get_any(p, "on_view", "On View", "On_view", "onView")

    pieces_sorted = sorted(pieces, key=lambda x: (not bool(_on_view(x)), _title(x)))
    lines = []
    for p in pieces_sorted:
        title = _title(p)
        gallery = _gallery(p)
        suffix = " (on view)" if _on_view(p) is True else ""
        lines.append(f"- {title} — gallery {gallery}{suffix}")

    return f"Works by {artist}:\n" + "\n".join(lines)


def _art_answer(norm: str) -> Optional[str]:
    # works by artist
    if re.search(r"\b(works|pieces|art|paintings)\s+by\b", norm):
        name_part = _extract_after_by(norm) or norm
        if _ARTISTS:
            best = process.extractOne(name_part, _ARTISTS, scorer=fuzz.WRatio)
            if best and best[1] >= 70:
                return _artist_list_works(best[0])

    # tell me about artist
    if _ARTISTS and re.search(r"\b(tell me about|who is|about|info on|information on)\b", norm):
        subj = _extract_subject(norm)
        if subj:
            best_artist = process.extractOne(subj, _ARTISTS, scorer=fuzz.WRatio)
            if best_artist and best_artist[1] >= 82:
                return _artist_list_works(best_artist[0])

    # artwork title match
    if not _ART_TITLES:
        return None

    subj = _extract_subject(norm) or norm
    best = process.extractOne(subj, _ART_TITLES, scorer=fuzz.WRatio)
    if not best:
        return None

    title, score = best[0], best[1]
    overlap = _token_overlap_score(subj, title)

    intent = re.search(r"\b(tell me about|about|where is|where's|located|location|who made|who painted|artist of)\b", norm) is not None
    if (score >= 82 and overlap >= 0.35) or (intent and score >= 75 and overlap >= 0.30):
        art = _ART_TITLE_TO_OBJ.get(title)
        if art:
            return _format_artwork(art)

    return None


# Recommendations:
# -------------------------
def _pick_random_art(filter_fn=None) -> Optional[Dict[str, Any]]:
    pool = SLAM_ART
    if filter_fn:
        pool = [a for a in SLAM_ART if filter_fn(a)]
    if not pool:
        return None
    return random.choice(pool)


def _must_see_answer(norm: str) -> Optional[str]:
    if not re.search(r"\b(must see|must-see|recommend|recommendation|suggest|highlight)\b", norm):
        return None

    if _CATEGORIES:
        best = process.extractOne(norm, _CATEGORIES, scorer=fuzz.WRatio)
        if best:
            cat, score = best[0], best[1]
            if score >= 78 or _token_overlap_score(norm, cat) >= 0.45:
                galleries = []
                for c, _, nums in _CATEGORY_ENTRIES:
                    if c == cat:
                        galleries.extend(nums)
                galleries = list({g.upper().strip() for g in galleries})
                pick = _pick_random_art(lambda a: str(_get_any(a, "gallery", "Gallery", default="")).upper().strip() in galleries)
                if pick:
                    return f"A must-see in {cat}: " + _format_artwork(pick)

    pick = _pick_random_art(lambda a: _get_any(a, "on_view", "On View", "onView") is True) or _pick_random_art()
    if pick:
        return "Here’s a must-see artwork: " + _format_artwork(pick)
    return None


# Category matching & maps:
# -------------------------
def _best_category(norm: str) -> Optional[str]:
    if not _CATEGORIES:
        return None

    filters = []
    if "native" in norm:
        filters.append("native")
    if "islamic" in norm:
        filters.append("islamic")
    if "european" in norm:
        filters.append("europe")
    if "american" in norm:
        filters.append("american")

    candidates = _CATEGORIES
    if filters:
        filtered = [c for c in _CATEGORIES if all(f in c.lower() for f in filters)]
        if filtered:
            candidates = filtered

    for c in candidates:
        c_norm = _normalize(c)
        if c_norm and re.search(rf"\b{re.escape(c_norm)}\b", norm):
            return c

    best = process.extractOne(norm, candidates, scorer=fuzz.WRatio)
    if not best:
        return None
    cat, score = best[0], best[1]
    overlap = _token_overlap_score(norm, cat)

    if score >= 84 or overlap >= 0.50:
        return cat
    return None


def _category_location_payload(norm: str) -> Optional[Dict[str, Any]]:
    if not re.search(r"\b(where|located|find|location)\b", norm):
        return None

    cat = _best_category(norm)
    if not cat:
        return None

    hits = [(c, f, nums) for (c, f, nums) in _CATEGORY_ENTRIES if c == cat]
    if not hits:
        return None

    floor_map: Dict[str, List[str]] = {}
    for _, floor, nums in hits:
        floor_map.setdefault(floor, [])
        floor_map[floor].extend(nums)

    floors_sorted = sorted(
        floor_map.keys(),
        key=lambda x: int(re.sub(r"\D", "", x) or "0")
    )

    parts = []
    for floor in floors_sorted:
        uniq = []
        seen = set()
        for n in floor_map[floor]:
            if n not in seen:
                seen.add(n)
                uniq.append(n)
        parts.append(f"floor {floor} (galleries {', '.join(uniq)})")

    text = f"{cat} is located on " + " and ".join(parts) + "."

    return {"text": text, "image_url": None}


def _map_answer(norm: str) -> Optional[Dict[str, Any]]:
    cat_payload = _category_location_payload(norm)
    if cat_payload:
        return cat_payload

    token = _extract_gallery_token(norm)
    if token and re.search(r"\b(where|located|find|map|gallery|room|rm)\b", norm):
        img_payload = get_gallery_map_image(token, MAP_LOCATIONS)
        if img_payload and img_payload.get("image_url"):
            return {"text": f"Here is where gallery {token} is located:", "image_url": img_payload["image_url"]}
        return {"text": f"I couldn’t generate the map image for gallery {token}.", "image_url": None}

    return None


# Suggestions:
# -------------------------
_SUGGESTION_TEMPLATES = [
    "What exhibitions are currently on view?",
    "Tell me more about {exh_name}.",
    "When does {exh_name} run?",
    "Tell me about {art_title}.",
    "Show me works by {artist}.",
    "What’s a must-see artwork in the {category} galleries?",
    "Where is {category}?",
    "Where is gallery 216?",
    "What are the museum hours today?",
    "What’s your name?",
]


def _make_suggestions(orig_lang: Optional[str]) -> List[str]:
    categories = _CATEGORIES[:50]
    art_titles = _ART_TITLES[:200]
    artists = _ARTISTS[:200]
    exh_names = _EXH_NAMES[:100]

    cat_pick = random.choice(categories) if categories else "American Art"
    art_pick = random.choice(art_titles) if art_titles else "View of St. Louis"
    artist_pick = random.choice(artists) if artists else "Taxile Doat"
    exh_pick = random.choice(exh_names) if exh_names else "a current exhibition"

    candidates = [
        t.format(category=cat_pick, art_title=art_pick, artist=artist_pick, exh_name=exh_pick)
        for t in _SUGGESTION_TEMPLATES
    ]
    random.shuffle(candidates)

    picks = []
    for s in candidates:
        if s not in picks:
            picks.append(s)
        if len(picks) == 3:
            break

    return [_translate_out(s, orig_lang) for s in picks]


# Main router:
# -------------------------
def generate_response(user_text: str) -> Dict[str, Any]:
    en_text, orig_lang = _translate_in(user_text)
    norm = _normalize(en_text)

    # small talk
    st = _smalltalk_answer(norm)
    if st:
        return {"text": _translate_out(st, orig_lang), "image_url": None, "suggestions": _make_suggestions(orig_lang)}

    # recommendations
    must = _must_see_answer(norm)
    if must:
        return {"text": _translate_out(must, orig_lang), "image_url": None, "suggestions": _make_suggestions(orig_lang)}

    # maps
    map_payload = _map_answer(norm)
    if map_payload:
        return {
            "text": _translate_out(map_payload["text"], orig_lang),
            "image_url": map_payload.get("image_url"),
            "suggestions": _make_suggestions(orig_lang),
        }

    # exhibitions
    ex = _exhibitions_answer(norm)
    if ex:
        return {"text": _translate_out(ex, orig_lang), "image_url": None, "suggestions": _make_suggestions(orig_lang)}

    # art/artists
    art = _art_answer(norm)
    if art:
        return {"text": _translate_out(art, orig_lang), "image_url": None, "suggestions": _make_suggestions(orig_lang)}

    # museum info
    mus = _museum_info_answer(norm)
    if mus:
        return {"text": _translate_out(mus, orig_lang), "image_url": None, "suggestions": _make_suggestions(orig_lang)}

    fallback = "I'm not sure I understand — could you try asking in a different way?"
    return {"text": _translate_out(fallback, orig_lang), "image_url": None, "suggestions": _make_suggestions(orig_lang)}


def respond(text: str) -> Dict[str, Any]:
    return generate_response(text)
