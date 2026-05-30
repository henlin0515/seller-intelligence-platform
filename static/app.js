const chatEl = document.getElementById("chat");
const form = document.getElementById("chatForm");
const input = document.getElementById("questionInput");
const sendBtn = document.getElementById("sendBtn");
const loadingBar = document.getElementById("loading");
const newChatBtn = document.getElementById("newChatBtn");
const saveChatBtn = document.getElementById("saveChatBtn");
const savedChatsBtn = document.getElementById("savedChatsBtn");
const sourceLibraryBtn = document.getElementById("sourceLibraryBtn");
const settingsBtn = document.getElementById("settingsBtn"); // optional legacy
const savedChatsPanel = document.getElementById("savedChatsPanel");
const sourceLibraryPanel = document.getElementById("sourceLibraryPanel");
const savedChatsList = document.getElementById("savedChatsList");
const savedChatsEmpty = document.getElementById("savedChatsEmpty");
const sourceLibraryList = document.getElementById("sourceLibraryList");
const sourceLibraryEmpty = document.getElementById("sourceLibraryEmpty");
const settingsModal = document.getElementById("settingsModal");

const STORAGE_SAVED = "shopee_saved_chats_v1";
const STORAGE_SOURCES = "shopee_source_library_v1";
const USER_FACING_ERROR =
  "Something went wrong while researching. Please try again or check the backend logs.";

let sessionMessages = [];
let sessionSources = [];
let loadingMessageEl = null;

function suggestionKeys() {
  return [
    "assistant.suggest1",
    "assistant.suggest2",
    "assistant.suggest3",
    "assistant.suggest4",
    "assistant.suggest5",
  ];
}

function i18n(key, fallback = "") {
  return window.SipI18n?.t(key, fallback) ?? fallback ?? key;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function initChat() {
  sessionMessages = [];
  const contextHint =
    localStorage.getItem("sip_seller_context_v1")
      ? `<p class="welcome-context">${escapeHtml(
          i18n(
            "assistant.contextHint",
            "Seller context is active — ask how to improve this shop's performance."
          )
        )}</p>`
      : "";
  const suggestions = suggestionKeys().map((k) => i18n(k));
  chatEl.innerHTML = `
    <div class="welcome-card">
      <div class="welcome-avatar" aria-hidden="true">✦</div>
      <h2>${escapeHtml(i18n("assistant.welcomeTitle", "How can I help you today?"))}</h2>
      <p>${i18n("assistant.welcomeBody", "Research Shopee programs, fees, eligibility, and policies.")}</p>
      ${contextHint}
      <div class="welcome-suggestions">
        ${suggestions
          .map(
            (s) =>
              `<button type="button" class="suggestion-chip" data-suggest="${escapeHtml(s)}">${escapeHtml(s)}</button>`
          )
          .join("")}
      </div>
    </div>
  `;
  chatEl.querySelectorAll(".suggestion-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      input.value = btn.dataset.suggest;
      form.requestSubmit();
    });
  });
  scrollChat();
}

function scrollChat() {
  const scroll = document.querySelector(".chat-scroll");
  if (scroll) scroll.scrollTop = scroll.scrollHeight;
}

function setLoading(on) {
  loadingBar.classList.toggle("hidden", !on);
  sendBtn.disabled = on;
  if (on) {
    showLoadingMessage();
  } else {
    removeLoadingMessage();
  }
}

function showLoadingMessage() {
  removeLoadingMessage();
  const row = document.createElement("div");
  row.className = "msg-row assistant loading-row";
  row.id = "loadingMessage";
  row.innerHTML = `
    <div class="msg-avatar">AI</div>
    <div class="msg-content">
      <div class="bubble">
        <div class="loading-dots" aria-hidden="true"><span></span><span></span><span></span></div>
        <span>${escapeHtml(i18n("assistant.loadingResearch", "Researching Seller Education sources…"))}</span>
      </div>
    </div>
  `;
  const welcome = chatEl.querySelector(".welcome-card");
  if (welcome) welcome.remove();
  chatEl.appendChild(row);
  loadingMessageEl = row;
  scrollChat();
}

function removeLoadingMessage() {
  const el = document.getElementById("loadingMessage");
  if (el) el.remove();
  loadingMessageEl = null;
}

function appendUserMessage(text) {
  const welcome = chatEl.querySelector(".welcome-card");
  if (welcome) welcome.remove();

  sessionMessages.push({ role: "user", text });

  const row = document.createElement("div");
  row.className = "msg-row user";
  row.innerHTML = `
    <div class="msg-content">
      <div class="bubble">${escapeHtml(text)}</div>
    </div>
    <div class="msg-avatar">You</div>
  `;
  chatEl.appendChild(row);
  scrollChat();
}

function buildSourceCards(sources) {
  if (!sources || sources.length === 0) {
    return '<p class="answer-text" style="color:var(--text-muted)">No sources found.</p>';
  }
  return `<div class="sources-grid">${sources
    .map(
      (s) => `
    <a class="source-card" href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">
      <span class="card-type">${escapeHtml(s.type || "article")}</span>
      <span class="title">${escapeHtml(s.title)}</span>
      <span class="url">${escapeHtml(s.url)}</span>
    </a>`
    )
    .join("")}</div>`;
}

function formatCopyText(data) {
  const lines = [`Answer:\n${data.answer || ""}`, "Key Points:"];
  (data.key_points || []).forEach((p) => lines.push(`- ${p}`));
  lines.push("Sources:");
  (data.sources || []).forEach((s) => lines.push(`- ${s.title} — ${s.url}`));
  return lines.join("\n");
}

function appendBotMessage(data) {
  const keyPointsHtml =
    data.key_points && data.key_points.length
      ? `<ul class="key-points">${data.key_points
          .map((p) => `<li>${escapeHtml(p)}</li>`)
          .join("")}</ul>`
      : '<p class="answer-text">—</p>';

  const copyText = data.formatted || formatCopyText(data);
  sessionMessages.push({ role: "assistant", data });

  mergeSourcesIntoLibrary(data.sources || []);

  const row = document.createElement("div");
  row.className = "msg-row assistant";
  row.innerHTML = `
    <div class="msg-avatar">AI</div>
    <div class="msg-content">
      <div class="bubble">
        <div class="section-title">Answer</div>
        <p class="answer-text">${escapeHtml(data.answer || "")}</p>
        <div class="section-title">Key Points</div>
        ${keyPointsHtml}
        <div class="section-title">Sources</div>
        ${buildSourceCards(data.sources)}
      </div>
      <div class="msg-actions">
        <button type="button" class="btn btn-ghost copy-btn">Copy answer</button>
      </div>
    </div>
  `;

  row.querySelector(".copy-btn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(copyText);
      const btn = row.querySelector(".copy-btn");
      const prev = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(() => {
        btn.textContent = prev;
      }, 1500);
    } catch {
      appendError("Could not copy to clipboard. Please select and copy manually.");
    }
  });

  chatEl.appendChild(row);
  scrollChat();
}

function appendError(friendlyMessage) {
  const row = document.createElement("div");
  row.className = "msg-row assistant";
  row.innerHTML = `
    <div class="msg-avatar">AI</div>
    <div class="msg-content">
      <div class="bubble error-bubble">
        <p class="error-title">Something went wrong</p>
        <p class="error-text">${escapeHtml(friendlyMessage)}</p>
      </div>
    </div>
  `;
  chatEl.appendChild(row);
  scrollChat();
}

function friendlyError(status) {
  if (status === 400) {
    return "Please enter a valid question about Shopee programs or policies.";
  }
  return USER_FACING_ERROR;
}

async function sendQuestion(question) {
  setLoading(true);
  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    let data = {};
    try {
      data = await res.json();
    } catch {
      data = {};
    }

    if (!res.ok) {
      throw { status: res.status };
    }
    appendBotMessage(data);
  } catch (err) {
    const status = err.status || 0;
    appendError(friendlyError(status));
  } finally {
    setLoading(false);
  }
}

function mergeSourcesIntoLibrary(sources) {
  const byUrl = new Map(sessionSources.map((s) => [s.url, s]));
  (sources || []).forEach((s) => {
    if (s.url) byUrl.set(s.url, s);
  });
  sessionSources = Array.from(byUrl.values());
  localStorage.setItem(STORAGE_SOURCES, JSON.stringify(sessionSources));
  renderSourceLibrary();
}

function renderSourceLibrary() {
  sourceLibraryList.innerHTML = "";
  if (sessionSources.length === 0) {
    sourceLibraryEmpty.classList.remove("hidden");
    return;
  }
  sourceLibraryEmpty.classList.add("hidden");
  sessionSources.forEach((s) => {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = s.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = s.title || s.url;
    li.appendChild(a);
    sourceLibraryList.appendChild(li);
  });
}

function loadSourceLibrary() {
  try {
    sessionSources = JSON.parse(localStorage.getItem(STORAGE_SOURCES) || "[]");
  } catch {
    sessionSources = [];
  }
  renderSourceLibrary();
}

function getSavedChats() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_SAVED) || "[]");
  } catch {
    return [];
  }
}

function saveCurrentChat() {
  if (sessionMessages.length === 0) {
    alert("Nothing to save yet. Ask a question first.");
    return;
  }
  const firstUser = sessionMessages.find((m) => m.role === "user");
  const title = firstUser ? firstUser.text.slice(0, 48) : "Chat";
  const saved = getSavedChats();
  saved.unshift({
    id: Date.now().toString(),
    title,
    messages: sessionMessages,
    savedAt: new Date().toISOString(),
  });
  localStorage.setItem(STORAGE_SAVED, JSON.stringify(saved.slice(0, 20)));
  renderSavedChats();
  alert("Chat saved.");
}

function renderSavedChats() {
  const saved = getSavedChats();
  savedChatsList.innerHTML = "";
  savedChatsEmpty.classList.toggle("hidden", saved.length > 0);
  saved.forEach((chat) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = chat.title;
    btn.title = new Date(chat.savedAt).toLocaleString();
    btn.addEventListener("click", () => loadSavedChat(chat));
    li.appendChild(btn);
    savedChatsList.appendChild(li);
  });
}

function loadSavedChat(chat) {
  initChat();
  sessionMessages = chat.messages || [];
  savedChatsPanel.classList.add("hidden");
  sessionMessages.forEach((m) => {
    if (m.role === "user") appendUserMessage(m.text);
    else if (m.role === "assistant" && m.data) appendBotMessage(m.data);
  });
}

function hideSidebarPanels() {
  savedChatsPanel.classList.add("hidden");
  sourceLibraryPanel.classList.add("hidden");
  document.querySelectorAll(".nav-item:not(.nav-main)").forEach((n) => n.classList.remove("active"));
}

function togglePanel(panel, btn) {
  const wasHidden = panel.classList.contains("hidden");
  hideSidebarPanels();
  if (wasHidden) {
    panel.classList.remove("hidden");
    btn.classList.add("active");
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  appendUserMessage(question);
  input.value = "";
  input.style.height = "auto";
  await sendQuestion(question);
});

newChatBtn.addEventListener("click", () => {
  hideSidebarPanels();
  initChat();
});

saveChatBtn.addEventListener("click", saveCurrentChat);

savedChatsBtn.addEventListener("click", () => {
  renderSavedChats();
  togglePanel(savedChatsPanel, savedChatsBtn);
});

sourceLibraryBtn.addEventListener("click", () => {
  renderSourceLibrary();
  togglePanel(sourceLibraryPanel, sourceLibraryBtn);
});

if (settingsBtn) {
  settingsBtn.addEventListener("click", () => {
    hideSidebarPanels();
    if (window.ShpPlatform?.navigate) window.ShpPlatform.navigate("settings");
    else settingsModal?.classList.remove("hidden");
  });
}

settingsModal.querySelectorAll("[data-close-modal]").forEach((el) => {
  el.addEventListener("click", () => settingsModal.classList.add("hidden"));
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
});

window.ShpChat = { refreshWelcome: initChat };

initChat();
loadSourceLibrary();

/* Navigation handled by platform.js */
