# IncidentPulse — Real-Time Health & Alerting Platform

[![Tests](https://img.shields.io/badge/tests-36%20passed-brightgreen.svg)](#running-automated-tests)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Design](https://img.shields.io/badge/visual%20identity-warm%20ivory%20%26%20light%20yellow-ffe680.svg)](#visual-identity)

**IncidentPulse** is an authentic, lightweight website and application health monitoring platform. Designed for engineers and website owners who require honest operational telemetry, clear incident lifecycles, SSRF-hardened endpoint checking, and transparent webhook alerting.

---

## 🌟 Key Features

1. **Independent Dual Alert Rules:**
   - **Rule 1 (Endpoint Failure):** Detects connection refusal, DNS errors, request timeouts, and unexpected HTTP status codes with configurable consecutive failure thresholds.
   - **Rule 2 (Latency Threshold):** Measures actual HTTP response time in milliseconds and opens a `DEGRADED` warning when latency limits are exceeded.
   - Both rules maintain independent identities and counters—preventing latency warnings from overwriting or misrepresenting outage incidents.
2. **Automated Incident Lifecycle & Accurate Duration:**
   - Detects outage beginnings and records precise UTC timestamps.
   - Deduplicates ongoing continuous outages so that no duplicate open incidents are generated.
   - Automatically detects recovery when consecutive successful checks occur.
   - Calculates exact downtime durations from real database timestamps (`(resolved_at - started_at).total_seconds()`).
3. **Accountable Webhook Notifications:**
   - Real JSON webhook POST dispatches with exponential backoff and bounded retries.
   - Complete attempt logging tracking HTTP response codes, timestamps, and error messages.
   - Manual test webhook trigger (`POST /api/notifications/test`) for immediate verification.
4. **SSRF & Security Hardening:**
   - Rejects non-HTTP/HTTPS schemes, embedded URL credentials, and malformed destinations.
   - Resolves hostnames to IP addresses and enforces strict RFC 1918 private, loopback, link-local, and cloud metadata (`169.254.169.254`) blocking.
   - Custom `SafeRedirectSession` re-validates each redirect target against SSRF policy before connection.
   - Authorized local demo mode permits local loopback testing strictly on designated ports (5000–9999).
5. **Light Yellow Aesthetic & Hand-Drawn SVG Doodles:**
   - Warm ivory `#FFFDF4`, soft yellow `#FFF4BF`, and light yellow `#FFE680` brand tokens.
   - Original pulse-line mascot, decorative sparkles, doodle servers, and celebratory recovery badge.
   - Zero-dependency Vanilla JS Canvas response-time chart that works 100% offline.
6. **Strict Telemetry Honesty:**
   - Absolutely no `Math.random()`, no fake uptime percentages, and no mock data in production mode.
   - Clean databases display honest zero counts and attractive empty states.

---

## 🏗️ Technology Stack

- **Backend:** Python 3.11+ / 3.14+, Flask 3.1, Requests 2.32
- **Database:** SQLite 3 with Write-Ahead Logging (WAL) and foreign key constraints enabled
- **Frontend:** Semantic HTML5, Custom CSS3 Design System, Vanilla JavaScript (ES6+)
- **Charting:** Responsive HTML5 Canvas engine (zero CDN or external NPM dependencies)
- **Testing:** pytest 9.1 with Flask Test Client, unit mocks, and integration suites
- **Deployment:** Gunicorn, Nginx reverse proxy, Linux systemd unit supervisors

---

## 📁 Repository Structure

```
c:\Users\kamal\Desktop\E-commerce 2\
├── incidentpulse/
│   ├── __init__.py           # Package init
│   ├── app.py                # Flask application factory
│   ├── config.py             # Environment configuration
│   ├── database.py           # SQLite connection factory & migrations
│   ├── models.py             # Repository layer & data access
│   ├── monitoring/
│   │   ├── security.py       # SSRF validator, DNS resolver, private IP blocking
│   │   ├── checker.py        # HTTP health check engine & timer
│   │   ├── rules.py          # Independent alert rule evaluation
│   │   ├── incidents.py      # Incident lifecycle & duration computation
│   │   ├── notifications.py  # Webhook dispatcher & retry mechanism
│   │   └── worker.py         # Dedicated background check scheduler
│   ├── routes/
│   │   ├── api.py            # RESTful JSON API (/api/services, /api/incidents, etc.)
│   │   └── web.py            # Jinja HTML page controllers
│   ├── templates/            # Semantic HTML5 Jinja templates
│   └── static/               # CSS styles, Canvas chart engine, SVG doodles
├── demo/
│   ├── demo_service.py       # Standalone test service with controllable modes
│   └── demo_instructions.md  # Step-by-step evaluator instructions
├── deploy/
│   ├── nginx.conf            # Production Nginx reverse-proxy config
│   ├── incidentpulse.service # Gunicorn systemd unit file
│   └── incidentpulse-worker.service # Background worker systemd unit file
├── tests/                    # 36 automated test cases
├── run_server.py             # Development server runner
├── run_worker.py             # Standalone worker runner
├── wsgi.py                   # Production WSGI entry point
├── requirements.txt          # Python dependencies
├── SRS.md                    # Software Requirements Specification
└── README.md                 # Project documentation
```

---

## 🚀 Quickstart & Local Setup

### 1. Prerequisites
- Python 3.11 or higher installed (`python --version`)
- pip installed

### 2. Installation
Clone or navigate to the project directory and install dependencies:
```bash
cd "c:\Users\kamal\Desktop\E-commerce 2"
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy the configuration template:
```bash
cp .env.example .env
```
Default values in `.env.example` are pre-tuned for local hackathon evaluation.

---

## 🧪 Running Automated Tests

Run the full automated test suite:
```bash
python -m pytest -v
```

### Test Coverage Highlights (36 Tests):
- `tests/test_checker.py`: HTTP 200, HTTP 500, Connection Refusal, Timeouts, Invalid URLs, JSON Workflow assertions.
- `tests/test_rules.py`: Consecutive failure threshold, deduplication during continuous outage, recovery threshold, independent latency rule.
- `tests/test_recovery.py`: Complete end-to-end failure detection, incident creation, automatic recovery, and duration calculation.
- `tests/test_notifications.py`: Webhook delivery success, HTTP 500 retries, timeouts, unconfigured notifications.
- `tests/test_security.py`: RFC 1918 private IP rejection, cloud metadata blocking, localhost restrictions, dangerous ports, redirect re-validation.
- `tests/test_services_api.py`: Services CRUD, input bounds, rate limit cooldown, honest empty-state metrics.
- `tests/test_web_routes.py`: Jinja HTML rendering for all dashboards and management pages.

---

## 🎬 Live Demonstration Workflow

Follow these exact steps to demonstrate real-time failure detection and automatic recovery to an evaluator:

### Step 1: Start the Demo Service
In Terminal 1:
```bash
python demo/demo_service.py
```
*The demo service runs at `http://127.0.0.1:5050/health`.*

### Step 2: Start IncidentPulse Web Application
In Terminal 2:
```bash
python run_server.py
```
*Open `http://localhost:5000` in your web browser.*

### Step 3: Register the Demo Service
1. Click **"+ Add Service"**.
2. Enter:
   - **Name:** `Inventory API`
   - **URL:** `http://127.0.0.1:5050/health`
   - **Check Interval:** `5` seconds
   - **Timeout:** `3` seconds
   - **Authorized Local Demo:** Checked
   - **Failures Before Alert:** `2`
   - **Latency Threshold:** `400` ms
3. Click **"Save Service"**.
4. Observe the initial state is `UNKNOWN` until the first check executes, then turns `UP` with authentic measured latency.

### Step 4: Simulate Failure (Process Outage)
In Terminal 1 (Demo Service), press **Ctrl+C** to stop the process.
1. Watch the dashboard: check failures accumulate.
2. After 2 consecutive failures, a **CRITICAL Incident** (`Inventory API is DOWN`) opens.
3. Observe that continuing checks do **NOT** duplicate open incidents.

### Step 5: Simulate Recovery
In Terminal 1, restart the demo service:
```bash
python demo/demo_service.py
```
1. Within 5–10 seconds, checks succeed with HTTP 200.
2. After 2 successful checks, IncidentPulse automatically marks the incident **RESOLVED**.
3. The exact duration (e.g. `24.8s`) is displayed on the dashboard and in the Incident Center.

### Step 6: Simulate High Latency (Rule 2)
In your browser or terminal, trigger slow mode:
```bash
curl "http://127.0.0.1:5050/control/set_mode?mode=slow"
```
1. Latency jumps to ~1500ms.
2. A **WARNING / DEGRADED** incident opens.
3. Restore normal speed:
   ```bash
   curl "http://127.0.0.1:5050/control/set_mode?mode=normal"
   ```
4. Latency recovers to <10ms and the degraded incident resolves automatically.

---

## 🌐 API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | System health & database connection status |
| `GET` | `/api/state` | Live aggregated dashboard metrics |
| `GET` | `/api/services` | List all monitored services |
| `POST` | `/api/services` | Register a new health check endpoint |
| `GET` | `/api/services/<id>` | Full service details, rules, and checks |
| `PATCH`| `/api/services/<id>` | Update service settings or pause/resume |
| `DELETE`|`/api/services/<id>` | Delete service and cascaded entities |
| `POST` | `/api/services/<id>/check` | Trigger immediate manual check (rate-limited) |
| `GET` | `/api/services/<id>/checks` | Chronological check history for telemetry chart |
| `GET` | `/api/incidents` | List incidents (filter by `status`, `severity`, `service_id`) |
| `GET` | `/api/incidents/<id>` | Incident detail and webhook delivery logs |
| `GET` | `/api/notifications` | Webhook settings and recent delivery logs |
| `POST` | `/api/notifications/config` | Update webhook URL and retry settings |
| `POST` | `/api/notifications/test` | Dispatch synthetic test notification |
| `GET` | `/api/audit` | Chronological audit trail of system events |

---

## 🔒 Security & SSRF Policy

1. **Protocol Restriction:** Only `http://` and `https://` schemes are supported.
2. **Credential Sanitization:** URLs with embedded credentials (e.g. `http://user:pass@host`) are rejected.
3. **IP Range Restrictions:** Hostnames are resolved to IP addresses via `socket.getaddrinfo`. The following ranges are blocked:
   - Loopback: `127.0.0.0/8`, `::1`
   - Private: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
   - Link-local: `169.254.0.0/16`, `fe80::/10`
   - Cloud Metadata: `169.254.169.254` (AWS, Google Cloud, Azure)
   - Multicast & Broadcast: `224.0.0.0/4`, `255.255.255.255`
4. **Safe Redirect Interception:** When `follow_redirects=True`, each redirect step is re-validated through the SSRF filter before connecting.
5. **Authorized Demo Mode:** When `allow_local_demo=True` is explicitly checked on a service AND `ALLOW_LOCAL_DEMO=true` in `.env`, localhost monitoring is permitted strictly on ports 5000–9999 for local hackathon evaluation.

---

## 🚢 Production Linux Deployment

To deploy IncidentPulse on a production Linux server (Ubuntu 22.04 / 24.04):

### 1. Setup Application Directory
```bash
sudo mkdir -p /var/www/incidentpulse
sudo chown -R www-data:www-data /var/www/incidentpulse
sudo git clone <repo_url> /var/www/incidentpulse
cd /var/www/incidentpulse
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with SECRET_KEY and ALLOW_LOCAL_DEMO=false
```

### 2. Configure systemd Services
Copy the provided unit definitions:
```bash
sudo cp deploy/incidentpulse.service /etc/systemd/system/
sudo cp deploy/incidentpulse-worker.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now incidentpulse
sudo systemctl enable --now incidentpulse-worker
```

### 3. Configure Nginx Reverse Proxy
```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/incidentpulse
sudo ln -s /etc/nginx/sites-available/incidentpulse /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## ⚠️ Known Limitations & Educational Notes

1. **Endpoint Availability vs. Workflow Health:**
   A passing HTTP 200 response on `/health` verifies that the target web server process is reachable and responding. It does **not** prove that complex user journeys (user checkout, Stripe payment processing, asynchronous background queue workers, database lock states) are functioning properly. IncidentPulse includes JSON field assertion support to begin bridging this gap.
2. **Webhook Acceptance vs. Human Attention:**
   A recorded `SUCCESS` delivery status confirms that the receiving webhook gateway returned an HTTP 2xx response. It cannot prove that a human engineer has seen or acknowledged the alert.
3. **In-Process vs. Standalone Worker:**
   In simple local single-command development, `run_server.py` starts a background thread. In multi-worker production (e.g. Gunicorn with 4 workers), you must run `run_worker.py` as an independent supervisor process (`incidentpulse-worker.service`) to ensure exactly one monitoring scheduler instance runs.

---

## 📄 License
MIT License. Created for Dev Sprint'26 | Problem 17: Alerting and Incident Notification System.
