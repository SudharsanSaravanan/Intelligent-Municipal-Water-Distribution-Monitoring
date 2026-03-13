require("dotenv").config();

const express = require("express");
const admin = require("firebase-admin");
const cors = require("cors");

const app = express();
app.use(cors());

const PORT = process.env.PORT || 5000;

// Firebase service account
const serviceAccount = require(process.env.FIREBASE_SERVICE_ACCOUNT);

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  databaseURL: process.env.FIREBASE_DATABASE_URL,
});

const db = admin.database();
const ref = db.ref("waterData");

// store latest data
let latestData = {};

console.log("Listening to new IoT data...\n");

// get latest existing key
ref.limitToLast(1).once("value", (snapshot) => {
  let lastKey = null;

  snapshot.forEach((child) => {
    lastKey = child.key;
  });

  // listen only for new data
  ref.orderByKey().startAfter(lastKey).on("child_added", (snapshot) => {
    latestData = snapshot.val();

    console.log("New IoT Data Received:");
    console.log(latestData);
    console.log("--------------------------");
  });
});

// API endpoint
app.get("/api", (req, res) => {
  res.json({
    status: "success",
    data: latestData,
  });
});

// start server
app.listen(PORT, () => {
  console.log(`API running on http://localhost:${PORT}/api`);
});