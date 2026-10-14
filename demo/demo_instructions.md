# IncidentPulse — Live Demonstration Guide

This guide details the exact steps to evaluate real-time health checks, failure detection, alerting, and automatic recovery.

---

## 1. Architecture Overview
- **IncidentPulse Dashboard & Engine**: Runs on port `5000` (`python run_server.py`).
- **Demo Monitored Service**: Runs as a separate process on port `5050` (`python demo/demo_service.py`).
- No hardcoded results or fake mock data are ever generated. All statuses and durations come from actual HTTP socket responses and SQLite timestamps.

---

## 2. Step-by-Step Demonstration

### Step 1: Start the Demo Service
Open Terminal 1:
```bash
python demo/demo_service.py
```
*Output confirms service is active at `http://127.0.0.1:5050/health`.*

### Step 2: Start IncidentPulse
Open Terminal 2:
```bash
python run_server.py
```
Open your browser to: `http://localhost:5000`

### Step 3: Configure a Webhook (Optional)
1. Navigate to **Notifications** (`/notifications`).
2. Enter your webhook URL (e.g. `https://webhook.site/...` or your team's Slack/Discord incoming webhook).
3. Click **"Send Test Notification"** to verify delivery. The delivery log will display the HTTP status code, timestamp, and attempts.

### Step 4: Register the Demo Service
1. Navigate to **Services** (`/services`).
2. Click **"+ Add Monitored Service"**.
3. Fill in:
   - **Name**: `Inventory API`
   - **URL**: `http://127.0.0.1:5050/health`
   - **Check Interval**: `5` seconds (for rapid demo feedback)
   - **Timeout**: `3` seconds
   - **Authorized Local Demo**: Checked (allows localhost/127.0.0.1 monitoring securely)
   - **Endpoint Failure Threshold**: `2` consecutive failures
   - **Latency Threshold**: `400` ms (consecutive: `2`)
4. Click **"Save Service"**.

*Notice: The service immediately begins in state `UNKNOWN` until the first real HTTP check finishes. Once the check succeeds, its status updates to `UP` with authentic measured latency (e.g., 4.2ms).*

### Step 5: Simulate Service Outage (Failure)
In Terminal 1 (Demo Service), press **Ctrl+C** to stop the demo server.

Observe the dashboard:
1. Within 5–10 seconds, check failures accumulate.
2. After 2 consecutive failures, an authentic **CRITICAL Incident** is opened:
   `Inventory API is DOWN (Connection refused)`.
3. If configured, a real webhook alert is dispatched and recorded in the Notification Center.
4. Note that subsequent failed checks do **NOT** open duplicate incidents; the single active incident tracks the duration continuously.

### Step 6: Simulate Service Recovery
In Terminal 1, restart the demo service:
```bash
python demo/demo_service.py
```

Observe the dashboard:
1. The next checks succeed (`HTTP 200`).
2. After 2 consecutive successful checks, IncidentPulse automatically marks the incident **RESOLVED**.
3. The exact incident duration (in seconds) is calculated from the database timestamps.
4. A recovery notification is dispatched.
5. Service status returns to **UP** with a recovery badge.

### Step 7: Demonstrate Latency Degradation (Rule 2)
With the demo service running, switch it to slow mode:
```bash
curl "http://127.0.0.1:5050/control/set_mode?mode=slow"
```
Or open `http://127.0.0.1:5050/control/set_mode?mode=slow` in your browser.

Observe:
1. Response time jumps to ~1500ms.
2. Latency alert rule opens a **WARNING / DEGRADED** incident:
   `Inventory API degraded: High Latency (>400ms)`.
3. Restore normal speed:
   ```bash
   curl "http://127.0.0.1:5050/control/set_mode?mode=normal"
   ```
4. Latency recovers to <10ms and the degraded incident is automatically resolved.

---

## 3. Verifying Data Persistence Across Restarts
1. Stop both IncidentPulse (`Ctrl+C` in Terminal 2) and Demo Service.
2. Restart IncidentPulse:
   ```bash
   python run_server.py
   ```
3. Open `http://localhost:5000/incidents` and `http://localhost:5000/audit`.
4. All recorded incidents, timestamps, durations, and audit histories are intact in SQLite.
