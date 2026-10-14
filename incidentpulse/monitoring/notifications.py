import json
import time
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import sqlite3
from incidentpulse.monitoring.security import validate_monitoring_url, SecurityValidationError
from incidentpulse.config import Config

def get_notification_config(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """Retrieves the active notification config from database."""
    cur = conn.execute("""
        SELECT * FROM notification_configs 
        WHERE is_enabled = 1 
        ORDER BY id DESC LIMIT 1
    """)
    return cur.fetchone()

def send_webhook_payload(
    target_url: str,
    payload: Dict[str, Any],
    timeout_seconds: int = 5,
    max_retries: int = 3
) -> Tuple[bool, Optional[int], str, int]:
    """
    Delivers a JSON webhook payload to target_url with bounded retries and exponential backoff.
    
    Returns:
        (success: bool, http_status: Optional[int], error_or_success_message: str, attempts: int)
    """
    if not target_url or not target_url.strip():
        return False, None, "No webhook URL configured", 0

    # Validate webhook target URL (allowing local demo if configured)
    try:
        validated_url, _ = validate_monitoring_url(target_url, allow_local_demo=Config.ALLOW_LOCAL_DEMO)
    except SecurityValidationError as e:
        return False, None, f"Webhook URL security validation failed: {e}", 0

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "IncidentPulse-AlertNotifier/1.0"
    }

    last_error = ""
    last_status = None
    attempt = 0

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                validated_url,
                json=payload,
                headers=headers,
                timeout=timeout_seconds
            )
            last_status = resp.status_code
            if 200 <= last_status < 300:
                return True, last_status, f"Delivered successfully (HTTP {last_status})", attempt
            else:
                last_error = f"Receiver returned unacceptable HTTP {last_status}"
        except requests.exceptions.Timeout:
            last_error = f"Webhook request timed out after {timeout_seconds}s"
        except requests.exceptions.ConnectionError:
            last_error = "Connection refused or host unreachable"
        except requests.exceptions.RequestException as e:
            last_error = f"Delivery request error: {str(e)[:100]}"

        # Exponential backoff between retries (e.g. 0.2s, 0.4s)
        if attempt < max_retries:
            time.sleep(0.2 * (2 ** (attempt - 1)))

    return False, last_status, last_error, attempt

def dispatch_incident_notification(
    conn: sqlite3.Connection,
    event_type: str,
    incident_data: Dict[str, Any],
    service_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Constructs and delivers an alert or recovery notification to the configured webhook,
    logging the attempt to notification_logs.
    """
    config = get_notification_config(conn)
    webhook_url = config["webhook_url"] if config else None
    timeout = config["timeout_seconds"] if config else Config.WEBHOOK_TIMEOUT_SECONDS
    max_retries = config["max_retries"] if config else Config.WEBHOOK_MAX_RETRIES

    now_iso = datetime.now(timezone.utc).isoformat()
    incident_id = incident_data.get("id")

    payload = {
        "event": event_type,  # 'INCIDENT_OPENED', 'INCIDENT_RESOLVED', 'TEST_NOTIFICATION'
        "timestamp": now_iso,
        "service": {
            "id": service_data.get("id"),
            "name": service_data.get("name"),
            "url": service_data.get("url")
        },
        "incident": {
            "id": incident_id,
            "rule_type": incident_data.get("rule_type"),
            "severity": incident_data.get("severity"),
            "title": incident_data.get("title"),
            "description": incident_data.get("description"),
            "started_at": incident_data.get("started_at"),
            "resolved_at": incident_data.get("resolved_at"),
            "duration_seconds": incident_data.get("duration_seconds")
        }
    }

    if not webhook_url:
        status_msg = "Notification not configured (No webhook URL provided)"
        if incident_id:
            conn.execute(
                "UPDATE incidents SET notification_status = 'NOT_CONFIGURED', updated_at = ? WHERE id = ?",
                (now_iso, incident_id)
            )
        return {"success": False, "status": "NOT_CONFIGURED", "message": status_msg, "attempts": 0}

    success, http_code, message, attempts = send_webhook_payload(
        webhook_url, payload, timeout_seconds=timeout, max_retries=max_retries
    )

    delivery_status = "SUCCESS" if success else ("TIMED_OUT" if "timed out" in message.lower() else "FAILED")

    # Record notification log in database
    conn.execute("""
        INSERT INTO notification_logs (
            incident_id, channel_type, target_url, payload_preview,
            status, http_status, attempt_number, error_message, created_at
        ) VALUES (?, 'WEBHOOK', ?, ?, ?, ?, ?, ?, ?)
    """, (
        incident_id,
        webhook_url,
        json.dumps(payload)[:500],
        delivery_status,
        http_code,
        attempts,
        None if success else message,
        now_iso
    ))

    # Update incident notification status
    if incident_id:
        conn.execute("""
            UPDATE incidents 
            SET notification_sent = ?,
                notification_status = ?,
                updated_at = ?
            WHERE id = ?
        """, (1 if success else 0, delivery_status, now_iso, incident_id))

    return {
        "success": success,
        "status": delivery_status,
        "http_code": http_code,
        "message": message,
        "attempts": attempts
    }

def send_test_notification(conn: sqlite3.Connection, target_url: Optional[str] = None) -> Dict[str, Any]:
    """Sends an immediate test notification to verify webhook configuration."""
    if not target_url:
        config = get_notification_config(conn)
        target_url = config["webhook_url"] if config else None

    if not target_url:
        return {
            "success": False,
            "status": "NOT_CONFIGURED",
            "message": "Cannot send test: Webhook URL is empty."
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    test_payload = {
        "event": "TEST_NOTIFICATION",
        "timestamp": now_iso,
        "message": "IncidentPulse test webhook delivery verification.",
        "system": {
            "platform": "IncidentPulse",
            "status": "operational"
        }
    }

    success, http_code, message, attempts = send_webhook_payload(
        target_url, test_payload, timeout_seconds=5, max_retries=1
    )

    delivery_status = "SUCCESS" if success else "FAILED"

    # Log the test notification
    conn.execute("""
        INSERT INTO notification_logs (
            incident_id, channel_type, target_url, payload_preview,
            status, http_status, attempt_number, error_message, created_at
        ) VALUES (NULL, 'WEBHOOK', ?, ?, ?, ?, ?, ?, ?)
    """, (
        target_url,
        json.dumps(test_payload),
        delivery_status,
        http_code,
        attempts,
        None if success else message,
        now_iso
    ))

    return {
        "success": success,
        "status": delivery_status,
        "http_code": http_code,
        "message": message,
        "attempts": attempts
    }
