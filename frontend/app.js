async function askQuestion() {
    const question = document.getElementById("question").value;
    const response = await fetch("https://YOUR_RENDER_APP_URL/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: question })
    });
    const data = await response.json();
    document.getElementById("answer").innerText = data.answer;
}
