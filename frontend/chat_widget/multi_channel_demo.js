/**
 * multi_channel_demo.js
 *
 * Drives all three chat panels on the multi-channel demo page. Each
 * panel is visually skinned differently (website / WhatsApp-style /
 * Messenger-style) but they all call the exact same backend endpoint
 * (/chat) — this file is intentionally generic per-panel logic, to
 * make that "same API, different front-end" point obvious in the code
 * itself, not just visually.
 *
 * Each panel gets its OWN session_id (set via data-session on the
 * .channel-card element), so the three demo conversations are
 * completely independent of each other, even though they're all
 * hitting the same agent.
 */

const API_BASE = "http://127.0.0.1:8000";

function initChannel(cardEl) {
  const sessionId = cardEl.dataset.session;
  const messagesEl = cardEl.querySelector(".messages");
  const inputEl = cardEl.querySelector("input");
  const sendBtn = cardEl.querySelector("button");

  function appendMessage(text, className) {
    const div = document.createElement("div");
    div.className = `bubble ${className}`;
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

      if (!response.ok) throw new Error(`Server returned ${response.status}`);

      const data = await response.json();
      loadingEl.remove();
      appendMessage(data.reply, "agent");
    } catch (err) {
      loadingEl.remove();
      appendMessage("Sorry, something went wrong reaching the assistant.", "error");
      console.error(`[${sessionId}] chat request failed:`, err);
    } finally {
      inputEl.disabled = false;
      sendBtn.disabled = false;
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMessage();
  });

  appendMessage("Hi! Ask me about products, orders, shipping, or returns.", "agent");
}

// Initialize every .channel-card on the page — adding a fourth demo
// channel later is just adding one more .channel-card element with
// its own data-session; no JS changes needed.
document.querySelectorAll(".channel-card").forEach(initChannel);
