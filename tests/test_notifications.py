from unittest.mock import patch, MagicMock
import requests
from incidentpulse.monitoring.notifications import (
    send_webhook_payload,
    dispatch_incident_notification,
    send_test_notification
)
from incidentpulse.models import create_service

def test_webhook_successful_delivery():
    """Verifies that an accepted HTTP 200 response logs delivery success."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("requests.post", return_value=mock_resp):
        success, code, msg, attempts = send_webhook_payload(
            "http://127.0.0.1:5050/webhook",
            {"event": "TEST"},
            timeout_seconds=2,
            max_retries=2
        )
        assert success is True
        assert code == 200
        assert attempts == 1
        assert "Delivered successfully" in msg

def test_webhook_error_and_retry():
    """Verifies that non-200 responses trigger bounded retries."""
    mock_resp = MagicMock()
    mock_resp.status_code = 502

    with patch("requests.post", return_value=mock_resp):
        success, code, msg, attempts = send_webhook_payload(
            "http://127.0.0.1:5050/webhook",
            {"event": "TEST"},
            timeout_seconds=1,
            max_retries=2
        )
        assert success is False
        assert code == 502
        assert attempts == 2  # Retried up to max_retries
        assert "unacceptable HTTP 502" in msg

def test_webhook_timeout():
    """Verifies that request timeouts are caught and reported."""
    with patch("requests.post", side_effect=requests.exceptions.Timeout("Connection timed out")):
        success, code, msg, attempts = send_webhook_payload(
            "http://127.0.0.1:5050/webhook",
            {"event": "TEST"},
            timeout_seconds=1,
            max_retries=2
        )
        assert success is False
        assert code is None
        assert "timed out" in msg.lower()

def test_incident_notification_unconfigured(db_conn):
    """Verifies that having no webhook URL records NOT_CONFIGURED without deleting incident."""
    service = create_service(name="Svc", url="http://127.0.0.1:5050/health", allow_local_demo=True)
    
    # Ensure webhook_url is empty in db
    db_conn.execute("UPDATE notification_configs SET webhook_url = ''")

    # Insert an incident
    cur = db_conn.execute("""
        INSERT INTO incidents (service_id, rule_type, severity, status, title, description, started_at, created_at, updated_at)
        VALUES (?, 'ENDPOINT_FAILURE', 'CRITICAL', 'OPEN', 'Outage', 'Down', '2026-10-14T10:00:00Z', '2026-10-14T10:00:00Z', '2026-10-14T10:00:00Z')
    """, (service["id"],))
    inc_id = cur.lastrowid

    inc_data = {"id": inc_id, "rule_type": "ENDPOINT_FAILURE", "severity": "CRITICAL", "title": "Outage"}
    res = dispatch_incident_notification(db_conn, "INCIDENT_OPENED", inc_data, service)
    assert res["success"] is False
    assert res["status"] == "NOT_CONFIGURED"

    # Incident must remain recorded in database!
    cur_chk = db_conn.execute("SELECT * FROM incidents WHERE id = ?", (inc_id,))
    row = cur_chk.fetchone()
    assert row is not None
    assert row["notification_status"] == "NOT_CONFIGURED"

def test_send_test_notification_flow(db_conn):
    """Verifies the test notification trigger function."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("requests.post", return_value=mock_resp):
        res = send_test_notification(db_conn, target_url="http://127.0.0.1:5050/webhook")
        assert res["success"] is True
        assert res["status"] == "SUCCESS"

        # Check log was saved
        cur = db_conn.execute("SELECT * FROM notification_logs WHERE target_url = 'http://127.0.0.1:5050/webhook'")
        log_entry = cur.fetchone()
        assert log_entry is not None
        assert log_entry["status"] == "SUCCESS"
