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
 * .channel-card element), so typing directly into one panel's input
 * keeps that panel's conversation independent of the others.
 *
 * Two ways to trigger a message on a panel:
 *   - typing into that panel's own input and hitting Send/Enter
 *     (makes its own /chat call, using that panel's own session_id)
 *   - the shared "Ask all three" bar above the panels — this makes
 *     ONE /chat call (under a separate shared session_id, so it never
 *     mixes into any panel's individual conversation history) and then
 *     mirrors that single question + single answer into all three
 *     panels at once. This guarantees the three panels show the exact
 *     same reply, and costs the same API quota as asking one question
 *     — not three — which matters given Gemini's free-tier daily limit.
 */

const API_BASE = "http://127.0.0.1:8000";
const ASK_ALL_SESSION_ID = "demo-ask-all-shared";

// Registry of per-panel display helpers so the shared "ask all three"
// bar can render into every panel without making its own network call
// per panel, and without each panel needing to know the others exist.
const channelPanels = [];

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

  function pulseCard() {
    cardEl.classList.remove("pulse");
    void cardEl.offsetWidth; // restart animation if triggered again quickly
    cardEl.classList.add("pulse");
  }

  function setInputBusy(busy) {
    inputEl.disabled = busy;
    sendBtn.disabled = busy;
  }

  // Normal path: this panel's own input/send button, hitting /chat
  // directly under this panel's own session_id.
  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text) return;

    sendBtn.classList.remove("bounce");
    void sendBtn.offsetWidth;
    sendBtn.classList.add("bounce");

    appendMessage(text, "user");
    inputEl.value = "";
    setInputBusy(true);

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
      setInputBusy(false);
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMessage();
  });

  appendMessage("Hi! Ask me about products, orders, shipping, or returns.", "agent");

  // Exposed for the shared "Ask all three" bar — no network call here,
  // just rendering into this panel's own message list.
  channelPanels.push({
    sessionId,
    showUserMessage: (text) => {
      pulseCard();
      appendMessage(text, "user");
    },
    showTyping: () => appendTypingIndicator(),
    showAgentReply: (loadingEl, replyText) => {
      loadingEl.remove();
      appendMessage(replyText, "agent", { markdown: true });
    },
    showError: (loadingEl) => {
      loadingEl.remove();
      appendMessage("Sorry, something went wrong reaching the assistant.", "error");
    },
  });
}

// Wires up the shared "Ask all three" bar. Makes exactly ONE /chat
// call (under a dedicated shared session_id, separate from any
// individual panel's session) and mirrors that single question and
// single answer into all three panels — same agent, same answer,
// three skins, one API call.
function wireAskAll() {
  const askAllInput = document.getElementById("ask-all-input");
  const askAllBtn = document.getElementById("ask-all-btn");
  if (!askAllInput || !askAllBtn) return;

  async function askAll() {
    const text = askAllInput.value.trim();
    if (!text) return;

    askAllInput.value = "";
    askAllInput.disabled = true;
    askAllBtn.disabled = true;
    askAllBtn.classList.remove("bounce");
    void askAllBtn.offsetWidth;
    askAllBtn.classList.add("bounce");

    // Show the question + a typing indicator in every panel immediately,
    // before the single network call even resolves.
    const loadingElsByPanel = channelPanels.map((panel) => {
      panel.showUserMessage(text);
      return panel.showTyping();
    });

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: ASK_ALL_SESSION_ID }),
      });

      if (!response.ok) throw new Error(`Server returned ${response.status}`);

      const data = await response.json();
      channelPanels.forEach((panel, i) => panel.showAgentReply(loadingElsByPanel[i], data.reply));
    } catch (err) {
      channelPanels.forEach((panel, i) => panel.showError(loadingElsByPanel[i]));
      console.error("[ask-all] chat request failed:", err);
    } finally {
      askAllInput.disabled = false;
      askAllBtn.disabled = false;
    }
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
// is in channelPanels.
document.querySelectorAll(".channel-card").forEach(initChannel);
wireAskAll();