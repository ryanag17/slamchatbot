/* backend/chatbot.js
   Browser-based NLP using CDN libs:
   - compromise (nlp) for tokenization / basic NER / normalization
   - Fuse.js for fuzzy search
   Works client-side (runs on GitHub Pages).
*/

let museumInfo = {};
let exhibitionsData = [];
let slamArtData = [];
let mapLocationsData = [];

let fuseExhibitions = null;
let fuseArt = null;

window.__museumLoaded = false;

// ---------- Load JSON files ----------
function loadJSONData() {
    Promise.all([
        fetch('backend/data/museum_info.json').then(r => r.json()),
        fetch('backend/data/exhibitions.json').then(r => r.json()),
        fetch('backend/data/slam_art.json').then(r => r.json()),
        fetch('backend/data/map_locations.json').then(r => r.json())
    ])
    .then(([info, exhibitions, art, map]) => {
        museumInfo = info || {};
        exhibitionsData = exhibitions || [];
        slamArtData = art || [];
        mapLocationsData = map || [];

        // Build Fuse indexes for fuzzy searching
        try {
            fuseExhibitions = new Fuse(exhibitionsData, {
                keys: [
                    { name: "name", weight: 0.7 },
                    { name: "description", weight: 0.2 },
                    { name: "id", weight: 0.1 }
                ],
                threshold: 0.35,
                ignoreLocation: true
            });

            fuseArt = new Fuse(slamArtData, {
                keys: [
                    { name: "title", weight: 0.7 },
                    { name: "artist", weight: 0.2 },
                    { name: "id", weight: 0.1 }
                ],
                threshold: 0.35,
                ignoreLocation: true
            });
        } catch (e) {
            console.warn("Fuse not available or indexing failed:", e);
        }

        window.__museumLoaded = true;
    })
    .catch(err => {
        console.error("Error loading JSON files:", err);
        window.__museumLoaded = true;
    });
}

loadJSONData();

// ---------- Utilities ----------

// sanitize text and remove punctuation but keep internal spaces
function sanitizeText(s) {
    if (!s || typeof s !== 'string') return '';
    return s.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, ' ').trim();
}

// produce tokens and also try to lemmatize/normalize using compromise
function nlpTokens(raw) {
    if (!raw) return [];
    const doc = window.nlp ? window.nlp(raw) : null;
    // fallback: simple split
    if (!doc) {
        return sanitizeText(raw).split(' ').filter(Boolean);
    }
    // normalize and get noun/verb tokens and lemmas where possible
    const normalized = doc.normalize({punctuation: true, lowercase: true}).out('text');
    // get array of terms
    let terms = [];
    try {
        terms = doc.terms().out('array');
    } catch (e) {
        terms = normalized.split(' ');
    }
    // include nouns, people, places, verbs as extra
    const nouns = doc.nouns().out('array') || [];
    const people = doc.people().out('array') || [];
    const places = doc.places().out('array') || [];
    const verbs = doc.verbs().out('normal') || []; // .out('normal') gives normalized verbs
    // combine and dedupe
    const combined = [...terms, ...nouns, ...people, ...places, ...verbs].map(s => sanitizeText(s)).filter(Boolean);
    return Array.from(new Set(combined));
}

// simple function to check if all required keywords exist (in sanitized text)
function hasKeywords(raw, keywords) {
    const s = sanitizeText(raw);
    // check each keyword's sanitized form
    return keywords.every(k => s.split(' ').includes(sanitizeText(k)));
}

// ---------- Main processInput ----------
function processInput(rawInput) {
    if (!rawInput || typeof rawInput !== "string") {
        return "I'm sorry, I didn't quite get that. Could you try asking again?";
    }

    // Sanitize for keyword checks and also create NLP tokens
    const clean = sanitizeText(rawInput);
    const tokens = nlpTokens(rawInput);

    // Intent pipeline: generic -> museum -> exhibitions -> art -> map
    return handleGeneric(clean, tokens, rawInput) ||
           handleMuseumInfo(clean, tokens, rawInput) ||
           handleExhibitions(clean, tokens, rawInput) ||
           handleSlamArt(clean, tokens, rawInput) ||
           handleMapLocations(clean, tokens, rawInput) ||
           "I'm not sure I understand — could you try asking in a different way?";
}

// ---------- Generic messages ----------
function handleGeneric(clean, tokens, raw) {
    // greetings
    if (/\b(hello|hi|hey)\b/.test(clean)) {
        return "Hello there! How may I help you today?";
    }
    if (clean.includes("how are you")) {
        return "I'm doing well! What would you like to know?";
    }
    if (clean.includes("your name") || clean.includes("call you")) {
        return "I don’t have a name yet — but I'd love suggestions!";
    }
    return null;
}

// ---------- Museum info ----------
function handleMuseumInfo(clean, tokens, raw) {
    if (hasKeywords(raw, ["name", "museum"]) || clean.includes("museum name")) {
        return museumInfo.name ? `We are called the ${museumInfo.name}.` : "We are the St. Louis Art Museum.";
    }

    if (tokens.includes("tuesday") || clean.includes("tuesday") || clean.includes("hours")) {
        return museumInfo.museum_hours?.tuesday
            ? `We are open on Tuesdays from ${museumInfo.museum_hours.tuesday}.`
            : "Please check the museum hours.";
    }

    if (clean.includes("free parking") || clean.includes("parking")) {
        return museumInfo.parking?.free || "Parking information is not available right now.";
    }

    if (clean.includes("location") || clean.includes("address")) {
        return museumInfo.location ? `Our address is: ${museumInfo.location}` : "Location information not available.";
    }

    return null;
}

// ---------- Exhibitions ----------
function handleExhibitions(clean, tokens, raw) {
    // keyword groups: require both words presence (makes "view" alone not trigger)
    const keywordGroups = [
        ["exhibitions", "view"],      // "exhibitions" + "view"
        ["current", "exhibitions"],   // "current" + "exhibitions"
        ["what", "on", "view"]        // "what's on view" variations
    ];

    for (const group of keywordGroups) {
        if (group.every(k => sanitizeText(raw).includes(sanitizeText(k)))) {
            const onView = exhibitionsData.filter(ex => ex.on_view);
            if (onView.length === 0) return "No exhibitions are currently on view.";
            const names = onView.map(ex => ex.name).join(", ");
            return `Exhibitions currently on view: ${names}`;
        }
    }

    // Try fuzzy match an exhibition name or id using Fuse
    if (fuseExhibitions && raw.trim().length > 1) {
        const res = fuseExhibitions.search(raw);
        if (res && res.length > 0 && res[0].score <= 0.35) {
            const ex = res[0].item;
            return `${ex.name} runs from ${ex.start_date} to ${ex.end_date}. ${ex.description}`;
        }
    }

    // exact id match (e.g., EXH001)
    const idMatch = raw.match(/exh\s*0*?(\d+)/i) || raw.match(/exh0*\d+/i);
    if (idMatch) {
        const q = idMatch[0].toLowerCase().replace(/\s+/g, '');
        const found = exhibitionsData.find(e => e.id.toLowerCase() === q || e.id.toLowerCase() === idMatch[0].toLowerCase());
        if (found) return `${found.name} runs from ${found.start_date} to ${found.end_date}. ${found.description}`;
    }

    return null;
}

// ---------- SLAM Art ----------
function handleSlamArt(clean, tokens, raw) {
    // fuzzy search artworks by title/artist
    if (fuseArt && raw.trim().length > 1) {
        const res = fuseArt.search(raw);
        if (res && res.length > 0 && res[0].score <= 0.35) {
            const art = res[0].item;
            return `${art.title} by ${art.artist} (${art.date}). It's located in gallery ${art.gallery}.`;
        }
    }

    // specific gallery lookup: "gallery 329"
    const galleryMatch = raw.match(/\b(\d{2,4})\b/);
    if (galleryMatch) {
        const num = galleryMatch[1];
        const items = slamArtData.filter(a => String(a.gallery) === String(num));
        if (items.length > 0) {
            return `In gallery ${num}, you can find: ${items.map(a => a.title).join(", ")}.`;
        }
    }

    // title exact substring fallback
    for (const art of slamArtData) {
        if (sanitizeText(raw).includes(sanitizeText(art.title))) {
            return `${art.title} by ${art.artist} (${art.date}). It's located in gallery ${art.gallery}.`;
        }
    }

    return null;
}

// ---------- Map locations ----------
function handleMapLocations(clean, tokens, raw) {
    // If user asks "where is X" or "where are the galleries for X"
    if (clean.includes("where") || clean.includes("location") || clean.includes("located")) {
        // check categories
        for (const floor of mapLocationsData) {
            for (const g of floor.galleries) {
                const categoryLower = sanitizeText(g.category);
                if (sanitizeText(raw).includes(categoryLower)) {
                    return `${g.category} is located on floor ${floor.floor} in galleries ${g.numbers.join(", ")}.`;
                }
            }
        }
    }

    // If user asks about a gallery number
    if (clean.includes("gallery") || /\b\d{2,4}\b/.test(clean)) {
        const numMatch = raw.match(/\b\d{2,4}\b/);
        if (numMatch) {
            const num = numMatch[0];
            for (const floor of mapLocationsData) {
                for (const g of floor.galleries) {
                    // g.numbers might be strings, ensure match
                    if (g.numbers && g.numbers.map(n => String(n)).includes(String(num))) {
                        return `Gallery ${num} is part of the ${g.category} section on floor ${floor.floor}.`;
                    }
                }
            }
        }
    }

    return null;
}

// Expose globally
window.processInput = processInput;
window.museumInfo = museumInfo;
