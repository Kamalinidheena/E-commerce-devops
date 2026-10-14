import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from incidentpulse.database import get_db_connection

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ==================== SERVICES ====================

def create_service(
    name: str,
    url: str,
    description: str = "",
    check_interval: int = 30,
    timeout: int = 5,
    expected_status: int = 200,
    follow_redirects: bool = True,
    allow_local_demo: bool = False,
    endpoint_failure_threshold: int = 2,
    latency_threshold_ms: float = 500.0,
    latency_consecutive_threshold: int = 2,
    recovery_threshold: int = 2
) -> Dict[str, Any]:
    """
    Creates a new monitored service and sets up its independent alert rules
    inside an atomic transaction.
    """
    conn = get_db_connection()
    try:
        with conn:
            ts = now_iso()
            cur = conn.execute("""
                INSERT INTO services (
                    name, description, url, check_interval, timeout, expected_status,
                    follow_redirects, allow_local_demo, is_active, current_status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'UNKNOWN', ?, ?)
            """, (
                name.strip(),
                description.strip() if description else "",
                url.strip(),
                check_interval,
                timeout,
                expected_status,
                1 if follow_redirects else 0,
                1 if allow_local_demo else 0,
                ts,
                ts
            ))
            service_id = cur.lastrowid

            # Create RULE 1: ENDPOINT_FAILURE
            conn.execute("""
                INSERT INTO alert_rules (
                    service_id, rule_type, threshold_value, consecutive_threshold,
                    recovery_threshold, is_enabled, current_failure_streak, current_success_streak,
                    created_at, updated_at
                ) VALUES (?, 'ENDPOINT_FAILURE', ?, ?, ?, 1, 0, 0, ?, ?)
            """, (service_id, endpoint_failure_threshold, endpoint_failure_threshold, recovery_threshold, ts, ts))

            # Create RULE 2: LATENCY_THRESHOLD
            conn.execute("""
                INSERT INTO alert_rules (
                    service_id, rule_type, threshold_value, consecutive_threshold,
                    recovery_threshold, is_enabled, current_failure_streak, current_success_streak,
                    created_at, updated_at
                ) VALUES (?, 'LATENCY_THRESHOLD', ?, ?, ?, 1, 0, 0, ?, ?)
            """, (service_id, latency_threshold_ms, latency_consecutive_threshold, recovery_threshold, ts, ts))

            # Record audit log
            conn.execute("""
                INSERT INTO audit_logs (event_type, entity_type, entity_id, message, details_json, created_at)
                VALUES ('SERVICE_CREATED', 'SERVICE', ?, ?, ?, ?)
            """, (
                service_id,
                f"Service '{name}' created with interval {check_interval}s",
                json.dumps({"name": name, "url": url, "check_interval": check_interval, "timeout": timeout}),
                ts
            ))

            return get_service_by_id(service_id, conn=conn)
    finally:
        conn.close()

def get_service_by_id(service_id: int, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    """Fetches a service by ID, including its alert rules."""
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    try:
        cur = conn.execute("SELECT * FROM services WHERE id = ?", (service_id,))
        row = cur.fetchone()
        if not row:
            return None
        service = dict(row)

        cur_rules = conn.execute("SELECT * FROM alert_rules WHERE service_id = ?", (service_id,))
        service["alert_rules"] = [dict(r) for r in cur_rules.fetchall()]
        return service
    finally:
        if should_close:
            conn.close()

def get_all_services(is_active_only: bool = False) -> List[Dict[str, Any]]:
    """Retrieves all services."""
    conn = get_db_connection()
    try:
        query = "SELECT * FROM services"
        params = ()
        if is_active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY id DESC"

        cur = conn.execute(query, params)
        rows = cur.fetchall()
        services = []
        for r in rows:
            s = dict(r)
            cur_rules = conn.execute("SELECT * FROM alert_rules WHERE service_id = ?", (s["id"],))
            s["alert_rules"] = [dict(rule) for rule in cur_rules.fetchall()]
            services.append(s)
        return services
    finally:
        conn.close()

def update_service(service_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates editable service fields and logs audit event."""
    conn = get_db_connection()
    try:
        with conn:
            existing = get_service_by_id(service_id, conn=conn)
            if not existing:
                return None

            allowed_fields = [
                "name", "description", "url", "check_interval", "timeout",
                "expected_status", "follow_redirects", "allow_local_demo", "is_active"
            ]
            set_clauses = []
            params = []
            for field in allowed_fields:
                if field in updates:
                    set_clauses.append(f"{field} = ?")
                    params.append(updates[field])

            if not set_clauses:
                return existing

            ts = now_iso()
            set_clauses.append("updated_at = ?")
            params.append(ts)
            params.append(service_id)

            conn.execute(f"UPDATE services SET {', '.join(set_clauses)} WHERE id = ?", params)

            conn.execute("""
                INSERT INTO audit_logs (event_type, entity_type, entity_id, message, details_json, created_at)
                VALUES ('SERVICE_UPDATED', 'SERVICE', ?, ?, ?, ?)
            """, (
                service_id,
                f"Service #{service_id} updated",
                json.dumps(updates),
                ts
            ))

            return get_service_by_id(service_id, conn=conn)
    finally:
        conn.close()

def delete_service(service_id: int) -> bool:
    """Deletes a service and cascades deletion of rules, checks, incidents."""
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.execute("SELECT name FROM services WHERE id = ?", (service_id,))
            s = cur.fetchone()
            if not s:
                return False

            name = s["name"]
            conn.execute("DELETE FROM services WHERE id = ?", (service_id,))
            ts = now_iso()
            conn.execute("""
                INSERT INTO audit_logs (event_type, entity_type, entity_id, message, details_json, created_at)
                VALUES ('SERVICE_DELETED', 'SERVICE', ?, ?, ?, ?)
            """, (service_id, f"Service '{name}' (ID: {service_id}) deleted", json.dumps({"service_id": service_id, "name": name}), ts))
            return True
    finally:
        conn.close()

def get_dashboard_summary() -> Dict[str, Any]:
    """Calculates live dashboard overview statistics strictly from database state."""
    conn = get_db_connection()
    try:
        cur = conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN current_status = 'UP' THEN 1 ELSE 0 END) as count_up,
                SUM(CASE WHEN current_status = 'DOWN' THEN 1 ELSE 0 END) as count_down,
                SUM(CASE WHEN current_status = 'DEGRADED' THEN 1 ELSE 0 END) as count_degraded,
                SUM(CASE WHEN current_status = 'UNKNOWN' THEN 1 ELSE 0 END) as count_unknown
            FROM services
        """)
        row = cur.fetchone()
        
        # Open incidents
        cur_inc = conn.execute("SELECT COUNT(*) as open_incidents FROM incidents WHERE status = 'OPEN'")
        open_inc = cur_inc.fetchone()["open_incidents"]

        # Alerts in last 24 hours
        cur_alerts = conn.execute("""
            SELECT COUNT(*) as alert_count FROM incidents 
            WHERE started_at >= datetime('now', '-1 day')
        """)
        alerts_24h = cur_alerts.fetchone()["alert_count"]

        # Recent recoveries in last 24h
        cur_rec = conn.execute("""
            SELECT COUNT(*) as recovery_count FROM incidents 
            WHERE status = 'RESOLVED' AND resolved_at >= datetime('now', '-1 day')
        """)
        recent_recoveries = cur_rec.fetchone()["recovery_count"]

        # Latest check timestamp and latest response time across all services
        cur_last_check = conn.execute("""
            SELECT last_checked_at, last_response_time_ms FROM services 
            WHERE last_checked_at IS NOT NULL 
            ORDER BY last_checked_at DESC LIMIT 1
        """)
        last_check_row = cur_last_check.fetchone()

        return {
            "total_services": row["total"] or 0,
            "services_up": row["count_up"] or 0,
            "services_down": row["count_down"] or 0,
            "services_degraded": row["count_degraded"] or 0,
            "services_unknown": row["count_unknown"] or 0,
            "open_incidents": open_inc or 0,
            "alerts_24h": alerts_24h or 0,
            "recent_recoveries": recent_recoveries or 0,
            "last_check_time": last_check_row["last_checked_at"] if last_check_row else None,
            "latest_response_time_ms": last_check_row["last_response_time_ms"] if last_check_row else None
        }
    finally:
        conn.close()

# ==================== CHECK RESULTS ====================

def get_service_check_history(service_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves chronological check history for a service."""
    conn = get_db_connection()
    try:
        cur = conn.execute("""
            SELECT * FROM check_results 
            WHERE service_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (service_id, limit))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

# ==================== INCIDENTS ====================

def get_incidents_list(
    service_id: Optional[int] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves incidents with optional filters and total count."""
    conn = get_db_connection()
    try:
        where_clauses = []
        params = []

        if service_id is not None:
            where_clauses.append("i.service_id = ?")
            params.append(service_id)
        if status:
            where_clauses.append("i.status = ?")
            params.append(status.upper())
        if severity:
            where_clauses.append("i.severity = ?")
            params.append(severity.upper())

        where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Total count
        cur_count = conn.execute(f"SELECT COUNT(*) as total FROM incidents i {where_str}", params)
        total = cur_count.fetchone()["total"]

        query = f"""
            SELECT i.*, s.name as service_name, s.url as service_url 
            FROM incidents i 
            LEFT JOIN services s ON i.service_id = s.id 
            {where_str} 
            ORDER BY i.started_at DESC 
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        cur = conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()], total
    finally:
        conn.close()

def get_incident_by_id(incident_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves full incident details including delivery logs and service info."""
    conn = get_db_connection()
    try:
        cur = conn.execute("""
            SELECT i.*, s.name as service_name, s.url as service_url 
            FROM incidents i 
            LEFT JOIN services s ON i.service_id = s.id 
            WHERE i.id = ?
        """, (incident_id,))
        row = cur.fetchone()
        if not row:
            return None
        incident = dict(row)

        # Retrieve related notification delivery logs
        cur_logs = conn.execute("""
            SELECT * FROM notification_logs 
            WHERE incident_id = ? 
            ORDER BY created_at DESC
        """, (incident_id,))
        incident["notification_logs"] = [dict(log) for log in cur_logs.fetchall()]
        return incident
    finally:
        conn.close()

# ==================== NOTIFICATIONS & AUDIT ====================

def get_notification_logs(limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves notification logs with total count."""
    conn = get_db_connection()
    try:
        cur_count = conn.execute("SELECT COUNT(*) as total FROM notification_logs")
        total = cur_count.fetchone()["total"]

        cur = conn.execute("""
            SELECT nl.*, i.title as incident_title 
            FROM notification_logs nl 
            LEFT JOIN incidents i ON nl.incident_id = i.id 
            ORDER BY nl.created_at DESC 
            LIMIT ? OFFSET ?
        """, (limit, offset))
        return [dict(r) for r in cur.fetchall()], total
    finally:
        conn.close()

def get_audit_logs(limit: int = 100, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves audit trail with total count."""
    conn = get_db_connection()
    try:
        cur_count = conn.execute("SELECT COUNT(*) as total FROM audit_logs")
        total = cur_count.fetchone()["total"]

        cur = conn.execute("""
            SELECT * FROM audit_logs 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        """, (limit, offset))
        return [dict(r) for r in cur.fetchall()], total
    finally:
        conn.close()
