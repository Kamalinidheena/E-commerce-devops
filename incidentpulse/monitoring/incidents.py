import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import sqlite3

def get_utc_now_iso() -> str:
    """Returns current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()

def parse_iso_datetime(iso_str: str) -> datetime:
    """Parses an ISO 8601 string to a timezone-aware datetime."""
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def calculate_duration_seconds(started_at_iso: str, resolved_at_iso: str) -> float:
    """Calculates duration in seconds between two ISO timestamps."""
    start_dt = parse_iso_datetime(started_at_iso)
    resolved_dt = parse_iso_datetime(resolved_at_iso)
    duration = (resolved_dt - start_dt).total_seconds()
    return max(0.0, round(duration, 2))

def get_open_incident_for_rule(conn: sqlite3.Connection, service_id: int, rule_type: str) -> Optional[sqlite3.Row]:
    """Finds an existing OPEN incident for a specific service and rule type."""
    cur = conn.execute("""
        SELECT * FROM incidents 
        WHERE service_id = ? AND rule_type = ? AND status = 'OPEN'
        LIMIT 1
    """, (service_id, rule_type))
    return cur.fetchone()

def open_incident(
    conn: sqlite3.Connection,
    service_id: int,
    rule_id: Optional[int],
    rule_type: str,
    severity: str,
    title: str,
    description: str
) -> Optional[int]:
    """
    Opens a new incident if none is already open for this service and rule.
    Returns the new incident ID, or None if an open incident already exists.
    """
    existing = get_open_incident_for_rule(conn, service_id, rule_type)
    if existing:
        # Avoid duplicate open incidents for the same ongoing condition
        # Update updated_at timestamp
        now_iso = get_utc_now_iso()
        conn.execute("UPDATE incidents SET updated_at = ? WHERE id = ?", (now_iso, existing["id"]))
        return None

    now_iso = get_utc_now_iso()
    cur = conn.execute("""
        INSERT INTO incidents (
            service_id, rule_id, rule_type, severity, status, title, description,
            started_at, notification_sent, notification_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, 0, 'PENDING', ?, ?)
    """, (service_id, rule_id, rule_type, severity, title, description, now_iso, now_iso, now_iso))
    
    incident_id = cur.lastrowid

    # Create audit log entry
    conn.execute("""
        INSERT INTO audit_logs (event_type, entity_type, entity_id, message, details_json, created_at)
        VALUES ('INCIDENT_OPENED', 'INCIDENT', ?, ?, ?, ?)
    """, (
        incident_id,
        f"Incident opened: {title}",
        json.dumps({"service_id": service_id, "rule_type": rule_type, "severity": severity, "description": description}),
        now_iso
    ))

    return incident_id

def resolve_incident(
    conn: sqlite3.Connection,
    incident_id: int,
    resolution_note: str = "Service recovered automatically"
) -> Optional[Dict[str, Any]]:
    """
    Resolves an open incident, computes real duration from persisted timestamps,
    and records an audit log.
    Returns incident summary dict or None if not found or already resolved.
    """
    cur = conn.execute("SELECT * FROM incidents WHERE id = ? AND status = 'OPEN'", (incident_id,))
    incident = cur.fetchone()
    if not incident:
        return None

    now_iso = get_utc_now_iso()
    started_at = incident["started_at"]
    duration = calculate_duration_seconds(started_at, now_iso)

    conn.execute("""
        UPDATE incidents 
        SET status = 'RESOLVED',
            resolved_at = ?,
            duration_seconds = ?,
            updated_at = ?
        WHERE id = ?
    """, (now_iso, duration, now_iso, incident_id))

    # Audit log
    conn.execute("""
        INSERT INTO audit_logs (event_type, entity_type, entity_id, message, details_json, created_at)
        VALUES ('INCIDENT_RESOLVED', 'INCIDENT', ?, ?, ?, ?)
    """, (
        incident_id,
        f"Incident #{incident_id} resolved after {duration}s: {resolution_note}",
        json.dumps({
            "service_id": incident["service_id"],
            "started_at": started_at,
            "resolved_at": now_iso,
            "duration_seconds": duration,
            "resolution_note": resolution_note
        }),
        now_iso
    ))

    return {
        "id": incident_id,
        "service_id": incident["service_id"],
        "rule_type": incident["rule_type"],
        "severity": incident["severity"],
        "title": incident["title"],
        "started_at": started_at,
        "resolved_at": now_iso,
        "duration_seconds": duration
    }
