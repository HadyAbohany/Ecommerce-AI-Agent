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
 *
 * Two ways to trigger a message on a panel:
 *   - typing into that panel's own input and hitting Send/Enter
 *   - the shared "Ask all three" bar above the panels, which fires
 *     the exact same text at all three sessions at once (see
 *     wireAskAll() at the bottom) — this is the "same backend, three
 *     skins" demo moment.
 */

const API_BASE = "http://127.0.0.1:8000";

// Registry of { sessionId, sendMessage(text) } so the shared
// "ask all three" bar can trigger every panel without each panel
// needing to know the others exist.
const channelSenders = [];

function renderMarkdown(text) {
  // marked is loaded from a CDN <script> tag in the HTML. Fall back
  // to plain text if it hasn't loaded for some reason, so a slow/
  // blocked CDN never breaks the chat.
  if (window.marked && typeof window.marked.parse === "function") {
    return window.marked.parse(text);
  }
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function initChannel(cardEl) {
  const sessionId = cardEl.dataset.session;
  const messagesEl = cardEl.querySelector(".messages");
  const inputEl = cardEl.querySelector("input");
  const sendBtn = cardEl.querySelector("button");

  function appendMessage(text, className, { markdown = false } = {}) {
    const div = document.createElement("div");
    div.className = `bubble ${className}`;
    if (markdown) {
      div.innerHTML = renderMarkdown(text);
    } else {
      div.textContent = text;
    }
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function appendTypingIndicator() {
    const div = document.createElement("div");
    div.className = "bubble loading";
    div.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  async function sendMessage(presetText) {
    const text = (presetText !== undefined ? presetText : inputEl.value).trim();
    if (!text) return;

    sendBtn.classList.remove("bounce");
    void sendBtn.offsetWidth; // restart animation if clicked again quickly
    sendBtn.classList.add("bounce");

    if (presetText !== undefined) {
      cardEl.classList.remove("pulse");
      void cardEl.offsetWidth;
      cardEl.classList.add("pulse");
    }

    appendMessage(text, "user");
    if (presetText === undefined) inputEl.value = "";
    inputEl.disabled = true;
    sendBtn.disabled = true;

    const loadingEl = appendTypingIndicator();

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });

      if (!response.ok) throw new Error(`Server returned ${response.status}`);

      const data = await response.json();
      loadingEl.remove();
      appendMessage(data.reply, "agent", { markdown: true });
    } catch (err) {
      loadingEl.remove();
      appendMessage("Sorry, something went wrong reaching the assistant.", "error");
      console.error(`[${sessionId}] chat request failed:`, err);
    } finally {
      inputEl.disabled = false;
      sendBtn.disabled = false;
    }
  }

  sendBtn.addEventListener("click", () => sendMessage());
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMessage();
  });

  appendMessage("Hi! Ask me about products, orders, shipping, or returns.", "agent");

  channelSenders.push({ sessionId, sendMessage });
}

// Wires up the shared "Ask all three" bar: one input + button that
// fires the identical message at every registered channel at once.
function wireAskAll() {
  const askAllInput = document.getElementById("ask-all-input");
  const askAllBtn = document.getElementById("ask-all-btn");
  if (!askAllInput || !askAllBtn) return;

  function askAll() {
    const text = askAllInput.value.trim();
    if (!text) return;
    askAllInput.value = "";
    askAllBtn.classList.remove("bounce");
    void askAllBtn.offsetWidth;
    askAllBtn.classList.add("bounce");
    channelSenders.forEach(({ sendMessage }) => sendMessage(text));
  }

  askAllBtn.addEventListener("click", askAll);
  askAllInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") askAll();
  });
}

// Initialize every .channel-card on the page — adding a fourth demo
// channel later is just adding one more .channel-card element with
// its own data-session; no JS changes needed. It'll automatically
// pick up "Ask all three" too, since that just fans out to whatever
// is in channelSenders.
document.querySelectorAll(".channel-card").forEach(initChannel);
wireAskAll();