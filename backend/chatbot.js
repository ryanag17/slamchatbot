/* =========================================================
    Not in Use - Old File
   ========================================================= */
let museumInfo = {};
let exhibitionsData = [];
let slamArtData = [];
let mapLocationsData = [];
let artworksData = [];

let __fusesBuilt = false;
window.__museumLoaded = false;

let fuseExhibitions = null;
let fuseArtByTitle = null;
let fuseArtByArtist = null;
let fuseMapCategories = null;
let fuseLocations = null;
let fuseGeneral = null;

const hasFuse = typeof Fuse !== "undefined";
const hasNLP = typeof nlp !== "undefined";
const hasDayjs = typeof dayjs !== "undefined";
const hasSpellCorrector = typeof spellCorrector !== "undefined";

/* Load JSON Data */
function loadJSONData() {
    const paths = [
        "backend/data/museum_info.json",
        "backend/data/exhibitions.json",
        "backend/data/slam_art.json",
        "backend/data/map_locations.json",
        "backend/data/artworks.json"
    ];

    Promise.all(
        paths.map(p =>
            fetch(p)
                .then(r => r.ok ? r.json() : null)
                .catch(() => null)
        )
    )
    .then(([info, exhibitions, slamArt, mapLocs, artworks]) => {
        museumInfo = info || {};
        exhibitionsData = exhibitions || [];
        slamArtData = slamArt || [];
        mapLocationsData = mapLocs || [];
        artworksData = artworks || [];

        try { buildFuses(); }
        catch (e) { console.warn("Fuse build error:", e); }
        finally { window.__museumLoaded = true; }
    })
    .catch(() => {
        try { buildFuses(); } catch {}
        window.__museumLoaded = true;
    });
}

loadJSONData();

/* Fuzzy Search */
function buildFuses() {
    if (!hasFuse) { __fusesBuilt = true; return; }

    fuseExhibitions = new Fuse(
        exhibitionsData.map(e => ({
            id: e.id,
            name: e.name,
            description: e.description
        })),
        { keys: ["name", "id", "description"], threshold: 0.45 }
    );

    fuseArtByTitle = new Fuse(
        slamArtData.map(a => ({
            id: a.id,
            title: a.title,
            artist: a.artist,
            gallery: a.gallery
        })),
        { keys: ["title"], threshold: 0.45 }
    );

    fuseArtByArtist = new Fuse(
        slamArtData.map(a => ({ id: a.id, artist: a.artist })),
        { keys: ["artist"], threshold: 0.45 }
    );

    const categories = [];
    for (const floor of mapLocationsData) {
        for (const g of floor.galleries || []) {
            categories.push({
                category: g.category,
                floor: floor.floor,
                numbers: g.numbers || []
            });
        }
    }

    fuseMapCategories = new Fuse(categories, {
        keys: ["category"],
        threshold: 0.45
    });

    __fusesBuilt = true;
}

/* NLP Help */
function sanitize(text) {
    return (text || "")
        .toLowerCase()
        .replace(/[^\w\s]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}

function lemmatizeTokens(text) {
    if (hasNLP) {
        try {
            return nlp(text).terms().out("lemma").map(t => t.toLowerCase());
        } catch {}
    }
    return sanitize(text).split(" ");
}

function correctSpelling(input) {
    if (!hasSpellCorrector) return input;
    try {
        return input.split(" ").map(w => {
            const c = spellCorrector.getCorrections(w);
            return c && c.length ? c[0] : w;
        }).join(" ");
    } catch {
        return input;
    }
}

function capitalize(str) {
    return str ? str[0].toUpperCase() + str.slice(1) : str;
}

function isLocationQuestion(s) {
    return /\b(where|located|find|location|map|directions)\b/.test(s);
}

/* Router */
function processInput(rawInput) {
    if (!rawInput || !rawInput.trim()) {
        return "I'm sorry, I didn’t quite catch that. Could you try again?";
    }

    const corrected = correctSpelling(rawInput);
    const s = sanitize(corrected);
    const lemmas = lemmatizeTokens(s);

    /* Greeting */
    if (/^(hi|hello|hey|greetings)\b/.test(s)) {
        return "Hello there! How may I help you today?";
    }

    return (
        handleMuseumInfo(s) ||
        handleExhibitions(s) ||
        handleMapLocations(s) || 
        handleSlamArt(s) ||
        handleGeneric(s) ||
        "I'm not sure I understand — could you try asking in a different way?"
    );
}

/* Handlers */
function handleGeneric(s) {
    if (/how are you/.test(s)) return "I'm doing well! What would you like to know?";
    if (/thank/.test(s)) return "You're welcome! 😊";
    return null;
}

function handleMuseumInfo(s) {
    if (s.includes("museum name")) {
        return `We are called the ${museumInfo.name || "St. Louis Art Museum"}.`;
    }

    if (s.includes("where") || s.includes("address")) {
        return museumInfo.location
            ? `We are located at ${museumInfo.location}.`
            : null;
    }

    if (s.includes("hours") || s.includes("open")) {
        if (!museumInfo.museum_hours) return null;
        return Object.entries(museumInfo.museum_hours)
            .map(([d, h]) => `${capitalize(d)}: ${h}`)
            .join("; ");
    }

    return null;
}

function handleExhibitions(s) {
    if (!fuseExhibitions) return null;
    const r = fuseExhibitions.search(s);
    if (r.length && r[0].score < 0.6) {
        const e = r[0].item;
        return `${e.name}: ${e.description || "No description available."}`;
    }
    return null;
}

function handleSlamArt(s) {
    if (!fuseArtByTitle) return null;
    const r = fuseArtByTitle.search(s);
    if (r.length && r[0].score < 0.55) {
        const a = r[0].item;
        return `${a.title} by ${a.artist}, located in gallery ${a.gallery}.`;
    }
    return null;
}

function handleMapLocations(s) {
    const galleryMatch = s.match(/\bgallery\s*([0-9]{1,3}[a-z]?)\b/);
    const bareNumberMatch = !galleryMatch ? s.match(/\b([0-9]{3}[a-z]?)\b/) : null;

    const candidateNum = galleryMatch ? galleryMatch[1] : (bareNumberMatch ? bareNumberMatch[1] : null);

    if (candidateNum && isLocationQuestion(s)) {
        const target = String(candidateNum).toUpperCase();

        for (const floor of mapLocationsData || []) {
            for (const g of (floor.galleries || [])) {
                const nums = (g.numbers || []).map(x => String(x).toUpperCase());
                if (nums.includes(target)) {
                    return `Gallery ${target} is on floor ${floor.floor} in the ${g.category} section.`;
                }
            }

            for (const key of ["stairs", "elevators", "coat_checks"]) {
                const arr = (floor[key] || []).map(x => String(x).toUpperCase());
                if (arr.includes(target)) {
                    return `${capitalize(key.replace("_", " "))} ${target} is on floor ${floor.floor}.`;
                }
            }

            for (const rr of (floor.restrooms || [])) {
                if (String(rr.location || "").toUpperCase() === target) {
                    return `A ${rr.type} restroom is near ${target} on floor ${floor.floor}.`;
                }
            }
        }
        return `I couldn't find gallery ${target} in the map data.`;
    }

    if (!fuseMapCategories) return null;
    const r = fuseMapCategories.search(s);
    if (r.length && r[0].score < 0.6) {
        const f = r[0].item;
        return `${f.category} is on floor ${f.floor}, galleries ${f.numbers.join(", ")}.`;
    }

    return null;
}

/* Exports */
function getResponse(input) {
    return processInput(input);
}

if (typeof window !== "undefined") {
    window.processInput = processInput;
    window.getResponse = getResponse;
}

if (typeof module !== "undefined") {
    module.exports = { processInput, getResponse };
}
