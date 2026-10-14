from unittest.mock import patch, MagicMock
from incidentpulse.monitoring.checker import perform_health_check
from incidentpulse.monitoring.rules import evaluate_check_rules
from incidentpulse.models import create_service, get_service_by_id, get_incidents_list
from incidentpulse.database import get_db_connection

def test_complete_outage_and_recovery_cycle(db_conn):
    """
    Comprehensive test demonstrating end-to-end failure detection,
    incident creation, notification dispatch, automatic recovery, and duration calculation.
    """
    # 1. Create a service with consecutive threshold 2 and recovery threshold 2
    service = create_service(
        name="Inventory Demo Service",
        url="http://127.0.0.1:5050/health",
        check_interval=5,
        timeout=2,
        allow_local_demo=True,
        endpoint_failure_threshold=2,
        recovery_threshold=2
    )
    service_id = service["id"]
    assert service["current_status"] == "UNKNOWN"

    mock_ok = MagicMock()
    mock_ok.status_code = 200
    mock_ok.headers = {}
    mock_ok.history = []

    # 2. First check: Service is UP
    with patch("requests.Session.get", return_value=mock_ok):
        outcome1 = perform_health_check(service["url"], allow_local_demo=True)
        eval1 = evaluate_check_rules(db_conn, service, outcome1)
        assert eval1["new_status"] == "UP"

    # Refresh service
    svc_after_check = get_service_by_id(service_id, conn=db_conn)
    assert svc_after_check["current_status"] == "UP"

    # 3. Simulate Outage (Process Stopped / Connection Error)
    import requests
    mock_fail = requests.exceptions.ConnectionError("Connection refused")
    
    with patch("requests.Session.get", side_effect=mock_fail), \
         patch("incidentpulse.monitoring.rules.dispatch_incident_notification") as mock_notify:

        # Failure check 1
        outcome_f1 = perform_health_check(service["url"], allow_local_demo=True)
        eval_f1 = evaluate_check_rules(db_conn, svc_after_check, outcome_f1)
        assert len(eval_f1["opened_incidents"]) == 0  # threshold 2 not reached yet

        # Failure check 2 -> Threshold reached!
        outcome_f2 = perform_health_check(service["url"], allow_local_demo=True)
        eval_f2 = evaluate_check_rules(db_conn, svc_after_check, outcome_f2)
        assert len(eval_f2["opened_incidents"]) == 1
        assert eval_f2["new_status"] == "DOWN"
        assert mock_notify.called

        incident_id = eval_f2["opened_incidents"][0]

        # Failure check 3 -> Ensure no duplicate incident is created
        outcome_f3 = perform_health_check(service["url"], allow_local_demo=True)
        eval_f3 = evaluate_check_rules(db_conn, svc_after_check, outcome_f3)
        assert len(eval_f3["opened_incidents"]) == 0

    # Verify incident state in database
    cur_inc = db_conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    inc_row = cur_inc.fetchone()
    assert inc_row["status"] == "OPEN"
    assert inc_row["severity"] == "CRITICAL"
    assert inc_row["started_at"] is not None
    assert inc_row["resolved_at"] is None

    # 4. Simulate Service Recovery (Process Restarted)
    with patch("requests.Session.get", return_value=mock_ok), \
         patch("incidentpulse.monitoring.rules.dispatch_incident_notification") as mock_rec_notify:

        # Recovery check 1: Below recovery threshold (needs 2)
        outcome_r1 = perform_health_check(service["url"], allow_local_demo=True)
        eval_r1 = evaluate_check_rules(db_conn, svc_after_check, outcome_r1)
        assert len(eval_r1["resolved_incidents"]) == 0

        # Recovery check 2: Reaches recovery threshold -> RESOLVED!
        outcome_r2 = perform_health_check(service["url"], allow_local_demo=True)
        eval_r2 = evaluate_check_rules(db_conn, svc_after_check, outcome_r2)
        assert len(eval_r2["resolved_incidents"]) == 1
        assert eval_r2["new_status"] == "UP"
        assert mock_rec_notify.called

    # 5. Verify resolved incident properties
    cur_resolved = db_conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    resolved_row = cur_resolved.fetchone()
    assert resolved_row["status"] == "RESOLVED"
    assert resolved_row["resolved_at"] is not None
    assert resolved_row["duration_seconds"] is not None
    assert resolved_row["duration_seconds"] >= 0.0

    # 6. Verify incident list querying
    incidents, total = get_incidents_list(service_id=service_id)
    assert total == 1
    assert incidents[0]["id"] == incident_id
    assert incidents[0]["status"] == "RESOLVED"
