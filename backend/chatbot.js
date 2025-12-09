let museumInfo = {};
let exhibitionsData = [];
let slamArtData = [];
let mapLocationsData = [];

window.__museumLoaded = false;

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

        window.__museumLoaded = true;
    })
    .catch(err => {
        console.error("Error loading JSON files:", err);
        window.__museumLoaded = true;
    });
}

loadJSONData();


function processInput(input) {
    if (!input || typeof input !== "string") {
        return "I'm sorry, I didn't quite get that. Could you try asking again?";
    }

    input = input.toLowerCase();

    return (
        handleGeneric(input) ||
        handleMuseumInfo(input) ||
        handleExhibitions(input) ||
        handleSlamArt(input) ||
        handleMapLocations(input) ||
        "I'm not sure I understand — could you try asking in a different way?"
    );
}


function handleGeneric(input) {
    if (/\b(hello|hi|hey)\b/.test(input)) {
        return "Hello there! How may I help you today?";
    }

    if (input.includes("how are you")) {
        return "I'm doing well! What would you like to know?";
    }

    if (input.includes("your name")) {
        return "I don’t have a name yet — but I'd love suggestions!";
    }

    return null;
}


function handleMuseumInfo(input) {
    if (input.includes("name") && input.includes("museum")) {
        return museumInfo.name
            ? `We are called the ${museumInfo.name}.`
            : "We are the St. Louis Art Museum.";
    }

    if (input.includes("tuesday") || input.includes("hours")) {
        return museumInfo.museum_hours?.tuesday
            ? `We are open on Tuesdays from ${museumInfo.museum_hours.tuesday}.`
            : "Please check the museum hours.";
    }

    if (input.includes("free parking") || input.includes("parking")) {
        return museumInfo.parking?.free || "Parking information is not available right now.";
    }

    if (input.includes("location") || input.includes("address")) {
        return museumInfo.location
            ? `Our address is: ${museumInfo.location}`
            : "Location information not available.";
    }

    return null;
}


function handleExhibitions(input) {
    if (input.includes("exhibitions") && input.includes("view")) {
        const onView = exhibitionsData.filter(ex => ex.on_view);
        if (onView.length === 0) return "No exhibitions are currently on view.";

        const names = onView.map(ex => ex.name).join(", ");
        return `Exhibitions currently on view: ${names}`;
    }

    for (const ex of exhibitionsData) {
        const lowerName = ex.name.toLowerCase();
        if (input.includes(ex.id.toLowerCase()) || input.includes(lowerName)) {
            return `${ex.name} runs from ${ex.start_date} to ${ex.end_date}. ${ex.description}`;
        }
    }

    return null;
}


function handleSlamArt(input) {
    for (const art of slamArtData) {
        const titleLower = art.title.toLowerCase();
        if (input.includes(titleLower)) {
            return `${art.title} by ${art.artist} (${art.date}). It's located in gallery ${art.gallery}.`;
        }
    }

    if (input.includes("gallery")) {
        const numMatch = input.match(/\b\d+\b/);
        if (numMatch) {
            const num = numMatch[0];
            const items = slamArtData.filter(a => a.gallery == num);
            if (items.length > 0) {
                return `In gallery ${num}, you can find: ${items.map(a => a.title).join(", ")}.`;
            }
        }
    }

    return null;
}


function handleMapLocations(input) {
    if (input.includes("where") || input.includes("location")) {
        for (const floor of mapLocationsData) {
            for (const g of floor.galleries) {
                const categoryLower = g.category.toLowerCase();
                if (input.includes(categoryLower)) {
                    return `${g.category} is located on floor ${floor.floor} in galleries ${g.numbers.join(", ")}.`;
                }
            }
        }
    }

    if (input.includes("gallery")) {
        const numMatch = input.match(/\b\d+\b/);
        if (numMatch) {
            const num = numMatch[0];
            for (const floor of mapLocationsData) {
                for (const g of floor.galleries) {
                    if (g.numbers.includes(num)) {
                        return `Gallery ${num} is part of the ${g.category} section on floor ${floor.floor}.`;
                    }
                }
            }
        }
    }

    return null;
}

window.processInput = processInput;
window.museumInfo = museumInfo;
