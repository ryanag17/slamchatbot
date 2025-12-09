let museumInfo = {};
let greeting = "Hello! I’m your friendly SLAM chatbot. How can I assist you today?";

// Load museum data
function loadJSONData() {
    fetch('./data/museum_info.json')
        .then(response => response.json())
        .then(data => {
            museumInfo = data;
        })
        .catch(error => console.error("Error loading museum_info.json:", error));
}



// ------------------------------
// ADD USER MESSAGE
// ------------------------------
function userMessage(message) {
    let timestamp = new Date().toLocaleString('en-US', {
        month: '2-digit', day: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit', hour12: true
    });

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
}



// ------------------------------
// ADD BOT REPLY
// ------------------------------
function botReply(input) {
    let response = processInput(input);

    let timestamp = new Date().toLocaleString('en-US', {
        month: '2-digit', day: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit', hour12: true
    });

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
}



// ------------------------------
// PROCESS INPUT
// ------------------------------
function processInput(input) {
    input = input.toLowerCase();

    if (input.includes("hello")) {
        return "Hello there! How may I help you today?";
    }
    else if (input.includes("how are you")) {
        return "I am doing well. How may I assist you today?";
    }
    else if (input.includes("what is your name")) {
        return "I don't have a name yet, but I am always interested to hear some ideas!";
    }
    else if (input.includes("name of the museum")) {
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



// ------------------------------
// SCROLL TO BOTTOM
// ------------------------------
function scrollChatToBottom() {
    let chatArea = document.getElementById("chat-area");
    chatArea.scrollTop = chatArea.scrollHeight;
}



// LOAD JSON ON PAGE LOAD
loadJSONData();
