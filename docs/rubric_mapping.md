# Rubric Mapping — Water Monitoring IoT System

| Rubric Criterion | Implementation | File(s) |
|---|---|---|
| **Embedded Layer — Sensor Reading** | HC-SR04 ultrasonic sensor reads water distance; level computed as `HEIGHT - distance` | `firmware/sub_tank_node/sub_tank.ino`, `firmware/main_tank_node/main_tank.ino` |
| **Embedded Layer — Wireless Communication** | ESP-NOW protocol for inter-node communication (sub → master); low-latency, WiFi-independent | Both `.ino` files |
| **Embedded Layer — Actuator Control** | Relay-controlled pump; auto ON < 20% / OFF > 80% threshold logic | `sub_tank.ino`, `main_tank.ino` |
| **Cloud Layer — Firebase RTDB** | Main node pushes sensor data to Firebase RTDB every 10 seconds (latest + history paths) | `firmware/main_tank_node/main_tank.ino`, `cloud/firebase/rules.json` |
| **Cloud Layer — Security Rules** | Role-based read/write rules; admin-only config writes | `cloud/firebase/rules.json` |
| **Backend — Node.js Server** | Express server with REST API + Socket.IO for live push | `backend/server.js` |
| **Backend — Firebase Listener** | `db.ref().on("value", ...)` listeners for main and sub tanks; event-driven processing | `backend/server.js` |
| **Backend — Local Cache Persistence** | `local_cache.json` updated on every Firebase event; fallback for offline mode | `backend/database/local_cache.json`, `backend/database/cache.helper.js` |
| **Backend — REST API** | 6 endpoints: `/latest`, `/main`, `/sub/:id`, `/history/:id`, `/alerts`, `/alerts/:id/resolve` | `backend/api/telemetry.routes.js` |
| **Backend — Alert Logic** | Automatic alert generation for critical/low levels; alert push to Firebase + WebSocket clients | `backend/server.js` |
| **Frontend — Dashboard UI** | Real-time dashboard with animated tank visuals, KPI cards, Chart.js history, alert panel | `frontend/index.html`, `frontend/css/style.css` |
| **Frontend — Live Updates** | Socket.IO client receives tank updates without page refresh | `frontend/js/app.js` |
| **Frontend — REST API Consumption** | `app.js` fetches `/latest`, `/history`, `/alerts` on load and every 15s fallback | `frontend/js/app.js` |
| **Frontend — Alert Management** | View and resolve alerts from dashboard; resolved via REST `POST` | `frontend/js/app.js` |
| **Documentation** | Architecture diagram, data flow, rubric mapping | `docs/` folder |

## System Architecture Summary

```
[Sub Tank Node (ESP32)]
    Sensors → ESP-NOW → [Main Tank Node (ESP32)]
                              |
                        WiFi + HTTPS
                              |
                     [Firebase RTDB]
                              |
               [Node.js Backend Server]
               ├── Firebase Listener (real-time)
               ├── local_cache.json (persistence)
               ├── REST API  (/api/telemetry/*)
               └── WebSocket (Socket.IO)
                              |
                  [Frontend Dashboard]
                  ├── Socket.IO (live)
                  └── REST API (fallback)
```

## Data Flow

1. **Sub tank node** reads ultrasonic sensor every 5s
2. Level data sent via **ESP-NOW** to main tank node
3. Main tank node reads its own sensor, combines data, uploads to **Firebase RTDB** every 10s
4. **Node.js backend** listens via Firebase Admin SDK `.on("value")` events
5. Backend updates **local_cache.json** on every event
6. Backend pushes update to frontend via **Socket.IO**
7. Frontend also polls REST API every 15s as fallback
8. **Alerts** are auto-generated on threshold breach, stored in Firebase, pushed to dashboard
