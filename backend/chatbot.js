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



const hasFuse = typeof Fuse !== 'undefined';
const hasNLP = typeof nlp !== 'undefined';
const hasDayjs = typeof dayjs !== 'undefined';
const hasSpellCorrector = typeof spellCorrector !== 'undefined';


function loadJSONData() {
    const paths = [
        'backend/data/museum_info.json',
        'backend/data/exhibitions.json',
        'backend/data/slam_art.json',
        'backend/data/map_locations.json',
        'backend/data/artworks.json'
    ];

    const fetches = paths.map(p =>
        fetch(p).then(r => {
            if (!r.ok) return null;
            return r.json().catch(() => null);
        }).catch(() => null)
    );

    Promise.all(fetches)
        .then(([info, exhibitions, slamArt, mapLocs, artworks]) => {
            museumInfo = info || {};
            exhibitionsData = Array.isArray(exhibitions) ? exhibitions : (exhibitions || []);
            slamArtData = Array.isArray(slamArt) ? slamArt : (slamArt || []);
            mapLocationsData = Array.isArray(mapLocs) ? mapLocs : (mapLocs || []);
            artworksData = Array.isArray(artworks) ? artworks : (artworks || []);

            try {
                buildFuses();
            } catch (err) {
                console.warn("Error building fuses:", err);
            } finally {
                window.__museumLoaded = true;
            }
        })
        .catch(err => {
            console.error("Error loading JSON files:", err);
            try { buildFuses(); } catch(e){ }
            window.__museumLoaded = true;
        });
}

loadJSONData();

function buildFuses() {
    if (!hasFuse) { __fusesBuilt = true; return; }

    try {
        fuseExhibitions = new Fuse((exhibitionsData || []).map(e => ({ id: e.id, name: e.name, description: e.description })), {
            keys: ['name', 'id', 'description'],
            includeScore: true,
            threshold: 0.45
        });

        fuseArtByTitle = new Fuse((slamArtData || []).map(a => ({ id: a.id, title: a.title, artist: a.artist, gallery: a.gallery })), {
            keys: ['title'],
            includeScore: true,
            threshold: 0.45
        });

        fuseArtByArtist = new Fuse((slamArtData || []).map(a => ({ id: a.id, artist: a.artist })), {
            keys: ['artist'],
            includeScore: true,
            threshold: 0.45
        });

        const categories = [];
        for (const floor of (mapLocationsData || [])) {
            for (const g of (floor.galleries || [])) {
                categories.push({ category: g.category, floor: floor.floor, numbers: g.numbers || [] });
            }
        }
        fuseMapCategories = new Fuse(categories, { keys: ['category'], includeScore: true, threshold: 0.45 });

        const locFlat = [];
        for (const floor of (mapLocationsData || [])) {
            for (const g of (floor.galleries || [])) {
                locFlat.push({ type: g.type || 'gallery', name: g.name || g.category, floor: floor.floor, numbers: g.numbers || [] });
            }
            if (floor.restrooms) locFlat.push(...floor.restrooms.map(r => ({ type: 'restroom', name: r.type || 'restroom', floor: floor.floor, location: r.location })));
            if (floor.elevators) locFlat.push(...floor.elevators.map(e => ({ type: 'elevator', name: e, floor: floor.floor })));
            if (floor.stairs) locFlat.push(...floor.stairs.map(s => ({ type: 'stairs', name: s, floor: floor.floor })));
        }
        fuseLocations = new Fuse(locFlat, { keys: ['type', 'name', 'numbers'], includeScore: true, threshold: 0.45 });

        fuseGeneral = new Fuse([
            { key: "address", phrases: ["address", "location", "where are you located"] },
            { key: "name", phrases: ["your name", "what are you called", "who are you"] },
            { key: "hours", phrases: ["hours", "open", "closing", "open today", "open tomorrow"] },
            { key: "greeting", phrases: ["hi", "hello", "hey"] }
        ], { keys: ['phrases'], includeScore: true, threshold: 0.35 });

        __fusesBuilt = true;
    } catch (e) {
        console.warn("buildFuses encountered an error:", e);
        __fusesBuilt = true;
    }
}


function sanitize(raw) {
    return (raw || '')
        .toLowerCase()
        .replace(/[“”«»„—–…]/g, ' ')
        .replace(/[^\w\s'\-]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}


function lemmatizeTokens(raw) {
    try {
        if (hasNLP) {
            const doc = nlp(raw || '');
            const lemmas = doc.terms().out('lemma'); // array
            if (Array.isArray(lemmas) && lemmas.length) return lemmas.map(x => (x || '').toLowerCase());
        }
    } catch (e) {
    }
    return sanitize(raw).split(' ').filter(Boolean);
}


function correctSpelling(input) {
    if (!hasSpellCorrector) return input;
    try {
        const tokens = (input || '').split(/\s+/).map(t => t.trim()).filter(Boolean);
        const corrected = tokens.map(t => {
            const corrections = spellCorrector.getCorrections && spellCorrector.getCorrections(t);
            if (corrections && corrections.length) return corrections[0];
            return t;
        });
        return corrected.join(' ');
    } catch (e) {
        return input;
    }
}


function getDayName(index) {
    const days = ['sunday','monday','tuesday','wednesday','thursday','friday','saturday'];
    return days[index % 7];
}
function resolveRelativeDay(term) {
    try {
        if (hasDayjs) {
            if (term === 'today') return dayjs().format('dddd').toLowerCase();
            if (term === 'tomorrow') return dayjs().add(1, 'day').format('dddd').toLowerCase();
        } else {
            const idx = new Date().getDay();
            if (term === 'today') return getDayName(idx);
            if (term === 'tomorrow') return getDayName((idx + 1) % 7);
        }
    } catch (e) {  }
    return null;
}


function hasAllKeywords(sanitizedInput, keywords) {
    if (!sanitizedInput) return false;
    return keywords.every(k => sanitizedInput.indexOf(k) !== -1);
}
function capitalize(str) {
    if (!str) return str;
    return str.charAt(0).toUpperCase() + str.slice(1);
}


function processInput(rawInput) {
    const original = (rawInput || '').trim();
    if (!original) return "I'm sorry, I didn't quite get that. Could you try asking again?";

    const maybeCorrected = correctSpelling(original);
    const s = sanitize(maybeCorrected);
    const lemmas = lemmatizeTokens(s);

    const isGreetingOnly = /^\s*(hi|hello|hey|yo|hiya|greetings)\b/.test(s) &&
        !(/\b(exhibit|exhibition|gallery|where|hours|open|address|location|museum|artist|work|what|which|when)\b/.test(s));
    if (isGreetingOnly) {
        return "Hello there! How may I help you today?";
    }

    // priority routing
    let out = null;
    out = handleMuseumInfo(original, s, lemmas) || out;
    if (out) return out;

    out = handleExhibitions(original, s, lemmas) || out;
    if (out) return out;

    out = handleSlamArt(original, s, lemmas) || out;
    if (out) return out;

    out = handleMapLocations(original, s, lemmas) || out;
    if (out) return out;

    out = handleGeneric(original, s, lemmas) || out;
    if (out) return out;

    return "I'm not sure I understand — could you try asking in a different way?";
}


function handleGeneric(raw, s, lemmas) {
    if (/\b(how are you|how's it going|how're you)\b/.test(s)) {
        return "I'm doing well! What would you like to know?";
    }

    if (/\b(your name|what should i call you|do you have a name|call you)\b/.test(s)) {
        return "I don’t have a proper name yet — you can call me SLAM Bot!";
    }

    if (/\b(thanks|thank you|cheers)\b/.test(s)) {
        return "You're welcome! Anything else you'd like to ask?";
    }

    return null;
}

function handleMuseumInfo(raw, s, lemmas) {
    if ((s.indexOf('name') !== -1 && s.indexOf('museum') !== -1) || /\b(what is the museum called|museum name|what are you called)\b/.test(s)) {
        return museumInfo.name ? `We are called the ${museumInfo.name}.` : "We are the St. Louis Art Museum.";
    }

    if (s.indexOf('where') !== -1 && (s.indexOf('museum') !== -1 || s.indexOf('located') !== -1) || s.indexOf('address') !== -1) {
        return museumInfo.location ? `We are located at: ${museumInfo.location}.` : "Location information is not available right now.";
    }

    if (s.indexOf('phone') !== -1 || (s.indexOf('call') !== -1 && s.indexOf('number') !== -1) || s.indexOf('tel') !== -1) {
        return museumInfo.phone_number ? `You can call the museum at ${museumInfo.phone_number}.` : "Phone information not available right now.";
    }

    if (s.indexOf('open') !== -1 || s.indexOf('hours') !== -1 || s.indexOf('closing') !== -1 || s.indexOf('when') !== -1) {
        const weekdays = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
        for (const wd of weekdays) {
            if (s.indexOf(wd) !== -1) {
                const hours = museumInfo.museum_hours && museumInfo.museum_hours[wd];
                return hours ? `The museum is open on ${capitalize(wd)}: ${hours}.` : `Hours for ${capitalize(wd)} are not available.`;
            }
        }

        if (s.indexOf('today') !== -1) {
            const day = resolveRelativeDay('today');
            const hours = museumInfo.museum_hours && museumInfo.museum_hours[day];
            return hours ? `Today (${capitalize(day)}) the museum hours are: ${hours}.` : `Today's hours are not available.`;
        }
        if (s.indexOf('tomorrow') !== -1) {
            const day = resolveRelativeDay('tomorrow');
            const hours = museumInfo.museum_hours && museumInfo.museum_hours[day];
            return hours ? `Tomorrow (${capitalize(day)}) the museum hours will be: ${hours}.` : `Tomorrow's hours are not available.`;
        }

        if (museumInfo.museum_hours) {
            const summary = Object.entries(museumInfo.museum_hours)
                .filter(([k]) => weekdays.includes(k))
                .map(([k, v]) => `${capitalize(k)}: ${v}`).join('; ');
            if (summary) return `Museum hours — ${summary}.`;
        }

        return "Please check the museum hours or ask about a specific day (e.g., 'What are the hours on Tuesday?').";
    }

    if (s.indexOf('parking') !== -1 || s.indexOf('park') !== -1) {
        return museumInfo.parking && museumInfo.parking.free ? museumInfo.parking.free : "Parking information is not available right now.";
    }

    return null;
}

function handleExhibitions(raw, s, lemmas) {
    const condA = (s.indexOf('exhibition') !== -1 || s.indexOf('exhibitions') !== -1) && (s.indexOf('view') !== -1 || s.indexOf('on view') !== -1);
    const condB = (s.indexOf('current') !== -1 && s.indexOf('exhibition') !== -1);
    if (condA || condB || s.indexOf("what's on view") !== -1 || s.indexOf("whats on view") !== -1 || s.indexOf("what is on view") !== -1) {
        const onView = (exhibitionsData || []).filter(ex => ex.on_view);
        if (!onView || onView.length === 0) return "No exhibitions are currently on view.";
        const names = onView.map(e => e.name).join(', ');
        return `Exhibitions currently on view: ${names}`;
    }

    if (fuseExhibitions && s.length > 2) {
        const results = fuseExhibitions.search(s).slice(0, 3);
        if (results && results.length) {
            const best = results[0];
            if (best && best.score <= 0.6) {
                const ex = exhibitionsData.find(e => e.id === best.item.id || e.name === best.item.name);
                if (ex) return `${ex.name} runs from ${ex.start_date || 'N/A'} to ${ex.end_date || 'N/A'}. ${ex.description || ''}`;
            }
        }
    }

    const idMatch = raw.match(/(EXH\d{3})/i);
    if (idMatch) {
        const id = idMatch[1].toUpperCase();
        const ex = exhibitionsData.find(e => (e.id || '').toUpperCase() === id);
        if (ex) return `${ex.name} runs from ${ex.start_date || 'N/A'} to ${ex.end_date || 'N/A'}. ${ex.description || ''}`;
    }

    return null;
}

function handleSlamArt(raw, s, lemmas) {
    if (fuseArtByTitle && s.length > 2) {
        const r = fuseArtByTitle.search(s);
        if (r && r.length) {
            const best = r[0];
            if (best.score <= 0.55) {
                const art = slamArtData.find(a => a.id === best.item.id || a.title === best.item.title);
                if (art) return `${art.title} by ${art.artist} (${art.date || 'N/A'}). Located in gallery ${art.gallery || 'N/A'}. ${art.description || ''}`;
            }
        }
    }

    if (fuseArtByArtist && s.length > 2 && (s.includes('by ') || s.includes('works by') || s.includes('pieces by') || s.includes('paintings by') || s.includes('artist'))) {
        const r = fuseArtByArtist.search(s);
        if (r && r.length) {
            const best = r[0];
            if (best.score <= 0.55) {
                const artistName = best.item.artist || best.item.artist;
                const pieces = slamArtData.filter(a => (a.artist || '').toLowerCase() === (artistName || '').toLowerCase());
                if (pieces.length) {
                    return `Works by ${artistName}: ${pieces.map(p => `${p.title} (gallery ${p.gallery || 'N/A'})`).join('; ')}`;
                }
            }
        }
    }

    if (s.indexOf('gallery') !== -1) {
        const numMatch = s.match(/\b(\d{1,3})\b/);
        if (numMatch) {
            const num = parseInt(numMatch[1], 10);
            const items = slamArtData.filter(a => parseInt(a.gallery, 10) === num);
            if (items.length) {
                return `In gallery ${num} you can find: ${items.map(i => `${i.title} by ${i.artist}`).join('; ')}`;
            } else {
                return `I couldn't find works listed for gallery ${num}.`;
            }
        }
    }

    return null;
}

function handleMapLocations(raw, s, lemmas) {
    if (fuseMapCategories && s.length > 2 && (s.includes('where is') || s.includes('where') || s.includes('located') || s.includes('find'))) {
        const r = fuseMapCategories.search(s);
        if (r && r.length) {
            const best = r[0];
            if (best.score <= 0.6) {
                const found = best.item;
                return `${found.category} is on floor ${found.floor} in galleries ${Array.isArray(found.numbers) ? found.numbers.join(', ') : found.numbers}.`;
            }
        }
    }

    const galleryNumMatch = s.match(/\b(\d{1,3})\b/);
    if (galleryNumMatch && s.indexOf('gallery') !== -1) {
        const num = galleryNumMatch[1];
        for (const floor of (mapLocationsData || [])) {
            for (const g of (floor.galleries || [])) {
                if ((g.numbers || []).map(String).includes(String(num))) {
                    return `Gallery ${num} is part of the ${g.category} section on floor ${floor.floor}.`;
                }
            }
        }
        return `I couldn't find gallery ${num} in the map data.`;
    }

    if (s.indexOf('restroom') !== -1 || s.indexOf('toilet') !== -1 || s.indexOf('bathroom') !== -1) {
        const floorMatch = s.match(/floor\s*(\d)/);
        if (floorMatch) {
            const floorNum = String(floorMatch[1]);
            const floorObj = (mapLocationsData || []).find(f => String(f.floor) === floorNum);
            if (floorObj && floorObj.restrooms && floorObj.restrooms.length) {
                const descs = floorObj.restrooms.map(r => `${r.type} restroom at ${r.location}`).join('; ');
                return `On floor ${floorNum} restrooms: ${descs}.`;
            }
            return `I couldn't find restrooms listed for floor ${floorNum}.`;
        } else {
            const all = [];
            for (const f of (mapLocationsData || [])) {
                if (f.restrooms && f.restrooms.length) {
                    all.push(`Floor ${f.floor}: ${f.restrooms.map(r => `${r.type} at ${r.location}`).join(', ')}`);
                }
            }
            if (all.length) return `Restrooms — ${all.join(' | ')}`;
            return "Restroom information is not available.";
        }
    }

    if ((s.indexOf('coat') !== -1 && s.indexOf('check') !== -1) || s.indexOf('coat-check') !== -1) {
        const all = [];
        for (const f of (mapLocationsData || [])) {
            if (f.coat_checks && f.coat_checks.length) all.push(`Floor ${f.floor}: ${f.coat_checks.join(', ')}`);
        }
        if (all.length) return `Coat checks — ${all.join(' | ')}`;
        return "Coat check information not available.";
    }

    if (s.indexOf('elevator') !== -1 || s.indexOf('elevators') !== -1) {
        const matches = [];
        for (const f of (mapLocationsData || [])) {
            if (f.elevators && f.elevators.length) matches.push(`Floor ${f.floor}: ${f.elevators.join(', ')}`);
        }
        if (matches.length) return `Elevators — ${matches.join(' | ')}`;
        return "Elevator information not available.";
    }

    if (s.indexOf('stair') !== -1 || s.indexOf('stairs') !== -1) {
        const matches = [];
        for (const f of (mapLocationsData || [])) {
            if (f.stairs && f.stairs.length) matches.push(`Floor ${f.floor}: ${f.stairs.join(', ')}`);
        }
        if (matches.length) return `Stairs — ${matches.join(' | ')}`;
        return "Stairs information not available.";
    }

    return null;
}

function getResponse(rawInput) {
    return processInput(rawInput);
}

if (typeof window !== 'undefined') {
    window.processInput = processInput;
    window.getResponse = getResponse;
    window.museumInfo = museumInfo;
}
if (typeof module !== 'undefined' && typeof module.exports !== 'undefined') {
    module.exports = { getResponse, processInput };
}