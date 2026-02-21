/**
 * app.js — HydroNet Frontend Application
 *
 * Data schema from backend (matches ESP32 firmware exactly):
 *   cache.master → { tdsPpm, waterQuality, tankLevelPercent, tankLevelCm }
 *   cache.slave  → { flow1_Lmin, flow2_Lmin, tdsPpm, waterQualityCode,
 *                    waterQuality, tankLevelPercent, tankLevelCm }
 *
 * WebSocket events: initial_state, master_update, slave_update, alert
 * REST API: GET /api/telemetry/latest | /master | /slave | /history/:node | /alerts
 */

// ── Config ──────────────────────────────────────────────────────
const CONFIG = {
    backendUrl: "http://localhost:3000",
    pollInterval: 15000,   // REST fallback polling interval (ms)
    chartPoints: 30,      // max data points shown in chart
};

// ── Application State ────────────────────────────────────────────
const state = {
    master: {},
    slave: {},
    alerts: [],
    connected: false,
    chartData: {
        labels: [],
        masterLevels: [],
        masterTds: [],
        slaveLevels: [],
        slaveTds: [],
    },
};

// ── DOM References ───────────────────────────────────────────────
const $ = id => document.getElementById(id);

const dom = {
    // KPI — Levels
    kpiMasterPct: $("kpi-master-pct"),
    kpiMasterCm: $("kpi-master-cm"),
    kpiSlavePct: $("kpi-slave-pct"),
    kpiSlaveCm: $("kpi-slave-cm"),
    kpiFlow1: $("kpi-flow1"),
    kpiFlow2: $("kpi-flow2"),

    // KPI — Quality
    kpiMasterTds: $("kpi-master-tds"),
    kpiMasterQuality: $("kpi-master-quality"),
    kpiSlaveTds: $("kpi-slave-tds"),
    kpiSlaveQuality: $("kpi-slave-quality"),
    kpiAlertCount: $("kpi-alert-count"),

    // Master Tank visual
    masterWaterFill: $("master-water-fill"),
    masterLevelLbl: $("master-level-label"),
    masterStatPct: $("master-stat-pct"),
    masterStatCm: $("master-stat-cm"),
    masterStatTds: $("master-stat-tds"),
    masterStatQuality: $("master-stat-quality"),
    masterQBadge: $("master-quality-badge"),
    masterStatTime: $("master-stat-time"),

    // Slave Tank visual
    slaveWaterFill: $("slave-water-fill"),
    slaveLevelLbl: $("slave-level-label"),
    slaveStatPct: $("slave-stat-pct"),
    slaveStatCm: $("slave-stat-cm"),
    slaveStatTds: $("slave-stat-tds"),
    slaveQBadge: $("slave-quality-badge"),
    slaveStatFlow1: $("slave-stat-flow1"),
    slaveStatFlow2: $("slave-stat-flow2"),

    // Connection
    statusDot: $("status-dot"),
    statusText: $("status-text"),
    statusDotMob: $("status-dot-mobile"),
    lastUpdateTime: $("last-update-time"),

    // Alerts
    alertBadge: $("alert-badge"),
    alertsList: $("alerts-list"),

    // Toast
    toastContainer: $("toast-container"),
};

// ── Formatters ───────────────────────────────────────────────────
function fmtPct(v) { return (v != null && v >= 0) ? `${Number(v).toFixed(1)}%` : "--%"; }
function fmtCm(v) { return (v != null && v >= 0) ? `${Number(v).toFixed(1)} cm` : "-- cm"; }
function fmtPpm(v) { return (v != null && v >= 0) ? `${Number(v).toFixed(0)} ppm` : "-- ppm"; }
function fmtFlow(v) { return (v != null) ? `${Number(v).toFixed(2)} L/min` : "-- L/min"; }
function fmtTime(ts) {
    if (!ts) return "--";
    try { return new Date(ts).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
    catch { return "--"; }
}

// ── Client-side key normalizer ─────────────────────────────────────
// Strips trailing colons from Firebase field names produced by early firmware
// e.g. "flow1_Lmin:" → "flow1_Lmin"
function normalizeKeys(obj) {
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) return obj;
    const out = {};
    for (const k of Object.keys(obj)) out[k.replace(/:+$/, "")] = obj[k];
    return out;
}

// ── Water Quality → CSS class ────────────────────────────────────
function qualityClass(qualityText) {
    if (!qualityText) return "error";
    const q = qualityText.toLowerCase();
    if (q.includes("excellent")) return "excellent";
    if (q.includes("good")) return "good";
    if (q.includes("average") || q.includes("not recommended")) return "average";
    if (q.includes("bad") || q.includes("high tds")) return "bad";
    return "error";
}

function qualityShort(qualityText) {
    if (!qualityText) return "--";
    const q = qualityText.toLowerCase();
    if (q.includes("excellent")) return "Excellent";
    if (q.includes("good")) return "Good";
    if (q.includes("average")) return "Average";
    if (q.includes("not ideal")) return "Low Minerals";
    if (q.includes("bad")) return "Bad";
    if (q.includes("error") || q.includes("no reading")) return "No Reading";
    return qualityText;
}

// ── KPI icon tint based on quality ──────────────────────────────
function setQualityIcon(iconEl, qualityText) {
    const cls = qualityClass(qualityText);
    iconEl.className = `kpi-icon ${cls === "excellent" ? "green" :
        cls === "good" ? "blue" :
            cls === "average" ? "yellow" :
                cls === "bad" ? "red" : "yellow"
        }`;
}

// ── Tank Visual Update ───────────────────────────────────────────
function updateTankFill(fillEl, labelEl, pct) {
    const v = Math.max(0, Math.min(100, pct || 0));
    fillEl.style.height = `${v}%`;
    labelEl.textContent = `${v.toFixed(0)}%`;
    // colour hint: red<20, amber<40, normal≥40
    fillEl.style.filter =
        v < 20 ? "hue-rotate(140deg) saturate(1.8)" :
            v < 40 ? "hue-rotate(30deg)  saturate(1.3)" : "none";
}

// ── Render Master Tank ────────────────────────────────────────────
function renderMaster(data, timestamp) {
    if (!data || typeof data !== "object") return;
    data = normalizeKeys(data); // strip any colon-suffixed keys
    state.master = data;

    const ts = timestamp || new Date().toISOString();

    // KPI
    dom.kpiMasterPct.textContent = fmtPct(data.tankLevelPercent);
    dom.kpiMasterCm.textContent = fmtCm(data.tankLevelCm);
    dom.kpiMasterTds.textContent = fmtPpm(data.tdsPpm);
    dom.kpiMasterQuality.textContent = qualityShort(data.waterQuality);
    setQualityIcon($("kpi-master-tds-icon"), data.waterQuality);

    // Tank visual
    updateTankFill(dom.masterWaterFill, dom.masterLevelLbl, data.tankLevelPercent);

    // Stats panel
    dom.masterStatPct.textContent = fmtPct(data.tankLevelPercent);
    dom.masterStatCm.textContent = fmtCm(data.tankLevelCm);
    dom.masterStatTds.textContent = fmtPpm(data.tdsPpm);
    dom.masterStatTime.textContent = fmtTime(ts);

    const cls = qualityClass(data.waterQuality);
    const short = qualityShort(data.waterQuality);
    dom.masterQBadge.textContent = short;
    dom.masterQBadge.className = `quality-badge ${cls}`;

    // Push chart point
    const label = fmtTime(ts);
    if (state.chartData.labels[state.chartData.labels.length - 1] !== label) {
        pushChartPoint(label, data.tankLevelPercent || 0, data.tdsPpm || 0, null, null);
    }
}

// ── Render Slave Tank ─────────────────────────────────────────────
function renderSlave(data, timestamp) {
    if (!data || typeof data !== "object") return;
    data = normalizeKeys(data); // strip any colon-suffixed keys
    state.slave = data;

    const ts = timestamp || new Date().toISOString();

    // KPI
    dom.kpiSlavePct.textContent = fmtPct(data.tankLevelPercent);
    dom.kpiSlaveCm.textContent = fmtCm(data.tankLevelCm);
    dom.kpiSlaveTds.textContent = fmtPpm(data.tdsPpm);
    dom.kpiSlaveQuality.textContent = qualityShort(data.waterQuality);
    dom.kpiFlow1.textContent = fmtFlow(data.flow1_Lmin);
    dom.kpiFlow2.textContent = fmtFlow(data.flow2_Lmin);
    setQualityIcon($("kpi-slave-tds-icon"), data.waterQuality);

    // Tank visual
    updateTankFill(dom.slaveWaterFill, dom.slaveLevelLbl, data.tankLevelPercent);

    // Stats
    dom.slaveStatPct.textContent = fmtPct(data.tankLevelPercent);
    dom.slaveStatCm.textContent = fmtCm(data.tankLevelCm);
    dom.slaveStatTds.textContent = fmtPpm(data.tdsPpm);
    dom.slaveStatFlow1.textContent = fmtFlow(data.flow1_Lmin);
    dom.slaveStatFlow2.textContent = fmtFlow(data.flow2_Lmin);

    const cls = qualityClass(data.waterQuality);
    const short = qualityShort(data.waterQuality);
    dom.slaveQBadge.textContent = short;
    dom.slaveQBadge.className = `quality-badge ${cls}`;

    // Push slave chart point
    const label = fmtTime(ts);
    pushChartPoint(label, null, null, data.tankLevelPercent || 0, data.tdsPpm || 0);
}

// ── Chart Data Push ───────────────────────────────────────────────
function pushChartPoint(label, masterLevel, masterTds, slaveLevel, slaveTds) {
    const d = state.chartData;

    if (d.labels[d.labels.length - 1] !== label) {
        d.labels.push(label);
        if (masterLevel != null) d.masterLevels.push(masterLevel); else d.masterLevels.push(d.masterLevels[d.masterLevels.length - 1] ?? 0);
        if (masterTds != null) d.masterTds.push(masterTds); else d.masterTds.push(d.masterTds[d.masterTds.length - 1] ?? 0);
        if (slaveLevel != null) d.slaveLevels.push(slaveLevel); else d.slaveLevels.push(d.slaveLevels[d.slaveLevels.length - 1] ?? 0);
        if (slaveTds != null) d.slaveTds.push(slaveTds); else d.slaveTds.push(d.slaveTds[d.slaveTds.length - 1] ?? 0);

        const MAX = CONFIG.chartPoints;
        if (d.labels.length > MAX) {
            d.labels.shift(); d.masterLevels.shift(); d.masterTds.shift();
            d.slaveLevels.shift(); d.slaveTds.shift();
        }
        updateChart();
    }
}

// ── Alerts ───────────────────────────────────────────────────────
function renderAlerts(alerts) {
    const active = (alerts || []).filter(a => !a.resolved);
    state.alerts = active;

    const count = active.length;
    dom.kpiAlertCount.textContent = count;
    dom.alertBadge.textContent = count;
    dom.alertBadge.classList.toggle("show", count > 0);

    if (!active.length) {
        dom.alertsList.innerHTML = `
      <div class="empty-state">
        <i class="bi bi-shield-check"></i>
        <p>No active alerts — all systems nominal</p>
      </div>`;
        return;
    }

    dom.alertsList.innerHTML = active.map(a => `
    <div class="alert-item ${a.level || 'info'}" id="alert-${a.id}">
      <div class="alert-body">
        <div class="alert-type">${a.type || "ALERT"}</div>
        <div class="alert-message">${a.message}</div>
        <div class="alert-meta">${a.nodeId} · ${fmtTime(a.timestamp)}</div>
      </div>
      <button class="resolve-btn" onclick="resolveAlert('${a.id}')">
        <i class="bi bi-check-lg"></i> Resolve
      </button>
    </div>`).join("");
}

async function resolveAlert(id) {
    try {
        const res = await fetch(`${CONFIG.backendUrl}/api/telemetry/alerts/${id}/resolve`, { method: "POST" });
        if (res.ok) {
            showToast("Resolved", "Alert marked as resolved.", "success");
            document.getElementById(`alert-${id}`)?.remove();
            loadAlerts();
        }
    } catch { showToast("Error", "Could not resolve alert.", "critical"); }
}

// ── Toast ─────────────────────────────────────────────────────────
function showToast(title, message, type = "info") {
    const icons = {
        critical: "bi-exclamation-triangle-fill",
        warning: "bi-exclamation-circle-fill",
        success: "bi-check-circle-fill",
        info: "bi-info-circle-fill"
    };
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
    <i class="bi ${icons[type] || icons.info} toast-icon"></i>
    <div class="toast-body">
      <div class="toast-title">${title}</div>
      <div class="toast-msg">${message}</div>
    </div>`;
    dom.toastContainer.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = "toastOut 0.3s ease forwards";
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ── Chart ─────────────────────────────────────────────────────────
let levelChart = null;
let currentHistoryNode = "master";

function initChart() {
    const ctx = document.getElementById("levelChart").getContext("2d");
    levelChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: state.chartData.labels,
            datasets: [
                {
                    label: "Level (%)",
                    data: state.chartData.masterLevels,
                    borderColor: "#38bdf8",
                    backgroundColor: "rgba(56,189,248,0.10)",
                    tension: 0.4, fill: true,
                    pointRadius: 3, pointHoverRadius: 6,
                    yAxisID: "yLevel",
                },
                {
                    label: "TDS (ppm)",
                    data: state.chartData.masterTds,
                    borderColor: "#4ade80",
                    backgroundColor: "rgba(74,222,128,0.06)",
                    tension: 0.4, fill: true,
                    pointRadius: 3, pointHoverRadius: 6,
                    yAxisID: "yTds",
                }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: true,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: { labels: { color: "#8b95a6", font: { family: "Inter", size: 13 } } },
                tooltip: {
                    backgroundColor: "rgba(14,25,45,0.95)",
                    borderColor: "rgba(255,255,255,0.08)", borderWidth: 1,
                    titleColor: "#e2e8f0", bodyColor: "#8b95a6",
                }
            },
            scales: {
                x: {
                    ticks: { color: "#475569", font: { family: "JetBrains Mono", size: 11 }, maxTicksLimit: 8 },
                    grid: { color: "rgba(255,255,255,0.04)" }
                },
                yLevel: {
                    type: "linear", position: "left",
                    min: 0, max: 100,
                    ticks: { color: "#38bdf8", callback: v => v + "%", stepSize: 20 },
                    grid: { color: "rgba(255,255,255,0.06)" }
                },
                yTds: {
                    type: "linear", position: "right",
                    ticks: { color: "#4ade80", callback: v => v + " ppm" },
                    grid: { display: false }
                }
            }
        }
    });
}

function updateChart() {
    if (!levelChart) return;
    const d = state.chartData;
    const isMaster = currentHistoryNode === "master";
    levelChart.data.labels = [...d.labels];
    levelChart.data.datasets[0].data = [...(isMaster ? d.masterLevels : d.slaveLevels)];
    levelChart.data.datasets[1].data = [...(isMaster ? d.masterTds : d.slaveTds)];
    levelChart.update("none");
}

// ── REST API loaders ──────────────────────────────────────────────
async function loadLatest() {
    try {
        const res = await fetch(`${CONFIG.backendUrl}/api/telemetry/latest`);
        const json = await res.json();
        if (json.success && json.data) {
            if (json.data.master) renderMaster(json.data.master);
            if (json.data.slave) renderSlave(json.data.slave);
            setConnected(true);
        }
    } catch { setConnected(false); }
}

async function loadAlerts() {
    try {
        const res = await fetch(`${CONFIG.backendUrl}/api/telemetry/alerts`);
        const json = await res.json();
        if (json.success) renderAlerts(json.data || []);
    } catch { /* silent */ }
}

// History for chart section
async function loadHistory(node = "master") {
    currentHistoryNode = node;
    $("chart-title").textContent =
        (node === "master" ? "Main Tank" : "Sub Tank") + " — Level & TDS History";

    $("hist-master-btn").classList.toggle("active", node === "master");
    $("hist-slave-btn").classList.toggle("active", node === "slave");

    try {
        const res = await fetch(`${CONFIG.backendUrl}/api/telemetry/history/${node}?limit=30`);
        const json = await res.json();
        if (!json.success || !json.data?.length) return;

        const records = [...json.data].reverse();
        state.chartData.labels = records.map(r => fmtTime(r.timestamp));
        state.chartData.masterLevels = records.map(r => r.tankLevelPercent || 0);
        state.chartData.masterTds = records.map(r => r.tdsPpm || 0);
        state.chartData.slaveLevels = records.map(r => r.tankLevelPercent || 0);
        state.chartData.slaveTds = records.map(r => r.tdsPpm || 0);
        updateChart();
    } catch { showToast("History", "Could not load history.", "warning"); }
}

// ── Socket.IO ─────────────────────────────────────────────────────
function initSocket() {
    const socket = io(CONFIG.backendUrl, { transports: ["websocket", "polling"] });

    socket.on("connect", () => {
        setConnected(true);
        showToast("Connected", "Live data stream active.", "success");
    });
    socket.on("disconnect", () => setConnected(false));
    socket.on("connect_error", () => setConnected(false));

    socket.on("initial_state", (data) => {
        if (data.master) renderMaster(data.master);
        if (data.slave) renderSlave(data.slave);
    });

    socket.on("master_update", (data) => renderMaster(data, data.timestamp));
    socket.on("slave_update", (data) => renderSlave(data, data.timestamp));

    socket.on("alert", (alert) => {
        if (!alert.resolved) {
            showToast(
                alert.type || "Alert",
                alert.message || "",
                alert.level === "critical" ? "critical" : "warning"
            );
            loadAlerts();
        }
    });
}

// ── Connection status UI ──────────────────────────────────────────
function setConnected(on) {
    state.connected = on;
    dom.statusDot.className = `status-dot ${on ? "connected" : "error"}`;
    dom.statusText.textContent = on ? "Live" : "Offline";
    dom.statusDotMob.style.background = on ? "var(--green)" : "var(--red)";
    if (on) dom.lastUpdateTime.textContent = fmtTime(new Date().toISOString());
}

// ── Navigation ────────────────────────────────────────────────────
function initNav() {
    document.querySelectorAll(".nav-item").forEach(link => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            const sectionId = link.dataset.section;
            if (!sectionId) return;

            document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
            document.querySelectorAll(".page-section").forEach(s => s.classList.remove("active"));

            link.classList.add("active");
            document.getElementById(sectionId)?.classList.add("active");

            if (sectionId === "section-history") loadHistory(currentHistoryNode);
            if (sectionId === "section-alerts") loadAlerts();

            document.getElementById("sidebar").classList.remove("open");
        });
    });
}

// ── Init ──────────────────────────────────────────────────────────
function init() {
    initNav();
    initChart();

    // Seed chart with real Firebase snapshot so History tab has a starting point
    // Values: master 75% / 280 ppm  |  slave 60% / 260 ppm
    const seedLabel = fmtTime(new Date().toISOString());
    pushChartPoint(seedLabel, 75, 280, 60, 260);

    initSocket();
    loadLatest();
    loadAlerts();

    // Fallback polling
    setInterval(loadLatest, CONFIG.pollInterval);
    setInterval(loadAlerts, CONFIG.pollInterval * 2);

    // Refresh button
    $("refresh-btn").addEventListener("click", () => {
        loadLatest();
        loadAlerts();
        showToast("Refreshed", "Data reloaded.", "success");
    });

    // Mobile sidebar
    $("menu-btn").addEventListener("click", () => {
        document.getElementById("sidebar").classList.toggle("open");
    });

    // Clock tick
    setInterval(() => {
        if (state.connected)
            dom.lastUpdateTime.textContent = fmtTime(new Date().toISOString());
    }, 1000);

    console.log("[HydroNet] Dashboard init complete.");
}

document.addEventListener("DOMContentLoaded", init);
