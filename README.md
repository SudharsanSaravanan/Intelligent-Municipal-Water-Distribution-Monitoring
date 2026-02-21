# Intelligent Municipal Water Distribution Monitoring

> A full-stack IoT system for real-time water quality and tank level monitoring using **ESP32**, **ESP-NOW**, **Firebase RTDB**, **Node.js**, and a live animated web dashboard.

[![Firebase](https://img.shields.io/badge/Firebase-RTDB-orange?logo=firebase)](https://firebase.google.com/)
[![ESP32](https://img.shields.io/badge/Hardware-ESP32-blue)](https://www.espressif.com/)
[![Node.js](https://img.shields.io/badge/Backend-Node.js-green?logo=node.js)](https://nodejs.org/)

---

## Table of Contents 

1. [Project Overview](#-project-overview)
2. [Project Structure](#-project-structure)
3. [Hardware & Pin Configuration](#-hardware--pin-configuration)
4. [System Architecture](#-system-architecture)
5. [Firebase Setup](#-firebase-setup)
6. [Firmware Setup (ESP32)](#-firmware-setup-esp32)
7. [Backend Setup (Node.js)](#-backend-setup-nodejs)
8. [Frontend Setup (Dashboard)](#-frontend-setup-dashboard)
9. [REST API Reference](#-rest-api-reference)
10. [Real-Time Events](#-real-time-events-socketio)
11. [Environment Variables](#-environment-variables)

---

## Project Overview

This system monitors water distribution across **two tanks** — a **Main Tank (Master ESP32)** and a **Sub Tank (Slave ESP32)**. The slave collects local sensor data and sends it wirelessly via **ESP-NOW** to the master. The master reads its own sensors, combines both datasets, and uploads everything to **Firebase RTDB** every 5 seconds via HTTPS. A **Node.js backend** listens to Firebase in real time, caches data locally, and serves it to a **live web dashboard** via REST API and **Socket.IO**.

### Key Metrics Monitored

| Metric | Sensor | Node |
|---|---|---|
| Water Level (cm / %) | Ultrasonic HC-SR04 | Both |
| Water TDS (ppm) | TDS Analog Probe | Both |
| Water Quality | Computed from TDS | Both |
| Flow Rate Line 1 (L/min) | Flow Sensor | Sub Tank |
| Flow Rate Line 2 (L/min) | Flow Sensor | Sub Tank |
| Relay / Valve Control | Relay Module | Sub Tank |

---

## Project Structure

```
Intelligent-Municipal-Water-Distribution-Monitoring/
│
├── firmware/                          # ── EMBEDDED LAYER ──────────────────
│   ├── sub_tank_node/
│   │   └── sub_tank.ino               # Slave ESP32 — ESP-NOW sender
│   │                                  # Sensors: Flow×2, TDS, Ultrasonic, Relay×2
│   └── main_tank_node/
│       └── main_tank.ino              # Master ESP32 — ESP-NOW receiver + Firebase
│                                      # Sensors: TDS, Ultrasonic | WiFi: 11i
│
├── cloud/                             # ── FIREBASE LAYER ───────────────────
│   └── firebase/
│       ├── rules.json                 # RTDB security rules
│       └── sample_data.json           # Reference database structure
│
├── backend/                           # ── SERVER LAYER ─────────────────────
│   ├── server.js                      # Express + Socket.IO + Firebase listener
│   ├── firebase.js                    # Firebase Admin SDK initializer
│   ├── database/
│   │   ├── local_cache.json           # Local offline persistence (rubric)
│   │   └── cache.helper.js            # Cache read/write helpers
│   ├── api/
│   │   └── telemetry.routes.js        # REST API endpoints
│   ├── .env                           # Your environment variables (git-ignored)
│   ├── .env.example                   # Template — copy to .env
│   ├── serviceAccountKey.json         # Firebase service account (git-ignored)
│   └── package.json
│
├── frontend/                          # ── DASHBOARD LAYER ──────────────────
│   ├── index.html                     # Main dashboard page
│   ├── css/
│   │   └── style.css                  # Dark glassmorphism UI styles
│   └── js/
│       └── app.js                     # Socket.IO + REST + Chart.js client
│
├── docs/
│   └── rubric_mapping.md              # Criterion → implementation mapping
│
├── .gitignore
└── README.md
```

---

## Hardware & Pin Configuration

### Sub Tank Node — Slave ESP32

| Component | GPIO | Notes |
|---|---|---|
| Flow Sensor 1 | **GPIO 17** | Interrupt-driven pulse count |
| Flow Sensor 2 | **GPIO 16** | Interrupt-driven pulse count |
| Relay 1 | **GPIO 27** | Controls valve / pump line 1 |
| Relay 2 | **GPIO 26** | Controls valve / pump line 2 |
| TDS Sensor | **GPIO 34** | ADC1_CH6 — analog probe |
| Ultrasonic TRIG | **GPIO 15** | HC-SR04 trigger |
| Ultrasonic ECHO | **GPIO 2** | HC-SR04 echo |

> ADC reference: **3.3 V**, 12-bit resolution (0–4095)

### Main Tank Node — Master ESP32

| Component | GPIO | Notes |
|---|---|---|
| TDS Sensor | **GPIO 34** | ADC1_CH6 — analog probe |
| Ultrasonic TRIG | **GPIO 26** | HC-SR04 trigger |
| Ultrasonic ECHO | **GPIO 27** | HC-SR04 echo |

> WiFi SSID: **11i** | Firebase Project: **hydronet-monitor**

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EMBEDDED LAYER                               │
│                                                                     │
│  ┌─────────────────────┐         ┌─────────────────────────────┐   │
│  │  SUB TANK (Slave)   │         │    MAIN TANK (Master)       │   │
│  │  ─────────────────  │ ESP-NOW │  ──────────────────────── ─ │   │
│  │  • Flow Sensor 1&2  │ ──────► │  • TDS (GPIO 34)            │   │
│  │  • TDS (GPIO 34)    │         │  • Ultrasonic (GPIO 26/27)  │   │
│  │  • Ultrasonic       │         │  • Receives slave payload   │   │
│  │  • Relay 1&2        │         │  • Uploads to Firebase RTDB │   │
│  └─────────────────────┘         └──────────────┬──────────────┘   │
└─────────────────────────────────────────────────┼───────────────────┘
                                                  │ HTTPS PUT
                                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       CLOUD LAYER (Firebase RTDB)                   │
│                                                                     │
│   /waterSystem/status/master  →  { tdsPpm, waterQuality,           │
│   /waterSystem/status/slave      tankLevelPercent, tankLevelCm,    │
│   /waterSystem/history/*         flow1_Lmin, flow2_Lmin }           │
│   /waterSystem/alerts            (updated every 5 seconds)          │
└─────────────────────────────────────────────────┬───────────────────┘
                                                  │ Firebase Admin SDK
                                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       SERVER LAYER (Node.js)                        │
│                                                                     │
│   server.js  ┌─────────────────┐  ┌──────────────────────────┐    │
│   ──────────►│ Firebase        │  │ local_cache.json          │    │
│              │ .on("value")    │─►│ (offline persistence)     │    │
│              └────────┬────────┘  └──────────────────────────┘    │
│                       │                                             │
│              ┌────────▼────────┐  ┌──────────────────────────┐    │
│              │ REST API        │  │ Socket.IO WebSocket       │    │
│              │ /api/telemetry  │  │ → master_update           │    │
│              │ /health         │  │ → slave_update            │    │
│              └─────────────────┘  │ → alert                   │    │
│                                   └──────────────────────────┘    │
└─────────────────────────────────────────────────┬───────────────────┘
                                                  │ HTTP + WebSocket
                                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     DASHBOARD LAYER (Browser)                       │
│                                                                     │
│   KPI Cards · Animated Tanks · TDS Quality · Flow Rates            │
│   Chart.js History · Alert Panel · Socket.IO Live Updates          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Firebase Setup

### Step 1 — Create the project

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create (or open) project: **`hydronet-monitor`**
3. Navigate to **Build → Realtime Database → Create database**
4. Choose **Start in test mode** (you'll apply rules next)
5. Region: `asia-south1` (or closest to you)

### Step 2 — Apply security rules

1. In Firebase Console → Realtime Database → **Rules**
2. Paste the contents of [`cloud/firebase/rules.json`](./cloud/firebase/rules.json)
3. Click **Publish**

### Step 3 — Service account key

1. Firebase Console → Project Settings → **Service Accounts**
2. Click **Generate New Private Key** → Download JSON
3. Save the file as **`backend/serviceAccountKey.json`**

> **Never commit `serviceAccountKey.json` to git.** It is already listed in `.gitignore`.

### Step 4 — Import sample data (optional)

To pre-populate Firebase with the reference structure:

1. Firebase Console → Realtime Database → **⋮ (menu) → Import JSON**
2. Upload [`cloud/firebase/sample_data.json`](./cloud/firebase/sample_data.json)

---

## Firmware Setup (ESP32)

### Prerequisites

- [Arduino IDE 2.x](https://www.arduino.cc/en/software) or [VS Code + PlatformIO](https://platformio.org/)
- ESP32 board package installed (`esp32` by Espressif)
- No extra libraries needed — uses built-in `WiFi`, `esp_now`, `HTTPClient`, `WiFiClientSecure`

### Step 1 — Flash the Slave (Sub Tank) first

1. Open `firmware/sub_tank_node/sub_tank.ino` in Arduino IDE
2. Update the **master ESP32 MAC address** in the sketch:
   ```cpp
   uint8_t masterMAC[] = { 0xXX, 0xXX, 0xXX, 0xXX, 0xXX, 0xXX };
   ```
3. Select board: **ESP32 Dev Module**
4. Upload to the **slave ESP32**

> To find the master MAC: upload a temporary sketch with `Serial.println(WiFi.macAddress())` to the master board and read it from Serial Monitor.

### Step 2 — Flash the Master (Main Tank)

1. Open `firmware/main_tank_node/main_tank.ino` in Arduino IDE
2. Verify these constants match your setup:
   ```cpp
   const char* WIFI_SSID     = "11i";
   const char* WIFI_PASSWORD = "senu@123";
   const char* FIREBASE_HOST = "hydronet-monitor-default-rtdb.firebaseio.com";
   const float TANK_HEIGHT_CM = 100.0;  // ← set your actual tank height
   ```
3. Select board: **ESP32 Dev Module**
4. Upload to the **master ESP32**

### Step 3 — Verify on Serial Monitor

Open Serial Monitor (baud: `115200`). You should see:

```
[MASTER NODE] HydroNet Monitor — Booting...
[WiFi] MASTER MAC: XX:XX:XX:XX:XX:XX
[ESP-NOW] Receiver ready — listening for SLAVE...
[WiFi] Connected. IP: 192.168.x.x
[Firebase] Uploading...
[Firebase] Response code: 200
```

---

## 🖥️ Backend Setup (Node.js)

### Prerequisites

- [Node.js v18+](https://nodejs.org/) installed
- `backend/serviceAccountKey.json` already in place (see Firebase Setup)

### Step 1 — Install dependencies

```bash
cd backend
npm install
```

### Step 2 — Configure environment

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Open `.env` and verify:

```env
PORT=3000
FIREBASE_DATABASE_URL=https://hydronet-monitor-default-rtdb.firebaseio.com
FIREBASE_KEY_PATH=./serviceAccountKey.json
```

### Step 3 — Start the server

```bash
# Development (auto-restart on file changes)
npm run dev

# Production
npm start
```

### Step 4 — Verify it's running

Open a browser or run:

```bash
curl http://localhost:3000/health
```

Expected response:
```json
{
  "status": "OK",
  "service": "HydroNet Monitor Backend",
  "uptime": "5s"
}
```

---

## Frontend Setup (Dashboard)

The frontend is a **static HTML/CSS/JS** application — no build step required.

### Option A — Open directly (simplest)

```
Double-click  →  frontend/index.html
```

Or via File Explorer: right-click `index.html` → **Open with → Chrome/Edge**

### Option B — VS Code Live Server (recommended)

1. Install the [Live Server extension](https://marketplace.visualstudio.com/items?itemName=ritwickdey.LiveServer) in VS Code
2. Right-click `frontend/index.html` → **Open with Live Server**
3. Dashboard opens at `http://127.0.0.1:5500/frontend/index.html`

> Make sure the backend is running on port **3000** before opening the dashboard, so Socket.IO connects immediately.

### What you'll see

| Section | Description |
|---|---|
| **Dashboard** | KPI cards + animated tank visuals + quality badges |
| **History** | Chart.js line chart — Level % and TDS ppm over time |
| **Alerts** | Active alerts with one-click resolve |

---

## REST API Reference

Base URL: `http://localhost:3000`

| Method | Endpoint | Description | Response Source |
|---|---|---|---|
| `GET` | `/health` | Server health check | Live |
| `GET` | `/api/telemetry/latest` | Full snapshot (master + slave) | Local cache |
| `GET` | `/api/telemetry/master` | Main tank latest reading | Firebase → cache fallback |
| `GET` | `/api/telemetry/slave` | Sub tank latest reading | Firebase → cache fallback |
| `GET` | `/api/telemetry/history/master?limit=50` | Main tank history (newest first) | Firebase |
| `GET` | `/api/telemetry/history/slave?limit=50` | Sub tank history (newest first) | Firebase |
| `GET` | `/api/telemetry/alerts` | All unresolved alerts | Firebase |
| `POST` | `/api/telemetry/alerts/:id/resolve` | Resolve an alert by ID | Firebase |

### Sample Response — `/api/telemetry/latest`

```json
{
  "success": true,
  "source": "local_cache",
  "data": {
    "master": {
      "tdsPpm": 280,
      "waterQuality": "Good",
      "tankLevelPercent": 75,
      "tankLevelCm": 120
    },
    "slave": {
      "flow1_Lmin": 8.5,
      "flow2_Lmin": 6.2,
      "tdsPpm": 260,
      "waterQuality": "Good Quality Water",
      "waterQualityCode": 2,
      "tankLevelPercent": 60,
      "tankLevelCm": 65
    }
  },
  "timestamp": "2026-02-21T06:04:29.000Z"
}
```

---

## Real-Time Events (Socket.IO)

Connect to: `ws://localhost:3000`

| Event | Direction | Payload |
|---|---|---|
| `initial_state` | Server → Client | Full cached state on new connection |
| `master_update` | Server → Client | `{ tdsPpm, waterQuality, tankLevelPercent, tankLevelCm, timestamp }` |
| `slave_update` | Server → Client | `{ flow1_Lmin, flow2_Lmin, tdsPpm, waterQuality, waterQualityCode, tankLevelPercent, tankLevelCm, timestamp }` |
| `alert` | Server → Client | `{ nodeId, type, message, level, timestamp }` |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `3000` | Backend server port |
| `FIREBASE_DATABASE_URL` | — | Your Firebase RTDB URL |
| `FIREBASE_KEY_PATH` | `./serviceAccountKey.json` | Path to service account key |
| `CORS_ORIGIN` | `http://localhost:5500` | Allowed frontend origin |

---

## TDS Water Quality Scale

| TDS Range (ppm) | Quality Status | Badge Colour |
|---|---|---|
| 0 – 50 | Very Low Minerals (RO Water) | 🟡 Yellow |
| 51 – 150 | Excellent Drinking Water | 🟢 Green |
| 151 – 300 | Good Quality Water | 🔵 Blue |
| 301 – 500 | Average — Not Recommended | 🟡 Yellow |
| > 500 | BAD Water (High TDS) | 🔴 Red |

---
