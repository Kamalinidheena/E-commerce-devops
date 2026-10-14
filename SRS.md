# Software Requirements Specification (SRS)
## IncidentPulse — Real-Time Alerting and Incident Notification Platform
**Document Version:** 1.0.0  
**Date:** October 2026  
**Status:** Approved & Implemented  

---

## 1. Problem Statement
Modern digital platforms depend critically on continuous uptime and low-latency API responsiveness. However, engineering teams often face major blind spots:
1. Lack of clarity between socket-level reachability (HTTP 200) versus deep end-to-end business workflow execution.
2. Alert fatigue caused by noisy, transient single-check failures.
3. Incident duplication where continuing outages trigger repetitive alerts.
4. Opaque recovery tracking without accurate, automated timestamp calculation of actual downtime durations.
5. Inability to audit delivery attempts when webhook receivers fail or time out.

**IncidentPulse** solves this problem by providing a lightweight, beginner-maintainable, and mathematically honest health monitoring system with decoupled alert rules, SSRF security guards, bounded webhook retries, and automated recovery detection.

---

## 2. Project Objectives
- **Continuous Reliability Monitoring:** Perform periodic, automated HTTP/HTTPS health checks independently of active browser sessions.
- **Dual Independent Alert Rules:**
  - *Rule 1 (Endpoint Failure):* Detect complete socket death, DNS errors, timeouts, or unacceptable HTTP status codes with configurable consecutive sample smoothing.
  - *Rule 2 (Latency Threshold):* Identify degraded performance when response time in milliseconds exceeds limits, without conflating latency with complete outages.
- **Incident Lifecycle Management:** Record genuine start times, last updated times, resolution timestamps, and accurate elapsed downtime durations.
- **Accountable Notification Telemetry:** Deliver real JSON webhook payloads with bounded retries and exponential backoff, recording HTTP response codes and error messages.
- **Rigorous Data Integrity:** Enforce 100% authentic telemetry derived from actual socket connections and SQLite database states. Zero placeholder metrics, zero fake random counters.

---

## 3. User Roles & Personas
1. **Site Reliability Engineer (SRE) / DevOps Engineer:**
   - Configures monitored endpoints, check intervals, timeout limits, and failure thresholds.
   - Monitors live response-time trends and configures outbound webhook alerting destinations.
2. **Authorized Website Owner / Product Manager:**
   - Observes operational uptime, active incidents, and downtime durations.
   - Reviews audit history to understand past incidents and recovery events.
3. **Hackathon Evaluator / Auditor:**
   - Evaluates system behavior by stopping the local demo service, observing real incident triggers, restarting the service, and validating automatic recovery.

---

## 4. System Architecture

```
+----------------------------------------------------------------------------------+
|                              IncidentPulse Architecture                          |
+----------------------------------------------------------------------------------+
|                                                                                  |
|   +-----------------------+                    +-----------------------------+   |
|   |   Web Browser / UI    |<--- HTTP / JSON ---|  Flask Application Server   |   |
|   | (Light Yellow SaaS)   |                    |  - Blueprint Controllers    |   |
|   +-----------------------+                    |  - RESTful API Endpoints    |   |
|                                                +--------------+--------------+   |
|                                                               |                  |
|                                                +--------------+--------------+   |
|   +-----------------------+                    |  SQLite Database (WAL Mode) |   |
|   |  Monitoring Engine    |                    |  - services                 |   |
|   |  - Scheduler Loop     |<--- SQL Reads / ---|  - alert_rules              |   |
|   |  - SafeRedirectSession|     Writes         |  - check_results            |   |
|   |  - SSRF IP Validator  |                    |  - incidents                |   |
|   |  - Rule Evaluator     |                    |  - notification_logs        |   |
|   +-----------+-----------+                    |  - audit_logs               |   |
|               |                                +-----------------------------+   |
|               | HTTP Health Checks                                               |
|               v                                                                  |
|   +---------------------------------------+                                      |
|   | Target Endpoints / Demo Service       |                                      |
|   | (e.g. http://127.0.0.1:5050/health)   |                                      |
|   +---------------------------------------+                                      |
|                                                                                  |
+----------------------------------------------------------------------------------+
```

### Component Responsibilities:
- **`incidentpulse/monitoring/security.py`:** Validates URL structure, restricts allowed schemes to `http` and `https`, rejects embedded credentials, resolves hostnames to IPs, and blocks private/loopback/cloud metadata destinations unless explicitly authorized in local demo mode.
- **`incidentpulse/monitoring/checker.py`:** Performs timed HTTP requests using `requests.Session` with custom safe redirect re-validation, measures latency in milliseconds, checks HTTP response codes, and verifies optional workflow JSON assertions.
- **`incidentpulse/monitoring/rules.py`:** Evaluates check outcomes against independent alert rules (`ENDPOINT_FAILURE` and `LATENCY_THRESHOLD`), manages failure/success streaks, opens or resolves incidents, and dispatches notifications.
- **`incidentpulse/monitoring/incidents.py`:** Prevents duplicate open incidents for ongoing outages, computes duration as `resolved_at - started_at`, and writes immutable audit entries.
- **`incidentpulse/monitoring/notifications.py`:** Dispatches JSON POST requests to configured webhook endpoints with exponential backoff (e.g. 0.2s, 0.4s) and logs every delivery attempt.
- **`incidentpulse/monitoring/worker.py`:** Runs the periodic check cycle with per-service locks to prevent overlapping checks.

---

## 5. Functional Requirements

### 5.1 Endpoint Monitoring (REQ-MON-01 through 06)
- **REQ-MON-01:** System shall accept HTTP and HTTPS URLs with configurable check intervals (5s to 3600s) and timeouts (1s to 30s).
- **REQ-MON-02:** System shall record actual HTTP response codes, response times in milliseconds, and resolved IP addresses.
- **REQ-MON-03:** System shall reject connection attempts to private IP ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `169.254.0.0/16`, `169.254.169.254`) unless authorized local demo mode is enabled.
- **REQ-MON-04:** System shall support rate-limited manual check execution with a cooldown period (default: 3 seconds).
- **REQ-MON-05:** System shall maintain per-service execution locks to prevent overlapping concurrent checks.
- **REQ-MON-06:** System shall record check history for chronological retrieval and chart rendering.

### 5.2 Independent Alert Rules (REQ-RULE-01 through 05)
- **REQ-RULE-01:** System shall support Rule 1 (`ENDPOINT_FAILURE`) triggering on connection errors, timeouts, or unacceptable HTTP status codes.
- **REQ-RULE-02:** System shall support Rule 2 (`LATENCY_THRESHOLD`) triggering when measured response time exceeds threshold in milliseconds.
- **REQ-RULE-03:** Both rules shall track independent failure and success streaks without collision.
- **REQ-RULE-04:** An open incident of type `ENDPOINT_FAILURE` sets service status to `DOWN`. An open incident of type `LATENCY_THRESHOLD` sets status to `DEGRADED`.
- **REQ-RULE-05:** Subsequent checks during an active outage shall update `updated_at` but shall NEVER open duplicate incidents.

### 5.3 Automated Recovery (REQ-REC-01 through 03)
- **REQ-REC-01:** When a service achieves the configured number of consecutive successful checks (`recovery_threshold`), the open incident shall automatically transition to `RESOLVED`.
- **REQ-REC-02:** Incident duration shall be calculated using standard ISO UTC timestamps: `duration_seconds = (resolved_at - started_at).total_seconds()`.
- **REQ-REC-03:** A recovery notification shall be dispatched to the configured webhook channel.

### 5.4 Notification Delivery (REQ-NOTIF-01 through 04)
- **REQ-NOTIF-01:** System shall deliver alert and recovery payloads via HTTP POST in JSON format.
- **REQ-NOTIF-02:** Bounded retries (default: 3) with exponential backoff shall be executed on connection failure or non-2xx response.
- **REQ-NOTIF-03:** System shall record every delivery attempt in `notification_logs` (timestamp, attempt number, HTTP status code, error message).
- **REQ-NOTIF-04:** A manual test webhook endpoint (`POST /api/notifications/test`) shall allow administrators to verify webhook reachability on demand.

### 5.5 Audit & History (REQ-AUD-01)
- **REQ-AUD-01:** System shall record service creation, updates, deletions, incident states, and recovery events in `audit_logs`.

---

## 6. Non-Functional Requirements
- **NFR-PERF-01 (Check Latency):** Health check engine shall introduce less than 1ms overhead above raw network latency.
- **NFR-SEC-01 (SSRF Prevention):** All user URLs and redirect locations shall undergo DNS resolution and IP range validation.
- **NFR-SEC-02 (SQL Injection Protection):** All SQLite operations shall use parameterized queries.
- **NFR-REL-01 (Data Durability):** Database shall operate with SQLite Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) and enforced foreign keys (`PRAGMA foreign_keys = ON;`).
- **NFR-ACC-01 (Accessibility):** User interface shall comply with WCAG AA contrast standards and provide `@media (prefers-reduced-motion: reduce)` support.

---

## 7. Database Design & Schema

```sql
-- Core Services
CREATE TABLE services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    url TEXT NOT NULL,
    check_interval INTEGER NOT NULL DEFAULT 30,
    timeout INTEGER NOT NULL DEFAULT 5,
    expected_status INTEGER NOT NULL DEFAULT 200,
    follow_redirects INTEGER NOT NULL DEFAULT 1,
    allow_local_demo INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    current_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    last_checked_at TEXT,
    last_response_time_ms REAL,
    last_status_code INTEGER,
    last_error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Independent Alert Rules
CREATE TABLE alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    rule_type TEXT NOT NULL,
    threshold_value REAL NOT NULL,
    consecutive_threshold INTEGER NOT NULL DEFAULT 2,
    recovery_threshold INTEGER NOT NULL DEFAULT 2,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    current_failure_streak INTEGER NOT NULL DEFAULT 0,
    current_success_streak INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    UNIQUE(service_id, rule_type)
);

-- Check Telemetry History
CREATE TABLE check_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    http_status INTEGER,
    response_time_ms REAL,
    error_message TEXT,
    resolved_ip TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE
);

-- Incidents
CREATE TABLE incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    rule_id INTEGER,
    rule_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    started_at TEXT NOT NULL,
    resolved_at TEXT,
    duration_seconds REAL,
    notification_sent INTEGER NOT NULL DEFAULT 0,
    notification_status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    FOREIGN KEY (rule_id) REFERENCES alert_rules(id) ON DELETE SET NULL
);

-- Notification Config & Logs
CREATE TABLE notification_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_type TEXT NOT NULL DEFAULT 'WEBHOOK',
    webhook_url TEXT,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    timeout_seconds INTEGER NOT NULL DEFAULT 5,
    max_retries INTEGER NOT NULL DEFAULT 3,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE notification_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER,
    channel_type TEXT NOT NULL DEFAULT 'WEBHOOK',
    target_url TEXT NOT NULL,
    payload_preview TEXT,
    status TEXT NOT NULL,
    http_status INTEGER,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    error_message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE SET NULL
);

-- Audit Events
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    message TEXT NOT NULL,
    details_json TEXT,
    created_at TEXT NOT NULL
);
```

---

## 8. Verification & Acceptance Criteria
| Criteria | Implementation Status | Evidence |
| :--- | :---: | :--- |
| Application starts successfully | PASS | `run_server.py`, `wsgi.py` |
| Light-yellow visual identity & original doodles | PASS | `style.css`, `mascot.svg`, `empty_state.svg` |
| Independent alert rules (Failure & Latency) | PASS | `tests/test_rules.py` |
| Continuous failure deduplication | PASS | `test_endpoint_failure_rule_threshold` |
| Automatic recovery detection | PASS | `tests/test_recovery.py` |
| Accurate duration calculation | PASS | Real ISO timestamp delta computation |
| Webhook notification telemetry & bounded retries | PASS | `tests/test_notifications.py` |
| SSRF validation & IP restriction | PASS | `tests/test_security.py` |
| Honest empty states on fresh DB | PASS | `tests/test_services_api.py::test_api_state_empty_db` |
| 100% automated test pass rate | PASS | 36 / 36 tests passing in pytest |
