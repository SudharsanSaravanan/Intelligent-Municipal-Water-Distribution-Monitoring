/**
 * cache.helper.js — Local Cache Persistence Helpers
 * Reads/writes local_cache.json for offline resilience (rubric requirement)
 */

const fs = require("fs");
const path = require("path");

const CACHE_PATH = path.join(__dirname, "local_cache.json");

function readCache() {
    try {
        const raw = fs.readFileSync(CACHE_PATH, "utf8");
        return JSON.parse(raw);
    } catch {
        return { main_tank: {}, sub_tanks: {}, alerts: [], lastUpdated: null };
    }
}

function writeCache(data) {
    try {
        data.lastUpdated = new Date().toISOString();
        fs.writeFileSync(CACHE_PATH, JSON.stringify(data, null, 2), "utf8");
    } catch (err) {
        console.error("[Cache] Write error:", err.message);
    }
}

module.exports = { readCache, writeCache };
