// =====================
// Risk Trajectory Frontend Client
// Works on: Cloud Run (set window.RT_API_BASE), Codespaces, Localhost
// =====================

function resolveApiBase() {
  // 1) Cloud Run / production: explicitly set in index.html
  if (window.RT_API_BASE && typeof window.RT_API_BASE === "string" && window.RT_API_BASE.trim() !== "") {
    return window.RT_API_BASE.trim().replace(/\/+$/, "");
  }

  // 2) Codespaces: frontend on 8080, API on 8000
  const host = location.host; // e.g. xxx-8080.app.github.dev
  if (host.includes("-8080.") && host.includes(".app.github.dev")) {
    return `${location.protocol}//${host.replace("-8080.", "-8000.")}`;
  }

  // 3) Local dev
  return "http://localhost:8000";
}

const API_HTTP = resolveApiBase();
const API_WS = API_HTTP.replace(/^http/, "ws") + "/ws";

let ws = null;
let currentPatient = null;

const el = (id) => document.getElementById(id);

function setStatus(connected, text) {
  el("statusDot").style.background = connected ? "#2fd17a" : "#666";
  el("statusText").textContent = text;
}

function setBadge(level) {
  const b = el("riskBadge");
  b.className = `badge ${level}`;
  b.textContent = level.toUpperCase();
}

function renderOutcomes(outcomes) {
  const container = el("outcomes");
  container.innerHTML = "";

  if (!outcomes || outcomes.length === 0) {
    container.innerHTML = `<div class="muted">No predicted outcomes.</div>`;
    return;
  }

  outcomes.forEach((o) => {
    const prob = Math.round((o.probability || 0) * 100);
    const because = (o.because || []).slice(0, 4).map((x) => `• ${x}`).join("<br/>");

    container.innerHTML += `
      <div class="item">
        <div class="name">${o.name}</div>
        <div class="prob">Probability: ${prob}%</div>
        <div class="because">${because}</div>
        <div class="action"><b>Action:</b> ${o.suggested_action || "Clinician review."}</div>
      </div>
    `;
  });
}

function renderEvents(events) {
  const container = el("events");
  container.innerHTML = "";

  if (!events || events.length === 0) {
    container.innerHTML = `<div class="muted">No events found.</div>`;
    return;
  }

  events.forEach((e) => {
    container.innerHTML += `
      <div class="evt">
        <div class="meta">
          <span>${new Date(e.ts).toLocaleString()}</span>
          <span>${e.level.toUpperCase()} • ${e.title}</span>
        </div>
        <div class="msg">${e.message}</div>
      </div>
    `;
  });
}

async function loadPatients() {
  const res = await fetch(`${API_HTTP}/patients`);
  if (!res.ok) throw new Error(`Failed to load patients: ${res.status}`);

  const patients = await res.json();
  const sel = el("patientSelect");
  sel.innerHTML = "";

  patients.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.id} — ${p.name} (${p.profile})`;
    sel.appendChild(opt);
  });

  currentPatient = patients[0]?.id || null;
  sel.value = currentPatient;
}

async function refreshEvents() {
  if (!currentPatient) return;
  const res = await fetch(`${API_HTTP}/events?patient_id=${encodeURIComponent(currentPatient)}&limit=50`);
  if (!res.ok) return;
  const events = await res.json();
  renderEvents(events);
}

function connect() {
  if (!currentPatient) return;

  if (ws) {
    try { ws.close(); } catch {}
    ws = null;
  }

  let retryMs = 1000;

  const openSocket = () => {
    setStatus(false, "Connecting...");
    ws = new WebSocket(`${API_WS}?patient_id=${encodeURIComponent(currentPatient)}`);

    ws.onopen = () => {
      retryMs = 1000;
      setStatus(true, "Connected");
      refreshEvents();
    };

    ws.onclose = () => {
      setStatus(false, `Disconnected • retrying in ${Math.round(retryMs / 1000)}s`);
      setTimeout(openSocket, retryMs);
      retryMs = Math.min(15000, Math.round(retryMs * 1.5));
    };

    ws.onerror = () => {
      // Usually followed by onclose
    };

    ws.onmessage = (msg) => {
      const data = JSON.parse(msg.data);
      if (data.error) {
        setStatus(false, data.error);
        return;
      }

      const v = data.vitals;
      el("hr").textContent = v.heart_rate.toFixed(1);
      el("bp").textContent = `${v.bp_systolic.toFixed(0)}/${v.bp_diastolic.toFixed(0)}`;
      el("spo2").textContent = v.oxygen_saturation.toFixed(1);
      el("temp").textContent = v.temperature.toFixed(2);

      el("riskScore").textContent = data.risk_score.toFixed(1);
      el("profile").textContent = data.profile;

      setBadge(data.level);
      el("explainText").textContent = data.explain || "--";

      const r = data.rates_per_min || {};
      el("dhr").textContent = (r.heart_rate ?? 0).toFixed(2);
      el("dspo2").textContent = (r.oxygen_saturation ?? 0).toFixed(2);
      el("dsys").textContent = (r.bp_systolic ?? 0).toFixed(2);
      el("dtemp").textContent = (r.temperature ?? 0).toFixed(2);

      renderOutcomes(data.outcomes);

      if (data.level === "orange" || data.level === "red") {
        refreshEvents();
      }
    };
  };

  openSocket();
}

function wireUI() {
  el("patientSelect").addEventListener("change", (e) => {
    currentPatient = e.target.value;
    setStatus(false, "Disconnected");
  });

  el("connectBtn").addEventListener("click", connect);
  el("refreshEventsBtn").addEventListener("click", refreshEvents);
}

(async function init() {
  try {
    await loadPatients();
    wireUI();
    setStatus(false, "Ready");
  } catch (e) {
    setStatus(false, `Frontend error: ${e.message}`);
  }
})();
