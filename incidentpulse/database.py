import os
import sqlite3
from pathlib import Path
from typing import Optional, Any

_DB_PATH: Optional[str] = None

def set_db_path(db_path: Optional[str]):
    """Sets the active database path."""
    global _DB_PATH
    _DB_PATH = db_path
    if db_path and db_path != ":memory:":
        parent_dir = Path(db_path).parent
        parent_dir.mkdir(parents=True, exist_ok=True)

def get_db_path() -> str:
    """Returns the current database path."""
    global _DB_PATH
    if _DB_PATH is None:
        from incidentpulse.config import Config
        set_db_path(Config.DB_PATH)
    return _DB_PATH

def get_db_connection() -> sqlite3.Connection:
    """Creates a new database connection with foreign keys enabled."""
    conn = sqlite3.connect(get_db_path(), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def init_db(db_path: Optional[str] = None):
    """Initializes database tables, indices, and constraints."""
    if db_path is not None:
        set_db_path(db_path)
        
    conn = get_db_connection()
    try:
        with conn:
            # 1. Services table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
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
            """)

            # 2. Alert Rules table (Independent rules: ENDPOINT_FAILURE, LATENCY_THRESHOLD)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_rules (
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
            """)

            # 3. Check Results table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS check_results (
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
            """)

            # 4. Incidents table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
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
            """)

            # 5. Notification Configs table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_type TEXT NOT NULL DEFAULT 'WEBHOOK',
                webhook_url TEXT,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                timeout_seconds INTEGER NOT NULL DEFAULT 5,
                max_retries INTEGER NOT NULL DEFAULT 3,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            # 6. Notification Logs table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_logs (
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
            """)

            # 7. Audit Logs table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                message TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL
            );
            """)

            # Indices
            conn.execute("CREATE INDEX IF NOT EXISTS idx_services_active ON services(is_active);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_rules_service ON alert_rules(service_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_checks_service_created ON check_results(service_id, created_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_service_status ON incidents(service_id, status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_started ON incidents(started_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_notification_logs_created ON notification_logs(created_at DESC);")

            # Check if default notification config exists, if not create empty placeholder
            cur = conn.execute("SELECT COUNT(*) as cnt FROM notification_configs")
            if cur.fetchone()["cnt"] == 0:
                from datetime import datetime, timezone
                now_iso = datetime.now(timezone.utc).isoformat()
                from incidentpulse.config import Config
                conn.execute("""
                INSERT INTO notification_configs (channel_type, webhook_url, is_enabled, timeout_seconds, max_retries, created_at, updated_at)
                VALUES ('WEBHOOK', ?, 1, ?, ?, ?, ?)
                """, (Config.DEFAULT_WEBHOOK_URL or "", Config.WEBHOOK_TIMEOUT_SECONDS, Config.WEBHOOK_MAX_RETRIES, now_iso, now_iso))

    finally:
        conn.close()
