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

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function appendMessage(text, className) {
  const wrap = document.createElement("div");
  wrap.className = `msg-wrap ${className}`;

  const bubble = document.createElement("div");
  bubble.className = `msg ${className}`;

  if (className === "agent" && typeof marked !== "undefined") {
    // Agent replies are markdown (bold labels, bullet lists, etc.) — render
    // them properly instead of dumping raw **asterisks** to the page.
    bubble.innerHTML = marked.parse(text);
  } else {
    bubble.textContent = text;
  }

  wrap.appendChild(bubble);

  if (className === "user" || className === "agent") {
    const time = document.createElement("div");
    time.className = "msg-time";
    time.textContent = formatTime(new Date());
    wrap.appendChild(time);
  }

  messagesEl.appendChild(wrap);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return wrap;
}

function appendTypingIndicator() {
  const wrap = document.createElement("div");
  wrap.className = "msg-wrap loading";

  const bubble = document.createElement("div");
  bubble.className = "msg loading";
  bubble.innerHTML =
    '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';

  wrap.appendChild(bubble);
  messagesEl.appendChild(wrap);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return wrap;
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;

  appendMessage(text, "user");
  inputEl.value = "";
  inputEl.disabled = true;
  sendBtn.disabled = true;

  const loadingEl = appendTypingIndicator();

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
    sendBtn.disabled = inputEl.value.trim().length === 0;
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
inputEl.addEventListener("input", () => {
  sendBtn.disabled = inputEl.value.trim().length === 0;
});
resetBtn.addEventListener("click", resetConversation);

// Send button starts disabled since the input starts empty.
sendBtn.disabled = true;

// Initial greeting
appendMessage("Hi! Ask me about products, orders, shipping, or returns.", "agent");
