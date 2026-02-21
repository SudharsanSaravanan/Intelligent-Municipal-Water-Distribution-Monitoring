/**
 * telemetry.routes.js — REST API for HydroNet Telemetry
 *
 * Base path: /api/telemetry
 *
 * GET  /api/telemetry/latest           — full latest snapshot (from cache)
 * GET  /api/telemetry/master           — master tank live data
 * GET  /api/telemetry/slave            — slave/sub tank live data
 * GET  /api/telemetry/history/master   — master tank history (last N)
 * GET  /api/telemetry/history/slave    — slave tank history (last N)
 * GET  /api/telemetry/alerts           — active (unresolved) alerts
 * POST /api/telemetry/alerts/:id/resolve — resolve an alert
 */

const express = require("express");
const router = express.Router();
const { db } = require("../firebase");
const { readCache } = require("../database/cache.helper");

// ── GET /api/telemetry/latest ─────────────────────────────────
// Returns the full cached snapshot (fastest — no Firebase round-trip)
router.get("/latest", (req, res) => {
    const cache = readCache();
    res.json({
        success: true,
        source: "local_cache",
        data: cache,
        timestamp: new Date().toISOString()
    });
});

// ── GET /api/telemetry/master ─────────────────────────────────
router.get("/master", async (req, res) => {
    try {
        const snap = await db.ref("/waterSystem/status/master").once("value");
        if (!snap.exists()) {
            // fallback to cache
            const cache = readCache();
            return res.json({ success: true, source: "local_cache", data: cache.master || {} });
        }
        res.json({ success: true, source: "firebase", data: snap.val() });
    } catch (err) {
        const cache = readCache();
        res.json({ success: true, source: "local_cache", data: cache.master || {}, error: err.message });
    }
});

// ── GET /api/telemetry/slave ──────────────────────────────────
router.get("/slave", async (req, res) => {
    try {
        const snap = await db.ref("/waterSystem/status/slave").once("value");
        if (!snap.exists()) {
            const cache = readCache();
            return res.json({ success: true, source: "local_cache", data: cache.slave || {} });
        }
        res.json({ success: true, source: "firebase", data: snap.val() });
    } catch (err) {
        const cache = readCache();
        res.json({ success: true, source: "local_cache", data: cache.slave || {}, error: err.message });
    }
});

// ── GET /api/telemetry/history/:node?limit=50 ─────────────────
// node: "master" | "slave"
router.get("/history/:node", async (req, res) => {
    const { node } = req.params;
    if (!["master", "slave"].includes(node)) {
        return res.status(400).json({ success: false, message: "node must be 'master' or 'slave'" });
    }

    const limit = Math.min(parseInt(req.query.limit) || 50, 200);

    try {
        const snap = await db.ref(`/waterSystem/history/${node}`)
            .orderByChild("timestamp")
            .limitToLast(limit)
            .once("value");

        const history = [];
        snap.forEach((child) => history.push({ id: child.key, ...child.val() }));

        res.json({
            success: true,
            node,
            count: history.length,
            data: history.reverse() // newest first
        });
    } catch (err) {
        res.status(500).json({ success: false, message: err.message });
    }
});

// ── GET /api/telemetry/alerts ─────────────────────────────────
router.get("/alerts", async (req, res) => {
    try {
        const snap = await db.ref("/waterSystem/alerts")
            .orderByChild("resolved").equalTo(false)
            .once("value");

        const alerts = [];
        snap.forEach((child) => alerts.push({ id: child.key, ...child.val() }));

        res.json({ success: true, count: alerts.length, data: alerts });
    } catch (err) {
        res.status(500).json({ success: false, message: err.message });
    }
});

// ── POST /api/telemetry/alerts/:id/resolve ───────────────────
router.post("/alerts/:id/resolve", async (req, res) => {
    const { id } = req.params;
    try {
        await db.ref(`/waterSystem/alerts/${id}`).update({
            resolved: true,
            resolvedAt: new Date().toISOString()
        });
        res.json({ success: true, message: `Alert ${id} resolved.` });
    } catch (err) {
        res.status(500).json({ success: false, message: err.message });
    }
});

module.exports = router;
