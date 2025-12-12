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
            try { buildFuses(); } catch (err) {}
            window.__museumLoaded = true;
        })
        .catch(err => {
            try { buildFuses(); } catch(e){}
            window.__museumLoaded = true;
        });
}
loadJSONData();

function buildFuses() {
    if (!hasFuse) { __fusesBuilt = true; return; }
    try {
        fuseExhibitions = new Fuse((exhibitionsData || []).map(e => ({ id: e.id, name: e.name, description: e.description, start_date: e.start_date, end_date: e.end_date, gallery_numbers: e.gallery_numbers, curated_by: e.curated_by, collaborators: e.collaborators })), { keys: ['name','id','description'], includeScore: true, threshold: 0.45 });

        fuseArtByTitle = new Fuse((slamArtData || []).map(a => ({ id: a.id, title: a.title, artist: a.artist, gallery: a.gallery, date: a.date, description: a.description, dimensions: a.dimensions, provenance: a.provenance, image_url: a.image_url })), { keys: ['title'], includeScore: true, threshold: 0.45 });

        fuseArtByArtist = new Fuse((slamArtData || []).map(a => ({ artist: a.artist })), { keys: ['artist'], includeScore: true, threshold: 0.45 });

        const categories = [];
        for (const floor of (mapLocationsData || [])) {
            for (const g of (floor.galleries || [])) {
                categories.push({ category: g.category, floor: floor.floor, numbers: g.numbers || [] });
            }
        }
        fuseMapCategories = new Fuse(categories, { keys: ['category'], includeScore: true, threshold: 0.45 });

        const locFlat = [];
        for (const floor of (mapLocationsData || [])) {
            for (const g of (floor.galleries || []))
                locFlat.push({ type: g.type || 'gallery', name: g.name || g.category, floor: floor.floor, numbers: g.numbers || [] });

            if (floor.restrooms)
                locFlat.push(...floor.restrooms.map(r => ({ type: 'restroom', name: r.type, floor: floor.floor, location: r.location })));

            if (floor.elevators)
                locFlat.push(...floor.elevators.map(e => ({ type: 'elevator', name: e, floor: floor.floor })));

            if (floor.stairs)
                locFlat.push(...floor.stairs.map(s => ({ type: 'stairs', name: s, floor: floor.floor })));
        }
        fuseLocations = new Fuse(locFlat, { keys: ['type','name','numbers'], includeScore: true, threshold: 0.45 });

        fuseGeneral = new Fuse([
            { key: "address", phrases: ["address","location","where are you located","museum address"] },
            { key: "name", phrases: ["your name","what are you called","who are you"] },
            { key: "hours", phrases: ["hours","open","closing","opening","time"] },
            { key: "greeting", phrases: ["hi","hello","hey"] }
        ], { keys:['phrases'], includeScore:true, threshold:0.35 });

    } catch (e) {}
    __fusesBuilt = true;
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
            const lemmas = doc.terms().out('lemma');
            if (Array.isArray(lemmas) && lemmas.length)
                return lemmas.map(x => (x || '').toLowerCase());
        }
    } catch (e) {}
    return sanitize(raw).split(' ').filter(Boolean);
}

function correctSpelling(input) {
    if (!hasSpellCorrector) return input;
    try {
        const tokens = (input || '').split(/\s+/).map(t => t.trim()).filter(Boolean);
        const corrected = tokens.map(t => {
            const c = spellCorrector.getCorrections && spellCorrector.getCorrections(t);
            return (c && c.length) ? c[0] : t;
        });
        return corrected.join(' ');
    } catch (e) { return input; }
}

function getDayName(index) {
    const days = ['sunday','monday','tuesday','wednesday','thursday','friday','saturday'];
    return days[index % 7];
}

function resolveRelativeDay(term) {
    try {
        if (hasDayjs) {
            if (term === 'today') return dayjs().format('dddd').toLowerCase();
            if (term === 'tomorrow') return dayjs().add(1,'day').format('dddd').toLowerCase();
        } else {
            const idx = new Date().getDay();
            if (term === 'today') return getDayName(idx);
            if (term === 'tomorrow') return getDayName((idx+1)%7);
        }
    } catch(e){}
    return null;
}

function capitalize(str) {
    if (!str) return str;
    return str.charAt(0).toUpperCase() + str.slice(1);
}

function processInput(rawInput) {
    const original = (rawInput || '').trim();
    if (!original) return "I'm sorry, I didn't quite get that. Could you try asking again?";
    const cleaned = correctSpelling(original);
    const s = sanitize(cleaned);
    const lemmas = lemmatizeTokens(s);

    const isGreetingOnly =
        /^\s*(hi|hello|hey|yo|hiya|greetings)\b/.test(s) &&
        !(/\b(exhibit|exhibition|gallery|where|hours|open|address|location|museum|artist|work|what|which|when|restroom|bathroom|toilet)\b/.test(s));

    if (isGreetingOnly) return "Hello there! How may I help you today?";

    let out = null;
    out = handleMuseumInfo(original, s, lemmas) || out; if (out) return out;
    out = handleExhibitions(original, s, lemmas) || out; if (out) return out;
    out = handleSlamArt(original, s, lemmas) || out; if (out) return out;
    out = handleMapLocations(original, s, lemmas) || out; if (out) return out;
    out = handleGeneric(original, s, lemmas) || out; if (out) return out;

    return "I'm not sure I understand — could you try asking in a different way?";
}

function handleGeneric(raw, s, lemmas) {
    if (/\b(how are you|how's it going|how’re you)\b/.test(s)) return "I'm doing well! What would you like to know?";
    if (/\b(your name|what should i call you|do you have a name|call you)\b/.test(s)) return "I don’t have a proper name yet — you can call me SLAM Bot!";
    if (/\b(thanks|thank you|cheers)\b/.test(s)) return "You're welcome! Anything else you'd like to ask?";
    return null;
}

function handleMuseumInfo(raw, s, lemmas) {
    if ((s.includes('name') && s.includes('museum')) || /\b(what is the museum called|museum name)\b/.test(s))
        return museumInfo.name ? `We are called the ${museumInfo.name}.` : "We are the St. Louis Art Museum.";

    if ((s.includes('where') && (s.includes('museum') || s.includes('located'))) || s.includes('address'))
        return museumInfo.location ? `We are located at: ${museumInfo.location}.` : "Location information is not available right now.";

    if (s.includes('phone') || (s.includes('call') && s.includes('number')) || s.includes('tel'))
        return museumInfo.phone_number ? `You can call the museum at ${museumInfo.phone_number}.` : "Phone information not available.";

    if (s.includes('open') || s.includes('hours') || s.includes('closing') || s.includes('when')) {
        const weekdays = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
        for (const wd of weekdays) {
            if (s.includes(wd)) {
                const hrs = museumInfo.museum_hours && museumInfo.museum_hours[wd];
                return hrs ? `The museum is open on ${capitalize(wd)}: ${hrs}.` : `Hours for ${capitalize(wd)} are not available.`;
            }
        }
        if (s.includes('today')) {
            const d = resolveRelativeDay('today');
            const h = museumInfo.museum_hours && museumInfo.museum_hours[d];
            return h ? `Today (${capitalize(d)}) the museum hours are: ${h}.` : `Today's hours are not available.`;
        }
        if (s.includes('tomorrow')) {
            const d = resolveRelativeDay('tomorrow');
            const h = museumInfo.museum_hours && museumInfo.museum_hours[d];
            return h ? `Tomorrow (${capitalize(d)}) the museum hours will be: ${h}.` : `Tomorrow's hours are not available.`;
        }
        if (museumInfo.museum_hours) {
            const summary = Object.entries(museumInfo.museum_hours)
                .map(([k,v]) => `${capitalize(k)}: ${v}`).join('; ');
            return `Museum hours — ${summary}`;
        }
        return "Please ask about a specific day (e.g., 'What are the hours on Tuesday?').";
    }

    if (s.includes('parking') || s.includes('park'))
        return museumInfo.parking && museumInfo.parking.free ? museumInfo.parking.free : "Parking information not available.";

    return null;
}

function handleExhibitions(raw, s, lemmas) {
    const condA = (s.includes('exhibition') || s.includes('exhibitions')) && (s.includes('view'));
    const condB = s.includes('current') && (s.includes('exhibition') || s.includes('exhibitions'));
    if (condA || condB || s.includes("what's on view") || s.includes('whats on view') || s.includes('what is on view')) {
        const onView = (exhibitionsData || []).filter(ex => ex.on_view);
        if (!onView.length) return "No exhibitions are currently on view.";
        const names = onView.map(e => e.name).join(', ');
        return `Exhibitions currently on view: ${names}`;
    }

    if (fuseExhibitions && s.length > 2) {
        const results = fuseExhibitions.search(s).slice(0,5);
        if (results.length && results[0].score <= 0.6) {
            const ex = exhibitionsData.find(e => e.id === results[0].item.id);
            if (ex) {
                const detailKeywords = ['describe','description','curat','curator','collabor','start','end','date','gallery','where'];
                const askedDetail = detailKeywords.some(k => s.includes(k));

                if (askedDetail) {
                    if (s.includes('curat') || s.includes('curator')) return ex.curated_by || "Curator information not available.";
                    if (s.includes('collabor')) return ex.collaborators || "Collaborator information not available.";
                    if (s.includes('start') || s.includes('end') || s.includes('date'))
                        return `${ex.name} runs from ${ex.start_date || 'N/A'} to ${ex.end_date || 'N/A'}.`;
                    if (s.includes('gallery') || s.includes('where'))
                        return ex.gallery_numbers ? `This exhibition is in galleries: ${Array.isArray(ex.gallery_numbers) ? ex.gallery_numbers.join(', ') : ex.gallery_numbers}.` : "Gallery information not available.";
                    if (s.includes('describe') || s.includes('description'))
                        return ex.description || "Description not available.";
                }

                const short = `${ex.name} (${ex.start_date || 'N/A'} – ${ex.end_date || 'N/A'}).`;
                const options = " You can ask: 'Give me the description', 'Who curated it?', 'Which galleries?', or 'What are the start/end dates?'.";
                return short + options;
            }
        }
    }

    const idMatch = raw.match(/(EXH\d{3})/i);
    if (idMatch) {
        const ex = exhibitionsData.find(e => (e.id || '').toUpperCase() === idMatch[1].toUpperCase());
        if (ex) {
            const short = `${ex.name} (${ex.start_date || 'N/A'} – ${ex.end_date || 'N/A'}).`;
            const opts = " You can ask: 'Give me the description', 'Who curated it?', 'Which galleries?', or 'What are the start/end dates?'.";
            return short + opts;
        }
    }
    return null;
}

function handleSlamArt(raw, s, lemmas) {
    if (fuseArtByTitle && s.length > 2) {
        const r = fuseArtByTitle.search(s);
        if (r.length && r[0].score <= 0.55) {
            const art = slamArtData.find(a => a.id === r[0].item.id);
            if (art) {
                const detailKeywords = ['date','when','paint','who','artist','description','dimensions','provenance','image','url'];
                const askedDetail = detailKeywords.some(k => s.includes(k));

                if (askedDetail) {
                    if (s.includes('date') || s.includes('when') || s.includes('paint')) return art.date || "Date not available.";
                    if (s.includes('who') || s.includes('artist')) return art.artist || "Artist not available.";
                    if (s.includes('description')) return art.description || "Description not available.";
                    if (s.includes('dimensions')) return art.dimensions || "Dimensions not available.";
                    if (s.includes('provenance')) return art.provenance || "Provenance not available.";
                    if (s.includes('image') || s.includes('url')) return art.image_url || "Image URL not available.";
                }

                const short = `${art.title} — by ${art.artist || 'Unknown'}. Located in gallery ${art.gallery || 'N/A'}.`;
                const options = " You can ask: 'Who painted this?', 'When was it painted?', 'Give me the description', 'What are the dimensions?', or 'Show provenance'.";
                return short + options;
            }
        }
    }

    if (fuseArtByArtist && s.length > 2 && (s.includes('by ') || s.includes('works by') || s.includes('show me') || s.includes('pieces by') || s.includes('paintings by') || s.includes('artist'))) {
        const r = fuseArtByArtist.search(s);
        if (r.length && r[0].score <= 0.55) {
            const artistName = r[0].item.artist;
            const pieces = slamArtData.filter(a => (a.artist || '').toLowerCase() === artistName.toLowerCase());
            if (pieces.length)
                return `Works by ${artistName}: ${pieces.map(p => `${p.title} (gallery ${p.gallery || 'N/A'})`).join('; ')}`;
        }
    }

    if (s.includes('gallery')) {
        const num = s.match(/\b(\d{1,3})\b/);
        if (num) {
            const n = parseInt(num[1], 10);
            const items = slamArtData.filter(a => parseInt(a.gallery,10) === n);
            if (items.length)
                return `In gallery ${n} you can find: ${items.map(i => `${i.title} by ${i.artist}`).join('; ')}`;
            return `I couldn't find works listed for gallery ${n}.`;
        }
    }
    return null;
}

function handleMapLocations(raw, s, lemmas) {
    if (fuseMapCategories && s.length > 2 && (s.includes('where is') || s.includes('where') || s.includes('located') || s.includes('find'))) {
        const r = fuseMapCategories.search(s);
        if (r.length && r[0].score <= 0.6) {
            const a = r[0].item;
            return `${a.category} is on floor ${a.floor} in galleries ${Array.isArray(a.numbers) ? a.numbers.join(', ') : a.numbers}.`;
        }
    }

    const galleryNum = s.match(/\b(\d{1,3})\b/);
    if (galleryNum && s.includes('gallery')) {
        const n = galleryNum[1];
        for (const floor of (mapLocationsData || [])) {
            for (const g of (floor.galleries || [])) {
                if ((g.numbers || []).map(String).includes(String(n)))
                    return `Gallery ${n} is part of the ${g.category} section on floor ${floor.floor}.`;
            }
        }
        return `I couldn't find gallery ${n} in the map data.`;
    }

    if (s.includes('restroom') || s.includes('toilet') || s.includes('bathroom')) {
        const floorMatch = s.match(/floor\s*(\d)/);
        if (floorMatch) {
            const fl = String(floorMatch[1]);
            const floorObj = (mapLocationsData || []).find(f => String(f.floor) === fl);
            if (floorObj && floorObj.restrooms && floorObj.restrooms.length) {
                const locMap = {};
                for (const r of floorObj.restrooms) {
                    const loc = r.location || 'Unknown location';
                    const type = r.type || 'restroom';
                    if (!locMap[loc]) locMap[loc] = new Set();
                    locMap[loc].add(type);
                }
                const lines = Object.entries(locMap).map(([loc,types]) =>
                    `- ${loc}: ${Array.from(types).join(', ')}`
                );

                return `Restrooms on floor ${fl}:\n${lines.join('\n')}`;
            }
            return `I couldn't find restrooms listed for floor ${fl}.`;
        } else {
            const summaries = [];
            for (const f of (mapLocationsData || [])) {
                if (f.restrooms && f.restrooms.length) {
                    const locMap = {};
                    for (const r of f.restrooms) {
                        const loc = r.location || 'Unknown location';
                        const type = r.type || 'restroom';
                        if (!locMap[loc]) locMap[loc] = new Set();
                        locMap[loc].add(type);
                    }
                    const pairs = Object.entries(locMap).map(([loc,types]) => `${loc}: ${Array.from(types).join(', ')}`);
                    summaries.push(`Floor ${f.floor}: ${pairs.join('; ')}`);
                }
            }
            if (summaries.length) return `Restrooms — ${summaries.join(' | ')}`;
            return "Restroom information is not available.";
        }
    }

    if ((s.includes('coat') && s.includes('check')) || s.includes('coat-check')) {
        const all = [];
        for (const f of (mapLocationsData || []))
            if (f.coat_checks && f.coat_checks.length)
                all.push(`Floor ${f.floor}: ${f.coat_checks.join(', ')}`);
        if (all.length) return `Coat checks — ${all.join(' | ')}`;
        return "Coat check information not available.";
    }

    if (s.includes('elevator')) {
        const matches = [];
        for (const f of (mapLocationsData || []))
            if (f.elevators && f.elevators.length)
                matches.push(`Floor ${f.floor}: ${f.elevators.join(', ')}`);
        if (matches.length) return `Elevators — ${matches.join(' | ')}`;
        return "Elevator information not available.";
    }

    if (s.includes('stair')) {
        const matches = [];
        for (const f of (mapLocationsData || []))
            if (f.stairs && f.stairs.length)
                matches.push(`Floor ${f.floor}: ${f.stairs.join(', ')}`);
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
