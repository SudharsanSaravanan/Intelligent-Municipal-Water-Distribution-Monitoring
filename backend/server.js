/**
 * server.js — HydroNet Monitor Backend
 *
 * Firebase RTDB path: /waterSystem/status
 * Schema:
 *   master: { tdsPpm, waterQuality, tankLevelPercent, tankLevelCm }
 *   slave:  { flow1_Lmin, flow2_Lmin, tdsPpm, waterQualityCode,
 *             waterQuality, tankLevelPercent, tankLevelCm }
 */

require("dotenv").config();
const express = require("express");
const cors = require("cors");
const http = require("http");
const { Server } = require("socket.io");
const { db } = require("./firebase");
const telemetryRoutes = require("./api/telemetry.routes");
const { readCache, writeCache } = require("./database/cache.helper");

// ── Express + WebSocket ───────────────────────────────────────
const app = express();
const server = http.createServer(app);
const io = new Server(server, {
    cors: { origin: "*", methods: ["GET", "POST"] }
});

app.use(cors());
app.use(express.json());

// ── REST routes ───────────────────────────────────────────────
app.use("/api/telemetry", telemetryRoutes);

// Health check
app.get("/health", (req, res) => {
    res.json({
        status: "OK",
        service: "HydroNet Monitor Backend",
        time: new Date().toISOString(),
        uptime: Math.round(process.uptime()) + "s"
    });
});

// ── Utility: Normalize Firebase keys ────────────────────────
// Early firmware sent slave keys with trailing colons, e.g. "flow1_Lmin:"
// This strips them so the rest of the app always sees clean field names.
function normalizeKeys(obj) {
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) return obj;
    const out = {};
    for (const key of Object.keys(obj)) {
        const clean = key.replace(/:+$/, ""); // remove any trailing colons
        out[clean] = obj[key];
    }
    return out;
}

// ── Utility: raise alert in Firebase + broadcast ──────────────
async function raiseAlert(nodeId, type, message, level) {
    const alert = {
        nodeId, type, message, level,
        resolved: false,
        timestamp: new Date().toISOString()
    };
    await db.ref("/waterSystem/alerts").push(alert);
    io.emit("alert", alert);
    console.log(`[ALERT] ${level.toUpperCase()} — ${message}`);
}

// ──────────────────────────────────────────────────────────────
// Firebase RTDB Listener
// The ESP32 master does a PUT to /waterSystem/status every 5 s
// ──────────────────────────────────────────────────────────────
db.ref("/waterSystem/status").on("value", async (snapshot) => {
    const data = snapshot.val();
    if (!data) return;

    const ts = new Date().toISOString();
    console.log(`\n[Firebase] /waterSystem/status updated @ ${ts}`);

    const cache = readCache();

    // ── Master tank ─────────────────────────────────────────
    if (data.master) {
        const m = normalizeKeys(data.master);
        cache.master = { ...m, cachedAt: ts };
        console.log(`  [MASTER] TDS: ${m.tdsPpm} ppm | Level: ${m.tankLevelPercent}% | Quality: ${m.waterQuality}`);

        // Broadcast to connected dashboards
        io.emit("master_update", { ...m, timestamp: ts });

        // Historical snapshot
        db.ref("/waterSystem/history/master").push({ ...m, timestamp: ts });

        // ── Alert thresholds ───────────────────────────────────
        if (m.tankLevelPercent !== undefined && m.tankLevelPercent >= 0) {
            if (m.tankLevelPercent <= 15) {
                await raiseAlert("MASTER", "CRITICAL_LOW",
                    `Main tank critically low: ${m.tankLevelPercent.toFixed(1)}%`, "critical");
            } else if (m.tankLevelPercent <= 25) {
                await raiseAlert("MASTER", "LOW_LEVEL",
                    `Main tank low: ${m.tankLevelPercent.toFixed(1)}%`, "warning");
            }
        }

        if (m.waterQuality && m.waterQuality.toLowerCase().includes("bad")) {
            await raiseAlert("MASTER", "BAD_WATER",
                `Main tank water quality BAD: ${m.tdsPpm} ppm`, "critical");
        }
    }

    // ── Slave / Sub tank ─────────────────────────────────────
    if (data.slave) {
        // Normalize keys — strips trailing colons from old firmware payloads
        const s = normalizeKeys(data.slave);
        cache.slave = { ...s, cachedAt: ts };
        console.log(`  [SLAVE ] TDS: ${s.tdsPpm} ppm | Level: ${s.tankLevelPercent}% | Flow1: ${s.flow1_Lmin} L/min`);

        io.emit("slave_update", { ...s, timestamp: ts });
        db.ref("/waterSystem/history/slave").push({ ...s, timestamp: ts });

        if (s.tankLevelPercent !== undefined && s.tankLevelPercent >= 0 && s.tankLevelPercent <= 20) {
            await raiseAlert("SLAVE", "LOW_LEVEL",
                `Sub tank low: ${s.tankLevelPercent.toFixed(1)}%`, "warning");
        }

        if (s.waterQualityCode >= 4) {
            await raiseAlert("SLAVE", "BAD_WATER",
                `Sub tank water quality BAD: ${s.tdsPpm} ppm`, "critical");
        }
    }

    cache.lastUpdated = ts;
    writeCache(cache);
});

// ── Alert listener → forward to dashboard ────────────────────
db.ref("/waterSystem/alerts")
    .orderByChild("resolved").equalTo(false)
    .on("child_added", (snap) => {
        io.emit("alert", { id: snap.key, ...snap.val() });
    });

// ── WebSocket — send cached state on connect ──────────────────
io.on("connection", (socket) => {
    console.log(`[WS] Client connected: ${socket.id}`);
    socket.emit("initial_state", readCache());
    socket.on("disconnect", () => console.log(`[WS] Client left: ${socket.id}`));
});

// ── Start server ──────────────────────────────────────────────
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log(`\n╔══════════════════════════════════════════╗`);
    console.log(`║  HydroNet Monitor Backend v1.0           ║`);
    console.log(`║  REST API  : http://localhost:${PORT}      ║`);
    console.log(`║  WebSocket : ws://localhost:${PORT}        ║`);
    console.log(`║  Firebase  : hydronet-monitor RTDB       ║`);
    console.log(`╚══════════════════════════════════════════╝\n`);
});

module.exports = { app, io };
