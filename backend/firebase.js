/**
 * firebase.js — Firebase Admin SDK Init
 * Project: hydronet-monitor
 * RTDB URL: https://hydronet-monitor-default-rtdb.firebaseio.com
 */

const admin = require("firebase-admin");
const path = require("path");

// Service account key file (download from Firebase Console →
// Project Settings → Service Accounts → Generate New Private Key)
const serviceAccountPath =
    process.env.FIREBASE_KEY_PATH ||
    path.join(__dirname, "serviceAccountKey.json");

let serviceAccount;
try {
    serviceAccount = require(serviceAccountPath);
} catch (err) {
    console.error("[Firebase] ⚠️  serviceAccountKey.json not found at:", serviceAccountPath);
    console.error("  → Download it from Firebase Console > Project Settings > Service Accounts");
    process.exit(1);
}

if (!admin.apps.length) {
    admin.initializeApp({
        credential: admin.credential.cert(serviceAccount),
        databaseURL: process.env.FIREBASE_DATABASE_URL ||
            "https://hydronet-monitor-default-rtdb.firebaseio.com"
    });
}

const db = admin.database();

// Connection health indicator
db.ref(".info/connected").on("value", (snap) => {
    if (snap.val() === true) {
        console.log("[Firebase] ✅  Connected to hydronet-monitor RTDB");
    } else {
        console.warn("[Firebase] ⚠️   Disconnected — attempting to reconnect...");
    }
});

module.exports = { admin, db };
