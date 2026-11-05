// Argus Studio Universal Web & Mobile Client

const state = {
  currentTab: "downloader",
  currentMetadata: null,
  selectedFormatType: "video",
  selectedQuality: "best",
  tasks: {},
  ws: null,
};

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  setupNavigation();
  setupNetworkMonitoring();
  initWebSocket();
  loadSettings();
  loadLibrary();
  loadQueue();
});

// Network Connection Monitoring (Offline Supervisor)
function setupNetworkMonitoring() {
  const offlineBanner = document.getElementById("offline-banner");
  function updateOnlineStatus() {
    if (!navigator.onLine) {
      if (offlineBanner) offlineBanner.style.display = "flex";
      const fetchBtn = document.getElementById("fetch-btn");
      if (fetchBtn) fetchBtn.disabled = true;
    } else {
      if (offlineBanner) offlineBanner.style.display = "none";
      const fetchBtn = document.getElementById("fetch-btn");
      if (fetchBtn) fetchBtn.disabled = false;
    }
  }
  window.addEventListener("online", updateOnlineStatus);
  window.addEventListener("offline", updateOnlineStatus);
  updateOnlineStatus();
}

// Navigation
function setupNavigation() {
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      showTab(tab);
    });
  });
}

function showTab(tabKey) {
  state.currentTab = tabKey;
  document.querySelectorAll(".nav-item").forEach(b => {
    b.classList.toggle("active", b.dataset.tab === tabKey);
  });
  document.querySelectorAll(".view-panel").forEach(p => {
    p.classList.toggle("active", p.id === `view-${tabKey}`);
  });

  const titles = {
    downloader: "Media Downloader",
    queue: "Download Queue",
    library: "Media Library",
    settings: "Settings",
  };
  document.getElementById("top-title").innerText = titles[tabKey] || "Argus Studio";

  if (tabKey === "queue") loadQueue();
  if (tabKey === "library") loadLibrary();
  if (tabKey === "settings") loadSettings();
}

// WebSocket Connection
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/api/ws`;

  state.ws = new WebSocket(wsUrl);

  state.ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "init") {
        data.tasks.forEach(t => { state.tasks[t.id] = t; });
        renderQueue();
      } else if (data.type === "task_updated") {
        state.tasks[data.task.id] = data.task;
        renderQueue();
      } else if (data.type === "task_completed") {
        state.tasks[data.task.id] = data.task;
        renderQueue();
        loadLibrary();
      }
    } catch (e) {
      console.error("WS Parse error", e);
    }
  };

  state.ws.onclose = () => {
    setTimeout(initWebSocket, 2500);
  };
}

// Load Settings
async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    if (!res.ok) return;
    const data = await res.json();
    if (data.max_concurrent !== undefined) {
      const el = document.getElementById("setting-max-concurrent");
      if (el) el.value = data.max_concurrent.toString();
    }
    if (data.default_quality !== undefined) {
      const el = document.getElementById("setting-default-quality");
      if (el) el.value = data.default_quality;
    }
    if (data.speed_limit !== undefined) {
      const el = document.getElementById("setting-speed-limit");
      if (el) el.value = data.speed_limit;
    }
    if (data.embed_metadata !== undefined) {
      const el = document.getElementById("setting-embed-meta");
      if (el) el.checked = Boolean(data.embed_metadata);
    }
  } catch (e) {
    console.error("Error loading settings", e);
  }
}

// Save Settings
async function saveSettings() {
  const max_concurrent = parseInt(document.getElementById("setting-max-concurrent").value, 10);
  const default_quality = document.getElementById("setting-default-quality").value;
  const speed_limit = document.getElementById("setting-speed-limit").value;
  const embed_metadata = document.getElementById("setting-embed-meta").checked;

  const msg = document.getElementById("settings-status-msg");
  if (msg) {
    msg.innerText = "Saving...";
    msg.style.color = "var(--text-secondary)";
  }

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        max_concurrent,
        default_quality,
        speed_limit,
        embed_metadata
      })
    });
    if (res.ok) {
      if (msg) {
        msg.innerText = "Preferences saved successfully.";
        msg.style.color = "var(--success)";
        setTimeout(() => { if (msg) msg.innerText = ""; }, 3000);
      }
    } else {
      if (msg) {
        msg.innerText = "Failed to save settings.";
        msg.style.color = "var(--danger)";
      }
    }
  } catch (e) {
    if (msg) {
      msg.innerText = "Error: " + e.message;
      msg.style.color = "var(--danger)";
    }
  }
}

// Fetch Metadata (with 60s timeout supervisor for cloud hosts)
async function fetchMetadata() {
  const url = document.getElementById("url-input").value.trim();
  if (!url) return alert("Please enter a media URL.");

  if (!navigator.onLine) {
    return alert("Network connection offline. Please reconnect to fetch media.");
  }

  const fetchBtn = document.getElementById("fetch-btn");
  fetchBtn.disabled = true;
  fetchBtn.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
      <circle cx="12" cy="12" r="10"></circle>
      <path d="M12 2a10 10 0 0 1 10 10"></path>
    </svg>
    <span>Analyzing...</span>
  `;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 60000);

  try {
    const res = await fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to fetch media metadata.");
    }

    const data = await res.json();
    state.currentMetadata = data;

    document.getElementById("meta-title").innerText = data.title || "Untitled Media";
    document.getElementById("meta-author").innerText = `Author: ${data.uploader || data.channel || "Unknown"}`;
    const m = Math.floor((data.duration || 0) / 60);
    const s = (data.duration || 0) % 60;
    document.getElementById("meta-stats").innerText = `Duration: ${m}:${s.toString().padStart(2, '0')}`;

    if (data.thumbnail) {
      const img = document.getElementById("thumb-img");
      img.src = data.thumbnail;
      img.style.display = "block";
      document.getElementById("thumb-placeholder").style.display = "none";
    }

    renderQualityPills(data.formats || []);
  } catch (e) {
    clearTimeout(timeoutId);
    if (e.name === "AbortError") {
      alert("Analysis timed out. On cloud hosts, video services can delay initial preview.\n\nYou can click 'Download & Open Queue' directly to start downloading without waiting for preview!");
    } else {
      alert("Unable to load media:\n" + e.message);
    }
  } finally {
    fetchBtn.disabled = false;
    fetchBtn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="8"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
      <span>Fetch Media</span>
    `;
  }
}

function renderQualityPills(formats) {
  const container = document.getElementById("pills-container");
  container.innerHTML = "";

  const heights = [...new Set(formats.map(f => f.height).filter(Boolean))].sort((a, b) => b - a);
  const items = [{ label: "Best", q: "best", type: "video" }];

  heights.slice(0, 4).forEach(h => {
    let lbl = `${h}p`;
    if (h === 2160) lbl = "4K (2160p)";
    if (h === 1440) lbl = "2K (1440p)";
    items.push({ label: lbl, q: h.toString(), type: "video" });
  });

  items.push({ label: "Audio MP3", q: "best", type: "audio" });

  items.forEach(item => {
    const btn = document.createElement("button");
    btn.className = "pill-btn" + (item.q === state.selectedQuality && item.type === state.selectedFormatType ? " active" : "");
    btn.innerText = item.label;
    btn.onclick = () => {
      state.selectedQuality = item.q;
      state.selectedFormatType = item.type;
      document.querySelectorAll(".pill-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
    };
    container.appendChild(btn);
  });
}

// Add to Queue
async function queueMedia(jumpToQueue = false) {
  const url = document.getElementById("url-input").value.trim();
  if (!url) return alert("Please enter a media URL.");

  const payload = {
    url,
    title: (state.currentMetadata && state.currentMetadata.title) ? state.currentMetadata.title : "Analyzing URL...",
    thumbnail: state.currentMetadata ? state.currentMetadata.thumbnail : null,
    format_type: state.selectedFormatType || "video",
    quality: state.selectedQuality || "best",
    audio_codec: "mp3",
    audio_quality: "320",
    embed_thumbnail: true,
    add_metadata: true,
  };

  try {
    const res = await fetch("/api/queue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      document.getElementById("url-input").value = "";
      if (jumpToQueue) showTab("queue");
      else alert("Added to download queue.");
    } else {
      const err = await res.json();
      alert("Failed to queue download: " + (err.detail || "Server error"));
    }
  } catch (e) {
    alert("Error adding to queue: " + e.message);
  }
}

// Render Queue
async function loadQueue() {
  try {
    const res = await fetch("/api/queue");
    const data = await res.json();
    data.tasks.forEach(t => { state.tasks[t.id] = t; });
    renderQueue();
  } catch (e) {}
}

function renderQueue() {
  const list = document.getElementById("queue-list");
  if (!list) return;

  const tasks = Object.values(state.tasks);
  document.getElementById("badge-queue-count").innerText = tasks.filter(t => t.status === "downloading" || t.status === "queued").length;

  if (tasks.length === 0) {
    list.innerHTML = `<div style="text-align:center; padding: 40px; color: var(--text-muted)">Queue is empty</div>`;
    return;
  }

  list.innerHTML = "";
  tasks.reverse().forEach(task => {
    const card = document.createElement("div");
    card.className = "task-card";
    const pct = Math.round((task.progress || 0) * 100);

    card.innerHTML = `
      <div class="task-top">
        <span class="task-title">${task.title}</span>
        <span style="font-size:0.75rem; font-weight:700; color: var(--accent)">${task.badge}</span>
      </div>
      <div class="progress-bar-bg">
        <div class="progress-bar-fill" style="width: ${pct}%"></div>
      </div>
      <div class="task-bot">
        <span>${task.speed} • ${task.size_info} • ${task.eta}</span>
        <div style="display:flex; align-items:center; gap:6px;">
          ${task.status === "queued" || task.status === "downloading" 
            ? `<button class="pill-btn" style="background:#dc2626; color:#fff; display:flex; align-items:center; gap:4px;" onclick="cancelTask('${task.id}')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                <span>Cancel</span>
              </button>`
            : task.status === 'completed'
              ? `<a href="/api/download/${task.id}" class="pill-btn" style="background:var(--accent); color:#fff; text-decoration:none; padding:4px 10px; border-radius:6px; font-size:0.75rem; display:flex; align-items:center; gap:4px;" download>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                  <span>Save to Device</span>
                </a>`
              : task.status === 'canceled'
                ? `<div style="display:flex; align-items:center; gap:6px;">
                    <span style="font-weight:700; font-size:0.75rem; color:var(--text-muted)">CANCELED</span>
                    <button class="pill-btn" style="background:var(--accent); color:#fff; display:flex; align-items:center; gap:4px;" onclick="retryTask('${task.id}')">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>
                      <span>Retry</span>
                    </button>
                  </div>`
                : `<div style="display:flex; align-items:center; gap:6px;">
                    <span style="font-weight:700; font-size:0.75rem; color:var(--danger)">FAILED</span>
                    <button class="pill-btn" style="background:var(--accent); color:#fff; display:flex; align-items:center; gap:4px;" onclick="retryTask('${task.id}')">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>
                      <span>Retry</span>
                    </button>
                  </div>`}
        </div>
      </div>
      ${task.error_msg ? `<div style="margin-top:8px; font-size:0.75rem; color:#fca5a5; background:rgba(239,68,68,0.12); border:1px solid rgba(239,68,68,0.3); padding:6px 10px; border-radius:6px; white-space:pre-wrap; word-break:break-word;">${task.error_msg}</div>` : ''}
    `;
    list.appendChild(card);
  });
}

async function cancelTask(id) {
  await fetch(`/api/queue/${id}/cancel`, { method: "POST" });
}

async function retryTask(id) {
  try {
    const res = await fetch(`/api/queue/${id}/retry`, { method: "POST" });
    if (res.ok) {
      loadQueue();
    }
  } catch (e) {
    alert("Error retrying task: " + e.message);
  }
}

async function clearFinishedQueue() {
  await fetch("/api/queue/clear", { method: "POST" });
  state.tasks = {};
  loadQueue();
}

// Library
async function loadLibrary() {
  const list = document.getElementById("library-list");
  if (!list) return;
  try {
    const res = await fetch("/api/library");
    const data = await res.json();
    const items = data.items || [];

    if (items.length === 0) {
      list.innerHTML = `<div style="text-align:center; padding: 40px; color: var(--text-muted)">No downloaded media yet.</div>`;
      return;
    }

    list.innerHTML = "";
    items.forEach((item, idx) => {
      const card = document.createElement("div");
      card.className = "task-card";
      card.innerHTML = `
        <div class="task-top">
          <span class="task-title">${item.title}</span>
          <span style="font-size:0.75rem; color: var(--text-muted)">${item.format} • ${item.size}</span>
        </div>
        <div class="task-bot" style="margin-top:8px">
          <span style="font-size:0.75rem">${item.path || "Saved"}</span>
          <div style="display:flex; gap:6px;">
            <a href="/api/library/download/${idx}" class="pill-btn" style="background:var(--accent); color:#fff; text-decoration:none; padding:4px 10px; border-radius:6px; font-size:0.75rem; display:flex; align-items:center; gap:4px;" download>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
              <span>Download</span>
            </a>
            <button class="pill-btn" onclick="deleteLibraryItem(${idx})" style="background:#374151; display:flex; align-items:center; gap:4px;">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
              <span>Remove</span>
            </button>
          </div>
        </div>
      `;
      list.appendChild(card);
    });
  } catch (e) {}
}

async function deleteLibraryItem(idx) {
  if (confirm("Remove item from library history?")) {
    await fetch(`/api/library/${idx}`, { method: "DELETE" });
    loadLibrary();
  }
}
