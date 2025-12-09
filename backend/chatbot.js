/* chatbot.js
   - loads museum_info.json into museumInfo
   - exposes processInput(input)
   - sets window.__museumLoaded = true when data available
*/

let museumInfo = {};
window.__museumLoaded = false; // flag used by chat.html

const greeting = "Hello! I’m your friendly SLAM chatbot. How can I assist you today?";

function loadJSONData() {
    fetch('./data/museum_info.json')
        .then(response => {
            if (!response.ok) throw new Error("Failed to load museum_info.json");
            return response.json();
        })
        .then(data => {
            museumInfo = data || {};
            window.__museumLoaded = true;
        })
        .catch(error => {
            console.error("Error loading museum_info.json:", error);
            // still mark loaded so chat doesn't hang forever (it will use fallback)
            window.__museumLoaded = true;
        });
}

// Processing logic (returns reply string synchronously)
function processInput(input) {
    if (!input || typeof input !== 'string') return "I'm sorry, I didn't understand that. Can you please rephrase your question?";
    input = input.toLowerCase();

    if (input.includes("hello")) {
        return "Hello there! How may I help you today?";
    }
    if (input.includes("how are you")) {
        return "I am doing well. How may I assist you today?";
    }
    if (input.includes("what is your name")) {
        return "I don't have a name yet, but I am always interested to hear some ideas!";
    }
    if (input.includes("name of the museum") || input.includes("what is the museum called") || input.includes("museum name")) {
        return museumInfo.name ? `We are called the ${museumInfo.name}.` : "We are the St. Louis Art Museum.";
    }
    if (input.includes("open on tuesday") || input.includes("tuesday hours") || input.includes("open tuesday")) {
        return museumInfo.museum_hours && museumInfo.museum_hours.tuesday ? `The museum is open on Tuesdays from ${museumInfo.museum_hours.tuesday}.` : "Please check the museum hours.";
    }
    if (input.includes("free parking") || input.includes("parking")) {
        return museumInfo.parking && museumInfo.parking.free ? museumInfo.parking.free : "Parking information is not available right now.";
    }
    if (input.includes("location") || input.includes("address")) {
        return museumInfo.location ? `We are located at: ${museumInfo.location}.` : "Location information is not available right now.";
    }

    return "I'm sorry, I didn't understand that. Can you please rephrase your question?";
}

// ensure data loads on script run
loadJSONData();

// expose processInput globally (already is), and museum info for debugging if needed
window.processInput = processInput;
window.museumInfo = museumInfo;
