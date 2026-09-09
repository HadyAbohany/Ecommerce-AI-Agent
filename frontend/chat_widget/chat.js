/**
 * chat.js
 *
 * Talks to the FastAPI /chat and /chat/reset endpoints (Step 8).
 * This is a plain HTTP client — same as curl — proving the
 * "channel-agnostic API" design actually works from a browser.
 */

const API_BASE = "http://127.0.0.1:8000";

// One session_id per page load, reused for every message sent from
// this tab — this is what makes the agent's conversation memory
// (Step 7) actually work across multiple messages in one visit.
const sessionId = crypto.randomUUID();

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const resetBtn = document.getElementById("reset-btn");

function appendMessage(text, className) {
  const div = document.createElement("div");
  div.className = `msg ${className}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;

  appendMessage(text, "user");
  inputEl.value = "";
  inputEl.disabled = true;
  sendBtn.disabled = true;

  const loadingEl = appendMessage("...", "loading");

  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId }),
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const data = await response.json();
    loadingEl.remove();
    appendMessage(data.reply, "agent");
  } catch (err) {
    loadingEl.remove();
    appendMessage(
      "Sorry, something went wrong reaching the assistant. Please try again.",
      "error"
    );
    console.error("Chat request failed:", err);
  } finally {
    inputEl.disabled = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

async function resetConversation() {
  try {
    await fetch(`${API_BASE}/chat/reset?session_id=${sessionId}`, {
      method: "POST",
    });
  } catch (err) {
    console.error("Reset request failed:", err);
  }
  messagesEl.innerHTML = "";
  appendMessage("Conversation reset. How can I help you?", "agent");
}

sendBtn.addEventListener("click", sendMessage);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendMessage();
});
resetBtn.addEventListener("click", resetConversation);

// Initial greeting
appendMessage("Hi! Ask me about products, orders, shipping, or returns.", "agent");
