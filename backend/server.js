require("dotenv").config();

const express = require("express");
const admin = require("firebase-admin");
const cors = require("cors");

const app = express();
app.use(cors());

const PORT = process.env.PORT || 5000;
const databaseURL = process.env.FIREBASE_DB_URL;

// check env
if (!process.env.FIREBASE_SERVICE_ACCOUNT) {
  console.error("FIREBASE_SERVICE_ACCOUNT not found in .env");
  process.exit(1);
}

const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
serviceAccount.private_key = serviceAccount.private_key.replace(/\\n/g, "\n");

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  databaseURL: databaseURL,
});

const db = admin.database();
const ref = db.ref("waterData");

let latestData = {};

console.log("Listening to new IoT data...\n");

ref.limitToLast(1).once("value", (snapshot) => {
  let lastKey = null;

  snapshot.forEach((child) => {
    lastKey = child.key;
  });

  ref.orderByKey().startAfter(lastKey).on("child_added", (snapshot) => {
    latestData = snapshot.val();

    console.log("New IoT Data Received:");
    console.log(latestData);
    console.log("--------------------------");
  });
});

app.get("/api", (req, res) => {
  res.json({
    status: "success",
    data: latestData,
  });
});

app.listen(PORT, () => {
  console.log(`API running on http://localhost:${PORT}/api`);
});