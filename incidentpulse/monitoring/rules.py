import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from incidentpulse.monitoring.checker import CheckOutcome
from incidentpulse.monitoring.incidents import (
    open_incident,
    resolve_incident,
    get_open_incident_for_rule
)
from incidentpulse.monitoring.notifications import dispatch_incident_notification

def evaluate_check_rules(
    conn: sqlite3.Connection,
    service: sqlite3.Row,
    outcome: CheckOutcome
) -> Dict[str, Any]:
    """
    Evaluates independent alert rules for a service against a single CheckOutcome.
    Records the check result, updates failure/success streaks, opens or resolves incidents,
    dispatches notifications, and updates overall service status.
    """
    service_id = service["id"]
    service_name = service["name"]
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Record check outcome in check_results table
    check_status = "UP" if outcome.is_available else "DOWN"
    conn.execute("""
        INSERT INTO check_results (
            service_id, status, http_status, response_time_ms,
            error_message, resolved_ip, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        service_id,
        check_status,
        outcome.http_status,
        outcome.response_time_ms,
        outcome.error_message,
        outcome.resolved_ip,
        now_iso
    ))

    # 2. Retrieve configured alert rules for this service
    cur = conn.execute("""
        SELECT * FROM alert_rules 
        WHERE service_id = ? AND is_enabled = 1
    """, (service_id,))
    rules = cur.fetchall()

    opened_incidents = []
    resolved_incidents = []

    for rule in rules:
        rule_id = rule["id"]
        rule_type = rule["rule_type"]
        threshold_val = rule["threshold_value"]
        consec_thresh = rule["consecutive_threshold"]
        recovery_thresh = rule["recovery_threshold"]
        failure_streak = rule["current_failure_streak"]
        success_streak = rule["current_success_streak"]

        # RULE 1: ENDPOINT FAILURE
        if rule_type == "ENDPOINT_FAILURE":
            if not outcome.is_available or not outcome.workflow_passed:
                # Check failed
                failure_streak += 1
                success_streak = 0
                if failure_streak >= consec_thresh:
                    title = f"{service_name} is DOWN"
                    desc = outcome.error_message or "Service failed health check"
                    inc_id = open_incident(
                        conn=conn,
                        service_id=service_id,
                        rule_id=rule_id,
                        rule_type=rule_type,
                        severity="CRITICAL",
                        title=title,
                        description=f"{desc} (failed {failure_streak} consecutive checks)"
                    )
                    if inc_id:
                        opened_incidents.append(inc_id)
                        # Dispatch alert notification
                        inc_data = {
                            "id": inc_id,
                            "rule_type": rule_type,
                            "severity": "CRITICAL",
                            "title": title,
                            "description": desc,
                            "started_at": now_iso
                        }
                        dispatch_incident_notification(conn, "INCIDENT_OPENED", inc_data, dict(service))
            else:
                # Check succeeded
                failure_streak = 0
                success_streak += 1
                if success_streak >= recovery_thresh:
                    open_inc = get_open_incident_for_rule(conn, service_id, rule_type)
                    if open_inc:
                        resolved_summary = resolve_incident(
                            conn=conn,
                            incident_id=open_inc["id"],
                            resolution_note=f"Service responded successfully (HTTP {outcome.http_status})"
                        )
                        if resolved_summary:
                            resolved_incidents.append(resolved_summary["id"])
                            dispatch_incident_notification(conn, "INCIDENT_RESOLVED", resolved_summary, dict(service))
                    # Reset success streak after threshold reached to avoid redundant processing
                    success_streak = 0

            # Persist updated streaks
            conn.execute("""
                UPDATE alert_rules 
                SET current_failure_streak = ?,
                    current_success_streak = ?,
                    updated_at = ?
                WHERE id = ?
            """, (failure_streak, success_streak, now_iso, rule_id))

        # RULE 2: LATENCY THRESHOLD
        elif rule_type == "LATENCY_THRESHOLD":
            is_slow = outcome.is_available and (outcome.response_time_ms > threshold_val)
            
            if is_slow:
                # Latency exceeded
                failure_streak += 1
                success_streak = 0
                if failure_streak >= consec_thresh:
                    title = f"{service_name} degraded: High Latency"
                    desc = f"Response time {outcome.response_time_ms}ms exceeded configured threshold {threshold_val}ms."
                    inc_id = open_incident(
                        conn=conn,
                        service_id=service_id,
                        rule_id=rule_id,
                        rule_type=rule_type,
                        severity="WARNING",
                        title=title,
                        description=f"{desc} (exceeded for {failure_streak} consecutive checks)"
                    )
                    if inc_id:
                        opened_incidents.append(inc_id)
                        inc_data = {
                            "id": inc_id,
                            "rule_type": rule_type,
                            "severity": "WARNING",
                            "title": title,
                            "description": desc,
                            "started_at": now_iso
                        }
                        dispatch_incident_notification(conn, "INCIDENT_OPENED", inc_data, dict(service))
            elif outcome.is_available:
                # Latency within normal threshold
                failure_streak = 0
                success_streak += 1
                if success_streak >= recovery_thresh:
                    open_inc = get_open_incident_for_rule(conn, service_id, rule_type)
                    if open_inc:
                        resolved_summary = resolve_incident(
                            conn=conn,
                            incident_id=open_inc["id"],
                            resolution_note=f"Response time returned to normal ({outcome.response_time_ms}ms <= {threshold_val}ms)"
                        )
                        if resolved_summary:
                            resolved_incidents.append(resolved_summary["id"])
                            dispatch_incident_notification(conn, "INCIDENT_RESOLVED", resolved_summary, dict(service))
                    success_streak = 0

            # Persist updated streaks
            conn.execute("""
                UPDATE alert_rules 
                SET current_failure_streak = ?,
                    current_success_streak = ?,
                    updated_at = ?
                WHERE id = ?
            """, (failure_streak, success_streak, now_iso, rule_id))

    # 3. Determine overall service status based on active open incidents
    cur = conn.execute("""
        SELECT rule_type FROM incidents 
        WHERE service_id = ? AND status = 'OPEN'
    """, (service_id,))
    active_open_rule_types = {r["rule_type"] for r in cur.fetchall()}

    if "ENDPOINT_FAILURE" in active_open_rule_types:
        new_status = "DOWN"
    elif "LATENCY_THRESHOLD" in active_open_rule_types:
        new_status = "DEGRADED"
    elif outcome.is_available:
        new_status = "UP"
    else:
        new_status = "DOWN"

    # 4. Update service record
    conn.execute("""
        UPDATE services 
        SET current_status = ?,
            last_checked_at = ?,
            last_response_time_ms = ?,
            last_status_code = ?,
            last_error_message = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        new_status,
        now_iso,
        outcome.response_time_ms,
        outcome.http_status,
        outcome.error_message,
        now_iso,
        service_id
    ))

    # Commit transaction to ensure changes are immediately visible across all DB connections
    conn.commit()

    return {
        "service_id": service_id,
        "new_status": new_status,
        "opened_incidents": opened_incidents,
        "resolved_incidents": resolved_incidents,
        "outcome": outcome
    }
