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
            <div class="message-bubble bot-bubble">
                ${greeting}
                <div class="timestamp">${new Date().toLocaleString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true })}</div>
            </div>
        </div>
    `;
}

// Function to handle user messages
function userMessage(message) {
    let timestamp = new Date().toLocaleString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true });
    let messageHtml = `
        <div class="chat-message user-message">
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
    let timestamp = new Date().toLocaleString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true });
    let messageHtml = `
        <div class="chat-message bot-message">
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

// Process user input and provide a response
function processInput(input) {
    input = input.toLowerCase();

    if (input.includes("hello")) {
        return "Hello there! How may I help you today?";
    }
    else if (input.includes("how are you")) {
        return "I am doing well. How may I assist you today?";
    }
    else if (input.includes("what is your name")) {
        return "I don't have a name yet, but I am always interested to hear some ideas! Is there anything I could help with today?";
    }
    else if (input.includes("name of the museum")) {
        return `We are called the ${museumInfo.name}. Do you have any further questions?`;
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
    chatArea.scrollTop = chatArea.scrollHeight; // Ensures scrolling to the bottom of the chat container
}

// Modify bot and user messages to show at the bottom
function animateMessage() {
    const newMessage = document.querySelector('.chat-message:last-child');
    newMessage.classList.add('fade-in');
}

// Initialize chatbot interaction when user sends a message
document.getElementById("send-btn").addEventListener("click", function() {
    let userInput = document.getElementById("user-input").value;
    if (userInput.trim() !== "") {
        userMessage(userInput);
        botReply(userInput);
        document.getElementById("user-input").value = ""; 
        document.getElementById("welcome-container").style.display = 'none'; 
        document.getElementById("messages-container").style.display = 'block';
    }
});

document.getElementById("user-input").addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
        let userInput = document.getElementById("user-input").value;
        if (userInput.trim() !== "") {
            userMessage(userInput);
            botReply(userInput);
            document.getElementById("user-input").value = ""; 
            document.getElementById("welcome-container").style.display = 'none'; 
            document.getElementById("messages-container").style.display = 'block';
        }
    }
});

window.onload = loadJSONData;
