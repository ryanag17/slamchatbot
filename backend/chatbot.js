// Define variables to store the JSON data
let museumInfo = {};
let slamArt = [];
let mapLocations = [];
let exhibitions = [];

// Example of initial friendly greeting
let greeting = "Hello! I’m your friendly SLAM chatbot. How can I assist you today?";

// Fetch the JSON files
function loadJSONData() {
    fetch('./data/museum_info.json')  
        .then(response => response.json())
        .then(data => {
            museumInfo = data; 
            initializeChat();
        })
        .catch(error => console.error("Error loading museum_info.json:", error));

    fetch('./data/slam_art.json') 
        .then(response => response.json())
        .then(data => slamArt = data)
        .catch(error => console.error("Error loading slam_art.json:", error));

    fetch('./data/map_locations.json')
        .then(response => response.json())
        .then(data => mapLocations = data)
        .catch(error => console.error("Error loading map_locations.json:", error));

    fetch('./data/exhibitions.json')
        .then(response => response.json())
        .then(data => exhibitions = data)
        .catch(error => console.error("Error loading exhibitions.json:", error));
}

// Initialize chat interface after JSON data is loaded
function initializeChat() {
    // Hide the welcome message and show the chat window
    document.getElementById("welcome-container").classList.add("hidden");
    document.getElementById("chat-window").classList.remove("hidden");

    // Show the greeting message
    document.getElementById("chat-area").innerHTML = `
        <div class="chat-message bot-message">
            <img src="bot-profile-pic.jpg" class="profile-pic" alt="Bot">
            <div class="message-bubble bot-bubble">
                ${greeting}
                <div class="timestamp">${new Date().toLocaleTimeString()}</div>
            </div>
        </div>
    `;
}

// Event listener for send button
document.getElementById("send-btn").addEventListener("click", function() {
    let userInput = document.getElementById("user-input").value;
    if (userInput.trim() !== "") {
        userMessage(userInput);  // Display the user's message
        botReply(userInput);     // Let the bot respond
    }
    document.getElementById("user-input").value = ""; // Clear the input field
    document.getElementById("chat-window").classList.remove("hidden"); // Show the chat window
});

// Function to handle user messages
function userMessage(message) {
    let timestamp = new Date().toLocaleTimeString();
    let messageHtml = `
        <div class="chat-message user-message">
            <img src="user-profile-pic.jpg" class="profile-pic" alt="User">
            <div class="message-bubble user-bubble">
                ${message}
                <div class="timestamp">${timestamp}</div>
            </div>
        </div>
    `;
    document.getElementById("chat-area").innerHTML += messageHtml;
    scrollChatToBottom();
    animateMessage();
}

// Function to handle bot replies
function botReply(input) {
    let response = processInput(input);
    let timestamp = new Date().toLocaleTimeString();
    let messageHtml = `
        <div class="chat-message bot-message">
            <img src="bot-profile-pic.jpg" class="profile-pic" alt="Bot">
            <div class="message-bubble bot-bubble">
                ${response}
                <div class="timestamp">${timestamp}</div>
            </div>
        </div>
    `;
    document.getElementById("chat-area").innerHTML += messageHtml;
    scrollChatToBottom();
    animateMessage();
}

// Function to process input and provide relevant response
function processInput(input) {
    input = input.toLowerCase();

    // Simple responses to greetings
    if (input.includes("hello") || input.includes("hi") || input.includes("hey")) {
        return "Hello! How can I assist you today?";
    }
    // Respond to questions about the museum's hours
    else if (input.includes("hours") || input.includes("open")) {
        return getMuseumHours();
    } else if (input.includes("location")) {
        return museumInfo.location_description;
    } else if (input.includes("art") || input.includes("painting")) {
        return getArtDetails(input);
    } else if (input.includes("exhibition")) {
        return getExhibitionDetails(input);
    } else if (input.includes("galleries") || input.includes("floor")) {
        return getFloorLocations(input);
    } else {
        return "I'm sorry, I didn't understand that. Can you please rephrase your question?";
    }
}

// Function to get the museum hours in a friendly way
function getMuseumHours() {
    let hours = museumInfo.museum_hours;
    return `The museum is open:
    - Tuesday to Thursday: ${hours.tuesday}
    - Friday: ${hours.friday}
    - Saturday and Sunday: ${hours.saturday}
    - Monday: Closed`;
}

// Function to fetch art details based on title or artist
function getArtDetails(input) {
    let artPiece = slamArt.find(art => art.title.toLowerCase().includes(input) || art.artist.toLowerCase().includes(input));
    if (artPiece) {
        return `You can find "${artPiece.title}" by ${artPiece.artist} in Gallery ${artPiece.gallery}.`;
    } else {
        return "Sorry, I couldn't find that artwork. Please try again.";
    }
}

// Function to fetch exhibition details
function getExhibitionDetails(input) {
    let exhibition = exhibitions.find(exh => exh.name.toLowerCase().includes(input));
    if (exhibition) {
        return `The "${exhibition.name}" exhibition is in Gallery(s) ${exhibition.gallery_numbers.join(", ")} from ${exhibition.start_date} to ${exhibition.end_date}.`;
    } else {
        return "I couldn't find that exhibition. Please try again.";
    }
}

// Function to fetch gallery locations based on floor input
function getFloorLocations(input) {
    let floorData = mapLocations.find(floor => input.includes(floor.floor));
    if (floorData) {
        return `The following galleries are on floor ${floorData.floor}: ${floorData.galleries.map(gallery => gallery.numbers.join(", ")).join(", ")}.`;
    } else {
        return "Sorry, I couldn't find any relevant floor information.";
    }
}

// Function to scroll chat to the bottom
function scrollChatToBottom() {
    let chatArea = document.getElementById("chat-area");
    chatArea.scrollTop = chatArea.scrollHeight;
}

// Function to add fade-in effect to messages
function animateMessage() {
    const newMessage = document.querySelector('.chat-message:last-child');
    newMessage.classList.add('fade-in');
}

// Load JSON data on page load
window.onload = loadJSONData;
