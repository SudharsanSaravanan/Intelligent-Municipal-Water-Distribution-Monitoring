/**
 * telemetry.routes.js — REST API for HydroNet Telemetry
 *
 * Base path: /api/telemetry
 *
 * Firebase schema (live ESP32 pushes):
 *   /waterData/<push_id>       { mainTank, subTank }
 *   /systemHistory/mainTank    (push log added by server)
 *   /systemHistory/subTank     (push log added by server)
 *   /systemAlerts              (active alerts added by server)
 *
 * GET  /api/telemetry/latest             — full latest snapshot (from cache)
 * GET  /api/telemetry/master             — main tank live data
 * GET  /api/telemetry/slave              — sub tank live data
 * GET  /api/telemetry/history/:node      — history (node = master|slave)
 * GET  /api/telemetry/alerts             — active (unresolved) alerts
 * POST /api/telemetry/alerts/:id/resolve — resolve an alert
 */

const express = require("express");
const router = express.Router();
const { db } = require("../firebase");
const { readCache } = require("../database/cache.helper");

// ── GET /api/telemetry/latest ─────────────────────────────────────
// Returns the full cached snapshot — fastest path, no Firebase round-trip
router.get("/latest", (req, res) => {
    const cache = readCache();
    res.json({
        success: true,
        source: "local_cache",
        data: cache,
        timestamp: new Date().toISOString()
    });
});

// ── GET /api/telemetry/master ─────────────────────────────────────
// Reads latest push from /waterData live, falls back to cache
router.get("/master", async (req, res) => {
    try {
        const snap = await db.ref("/waterData").orderByKey().limitToLast(1).once("value");
        if (!snap.exists()) {
            const cache = readCache();
            return res.json({ success: true, source: "local_cache", data: cache.master || {} });
        }
        let data = {};
        snap.forEach(child => { if (child.val().mainTank) data = child.val().mainTank; });
        res.json({ success: true, source: "firebase", data });
    } catch (err) {
        const cache = readCache();
        res.json({ success: true, source: "local_cache", data: cache.master || {}, error: err.message });
    }
});

// ── GET /api/telemetry/slave ──────────────────────────────────────
// Reads latest push from /waterData live, falls back to cache
router.get("/slave", async (req, res) => {
    try {
        const snap = await db.ref("/waterData").orderByKey().limitToLast(1).once("value");
        if (!snap.exists()) {
            const cache = readCache();
            return res.json({ success: true, source: "local_cache", data: cache.slave || {} });
        }
        let data = {};
        snap.forEach(child => { if (child.val().subTank) data = child.val().subTank; });
        res.json({ success: true, source: "firebase", data });
    } catch (err) {
        const cache = readCache();
        res.json({ success: true, source: "local_cache", data: cache.slave || {}, error: err.message });
    }
});

// ── GET /api/telemetry/history/:node?limit=50 ─────────────────────
// node: "master" | "slave"  (maps to mainTank / subTank history)
router.get("/history/:node", async (req, res) => {
    const { node } = req.params;
    if (!["master", "slave"].includes(node)) {
        return res.status(400).json({ success: false, message: "node must be 'master' or 'slave'" });
    }

    const firebasePath = node === "master"
        ? "/systemHistory/mainTank"
        : "/systemHistory/subTank";

    const limit = Math.min(parseInt(req.query.limit) || 50, 200);

    try {
        const snap = await db.ref(firebasePath)
            .orderByChild("timestamp")
            .limitToLast(limit)
            .once("value");

        const history = [];
        snap.forEach((child) => history.push({ id: child.key, ...child.val() }));

        res.json({
            success: true,
            node,
            count: history.length,
            data: history.reverse()   // newest first
        });
    } catch (err) {
        res.status(500).json({ success: false, message: err.message });
    }
});

// ── GET /api/telemetry/alerts ─────────────────────────────────────
// Reads active (unresolved) alerts from /systemAlerts
router.get("/alerts", async (req, res) => {
    try {
        const snap = await db.ref("/systemAlerts")
            .orderByChild("resolved").equalTo(false)
            .once("value");

        const alerts = [];
        snap.forEach((child) => alerts.push({ id: child.key, ...child.val() }));

        res.json({ success: true, count: alerts.length, data: alerts });
    } catch (err) {
        res.status(500).json({ success: false, message: err.message });
    }
});

// ── POST /api/telemetry/alerts/:id/resolve ────────────────────────
// Resolves an alert by updating its status in /systemAlerts
router.post("/alerts/:id/resolve", async (req, res) => {
    const { id } = req.params;
    try {
        await db.ref(`/systemAlerts/${id}`).update({
            resolved: true,
            resolvedAt: new Date().toISOString()
        });
        res.json({ success: true, message: `Alert ${id} resolved.` });
    } catch (err) {
        res.status(500).json({ success: false, message: err.message });
    }
});

module.exports = router;
