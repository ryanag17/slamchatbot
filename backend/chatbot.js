/* chatbot.js
   Loads museum_info.json and provides processInput()
*/

let museumInfo = {};
window.__museumLoaded = false;

// Load museum data (YOUR ORIGINAL FUNCTION)
function loadJSONData() {
    fetch('../data/museum_info.json')   // FIXED PATH (same as your original)
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
            window.__museumLoaded = true; // let chat run anyway
        });
}

// Main chatbot logic (YOUR ORIGINAL LOGIC)
function processInput(input) {
    if (!input || typeof input !== 'string')
        return "I'm sorry, I didn't understand that. Could you please rephrase?";

    input = input.toLowerCase();

    if (input.includes("hello")) return "Hello there! How may I help you today?";
    if (input.includes("how are you")) return "I’m doing well! What would you like to know?";
    if (input.includes("what is your name")) return "I don’t have a name yet — but I'd love suggestions!";
    if (input.includes("name of the museum")) return museumInfo.name ? `We are called the ${museumInfo.name}.` : "We are the St. Louis Art Museum.";
    if (input.includes("tuesday")) return museumInfo.museum_hours?.tuesday ? `We are open on Tuesdays from ${museumInfo.museum_hours.tuesday}.` : "Please check the museum hours.";
    if (input.includes("free parking")) return museumInfo.parking?.free || "Parking information is not available right now.";
    if (input.includes("location") || input.includes("address")) return museumInfo.location ? `Our address is: ${museumInfo.location}` : "Location information not available.";

    return "I'm not sure I understand — could you try asking in a different way?";
}

// Start loading JSON
loadJSONData();

// Expose functions globally
window.processInput = processInput;
window.museumInfo = museumInfo;
