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
  initWebSocket();
  checkSystemStatus();
  loadAuthSettings();
  loadLibrary();
  loadQueue();
});

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
    settings: "Settings & System",
  };
  document.getElementById("top-title").innerText = titles[tabKey] || "Argus Studio";

  if (tabKey === "queue") loadQueue();
  if (tabKey === "library") loadLibrary();
  if (tabKey === "settings") {
    checkSystemStatus();
    loadAuthSettings();
  }
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

// Check System Status & FFmpeg
async function checkSystemStatus() {
  try {
    const res = await fetch("/api/system");
    const data = await res.json();
    const banner = document.getElementById("ffmpeg-banner");
    const statusLbl = document.getElementById("ffmpeg-status-lbl");
    const verLbl = document.getElementById("app-version-val");

    if (verLbl && data.version) {
      verLbl.innerText = `v${data.version}`;
    }

    if (data.ffmpeg_available) {
      if (banner) banner.style.display = "none";
      if (statusLbl) {
        statusLbl.innerText = `● FFmpeg Active (${data.ffmpeg_location})`;
        statusLbl.style.color = "var(--success)";
      }
    } else {
      if (banner) banner.style.display = "flex";
      if (statusLbl) {
        statusLbl.innerText = "⚠️ FFmpeg Missing";
        statusLbl.style.color = "var(--danger)";
      }
    }
  } catch (e) {
    console.error("System check error", e);
  }
}

// In-App Updates Check
async function checkWebUpdates() {
  const btn = document.getElementById("check-update-btn");
  const msg = document.getElementById("update-msg");
  if (btn) btn.innerText = "Checking...";
  try {
    const res = await fetch("/api/system/update/check");
    const data = await res.json();
    if (data.update_available) {
      if (msg) {
        msg.innerHTML = `<span style="color:var(--success); font-weight:600">🎉 Version v${data.latest_version} available!</span> <a href="${data.download_url}" target="_blank" class="pill-btn" style="background:var(--accent); color:#fff; text-decoration:none; padding:4px 8px; border-radius:4px; font-size:0.75rem">Download</a>`;
      }
    } else if (data.error) {
      if (msg) {
        msg.innerText = `⚠️ ${data.error}`;
        msg.style.color = "var(--warning)";
      }
    } else {
      if (msg) {
        msg.innerText = "● You are running the latest version";
        msg.style.color = "var(--success)";
      }
    }
  } catch (e) {
    if (msg) {
      msg.innerText = "Error checking updates.";
      msg.style.color = "var(--danger)";
    }
  } finally {
    if (btn) btn.innerText = "Check for Updates";
  }
}

// Session Authentication & Verification Bypass Management
async function loadAuthSettings() {
  try {
    const res = await fetch("/api/settings/auth");
    if (!res.ok) return;
    const data = await res.json();

    const badge = document.getElementById("auth-status-badge");
    if (badge) {
      if (data.has_cookies) {
        badge.innerText = `● Session Cookies Active (${data.cookie_lines} entries)`;
        badge.style.background = "#065f46";
        badge.style.color = "#a7f3d0";
      } else {
        badge.innerText = "Cloud Restricted (No Cookies)";
        badge.style.background = "#78350f";
        badge.style.color = "#fde68a";
      }
    }

    const profSelect = document.getElementById("client-profile-select");
    if (profSelect && data.player_client_profile) {
      profSelect.value = data.player_client_profile;
    }

    const proxyInput = document.getElementById("proxy-url-input");
    if (proxyInput && data.proxy_url) {
      proxyInput.value = data.proxy_url;
    }
  } catch (e) {
    console.error("Auth load error", e);
  }
}

async function saveCookiesText() {
  const txt = document.getElementById("cookies-input").value.trim();
  if (!txt) return alert("Please paste Netscape cookies content before saving.");
  try {
    const res = await fetch("/api/settings/cookies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: txt }),
    });
    if (res.ok) {
      alert("Session cookies saved successfully! Cloud verification is now bypassed.");
      document.getElementById("cookies-input").value = "";
      loadAuthSettings();
    } else {
      const err = await res.json();
      alert("Failed to save cookies: " + (err.detail || "Unknown error"));
    }
  } catch (e) {
    alert("Error saving cookies: " + e.message);
  }
}

function handleCookieFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async (e) => {
    const content = e.target.result;
    document.getElementById("cookies-input").value = content;
    await saveCookiesText();
  };
  reader.readAsText(file);
}

async function clearCookies() {
  if (!confirm("Clear saved session cookies?")) return;
  try {
    const res = await fetch("/api/settings/cookies", { method: "DELETE" });
    if (res.ok) {
      alert("Session cookies cleared.");
      document.getElementById("cookies-input").value = "";
      loadAuthSettings();
    }
  } catch (e) {
    alert("Error clearing cookies: " + e.message);
  }
}

async function saveProfileSettings() {
  const profile = document.getElementById("client-profile-select").value;
  const proxy = document.getElementById("proxy-url-input").value.trim();
  try {
    await fetch("/api/settings/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_client_profile: profile, proxy_url: proxy }),
    });
  } catch (e) {
    console.error("Profile save error", e);
  }
}

async function verifyAuthConnection() {
  const btn = document.getElementById("verify-conn-btn");
  const msg = document.getElementById("verify-status-msg");
  if (btn) btn.innerText = "Verifying...";
  if (msg) msg.innerText = "Testing YouTube access...";

  try {
    const res = await fetch("/api/settings/verify", { method: "POST" });
    const data = await res.json();
    if (data.verified) {
      if (msg) {
        msg.innerText = "✓ YouTube Connected & Verified!";
        msg.style.color = "var(--success)";
      }
      alert("Connection Successful!\nYouTube is fully authenticated and ready to ingest media.");
    } else {
      if (msg) {
        msg.innerText = "⚠️ Verification Failed";
        msg.style.color = "var(--danger)";
      }
      alert("Verification Failed:\n" + data.message + "\n\nPlease upload valid browser cookies.txt or try 'iOS Client'.");
    }
  } catch (e) {
    if (msg) {
      msg.innerText = "Error: " + e.message;
      msg.style.color = "var(--danger)";
    }
  } finally {
    if (btn) btn.innerText = "🛡️ Verify Connection";
  }
}

// Client Verification Modal Controls
function showVerificationModal() {
  const modal = document.getElementById("verification-modal");
  if (modal) {
    modal.style.display = "flex";
  }
}

function closeVerificationModal() {
  const modal = document.getElementById("verification-modal");
  if (modal) {
    modal.style.display = "none";
  }
}

function goToSessionAuthSettings() {
  closeVerificationModal();
  showTab("settings");
  setTimeout(() => {
    const card = document.getElementById("card-session-auth");
    if (card) {
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.style.boxShadow = "0 0 0 2px var(--accent)";
      setTimeout(() => { card.style.boxShadow = "none"; }, 2000);
    }
  }, 100);
}

// Install FFmpeg Action
async function installFFmpeg() {
  const btn = document.getElementById("install-ff-btn");
  if (btn) btn.innerText = "Installing Portable FFmpeg...";
  try {
    const res = await fetch("/api/system/ffmpeg/install", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      alert("FFmpeg successfully installed and active!");
      checkSystemStatus();
    } else {
      alert("Failed to install FFmpeg.");
    }
  } catch (e) {
    alert("Error installing FFmpeg: " + e.message);
  } finally {
    if (btn) btn.innerText = "Install Portable FFmpeg";
  }
}

// Fetch Metadata
async function fetchMetadata() {
  const url = document.getElementById("url-input").value.trim();
  if (!url) return alert("Please enter a media URL.");

  const fetchBtn = document.getElementById("fetch-btn");
  fetchBtn.disabled = true;
  fetchBtn.innerText = "Analyzing...";

  try {
    const res = await fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to fetch metadata");
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
    const errText = (e && e.message) ? e.message : String(e);
    if (errText.includes("verification") || errText.includes("bot") || errText.includes("429") || errText.includes("Sign in") || errText.includes("Cloud Restricted")) {
      showVerificationModal();
    } else {
      alert("Metadata Retrieval Error:\n" + errText);
    }
  } finally {
    fetchBtn.disabled = false;
    fetchBtn.innerText = "Fetch Media";
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
    format_type: state.selectedFormatType,
    quality: state.selectedQuality,
    audio_codec: document.getElementById("audio-codec") ? document.getElementById("audio-codec").value : "mp3",
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
      if (jumpToQueue) showTab("queue");
      else alert("Added to queue!");
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
        <span style="display:flex; align-items:center; gap:6px;">
          ${task.status === "queued" || task.status === "downloading" 
            ? `<button class="pill-btn" style="background:#dc2626; color:#fff" onclick="cancelTask('${task.id}')">Cancel</button>`
            : task.status === 'completed'
              ? `<a href="/api/download/${task.id}" class="pill-btn" style="background:var(--accent); color:#fff; text-decoration:none; padding:4px 10px; border-radius:6px; font-size:0.75rem;" download>⬇ Save to Device</a>`
              : task.status === 'canceled'
                ? `<span style="text-transform:uppercase; font-weight:700; color:var(--text-muted)">CANCELED</span>`
                : `<span style="text-transform:uppercase; font-weight:700; color:var(--danger)">FAILED</span>`}
        </span>
      </div>
      ${task.error_msg ? `<div style="margin-top:8px; font-size:0.75rem; color:#fca5a5; background:rgba(239,68,68,0.12); border:1px solid rgba(239,68,68,0.3); padding:6px 10px; border-radius:6px; white-space:pre-wrap; word-break:break-word;">${task.error_msg}</div>` : ''}
    `;
    list.appendChild(card);
  });
}

async function cancelTask(id) {
  await fetch(`/api/queue/${id}/cancel`, { method: "POST" });
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
            <a href="/api/library/download/${idx}" class="pill-btn" style="background:var(--accent); color:#fff; text-decoration:none; padding:4px 10px; border-radius:6px; font-size:0.75rem;" download>⬇ Download</a>
            <button class="pill-btn" onclick="deleteLibraryItem(${idx})" style="background:#374151">Remove</button>
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
