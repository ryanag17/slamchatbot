let museumInfo = {};
let greeting = "Hello! I’m your friendly SLAM chatbot. How can I assist you today?";

// Load the JSON data for the museum
function loadJSONData() {
    fetch('./data/museum_info.json')
        .then(response => response.json())
        .then(data => {
            museumInfo = data;
            initializeChat();
        })
        .catch(error => console.error("Error loading museum_info.json:", error));
}

// Initialize chat interface after JSON data is loaded
function initializeChat() {
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

// Allow sending messages by pressing Enter
document.getElementById("user-input").addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
        let userInput = document.getElementById("user-input").value;
        if (userInput.trim() !== "") {
            userMessage(userInput);  // Display the user's message
            botReply(userInput);     // Let the bot respond
        }
        document.getElementById("user-input").value = ""; // Clear the input field
    }
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
    let response = processInput(input);  // Process the user input and generate response
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

// Function to process user input and provide relevant response
function processInput(input) {
    input = input.toLowerCase();

    if (input.includes("name of the museum")) {
        return `We are called the ${museumInfo.name}.`;
    }
    else if (input.includes("open on tuesday")) {
        return `The museum is open on Tuesdays from ${museumInfo.museum_hours.tuesday}.`;
    }
    else if (input.includes("free parking")) {
        return museumInfo.parking.free;
    }
    else if (input.includes("location")) {
        return `We are located at: ${museumInfo.location}.`;
    }
    else {
        return "I'm sorry, I didn't understand that. Can you please rephrase your question?";
    }
}

// Scroll the chat to the bottom when new messages are added
function scrollChatToBottom() {
    let chatArea = document.getElementById("chat-area");
    chatArea.scrollTop = chatArea.scrollHeight;
}

// Add a fade-in effect for new messages
function animateMessage() {
    const newMessage = document.querySelector('.chat-message:last-child');
    newMessage.classList.add('fade-in');
}

// Load JSON data on page load
window.onload = loadJSONData;
