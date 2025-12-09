let museumInfo = {};
let greeting = "Hello! I’m your friendly SLAM chatbot. How can I assist you today?";

// Load museum JSON
function loadJSONData() {
    fetch('./data/museum_info.json')
        .then(r => r.json())
        .then(data => {
            museumInfo = data;
        })
        .catch(err => console.error("ERROR loading JSON:", err));
}

/* PROCESS INPUT — FIXED LOGIC */
function processInput(input) {
    input = input.toLowerCase();

    if (input.includes("hello")) return "Hello there! How may I help you today?";
    if (input.includes("how are you")) return "I am doing well. How may I assist you today?";
    if (input.includes("what is your name")) return "I don't have a name yet, but I’d love suggestions!";
    if (input.includes("name of the museum")) return `We are called the ${museumInfo.name}.`;

    if (input.includes("open on tuesday"))
        return `The museum is open on Tuesdays from ${museumInfo.museum_hours.tuesday}.`;

    if (input.includes("free parking"))
        return museumInfo.parking.free;

    if (input.includes("location"))
        return `We are located at: ${museumInfo.location}.`;

    return "I'm sorry, I didn't understand that. Can you please rephrase your question?";
}

window.onload = loadJSONData;
