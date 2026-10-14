from unittest.mock import patch
from incidentpulse.monitoring.checker import CheckOutcome
from incidentpulse.monitoring.rules import evaluate_check_rules
from incidentpulse.models import create_service, get_service_by_id

def test_endpoint_failure_rule_threshold(db_conn):
    """Verifies that failure threshold prevents noise and opens an incident on consecutive failures."""
    with patch("incidentpulse.monitoring.rules.dispatch_incident_notification"):
        service = create_service(
            name="Test Service",
            url="http://127.0.0.1:5050/health",
            allow_local_demo=True,
            endpoint_failure_threshold=2,
            recovery_threshold=2
        )
        service_id = service["id"]

        # Failure 1: Below threshold (threshold=2)
        outcome1 = CheckOutcome(is_available=False, http_status=500, response_time_ms=10.0, error_message="HTTP 500")
        eval1 = evaluate_check_rules(db_conn, service, outcome1)
        assert len(eval1["opened_incidents"]) == 0
        assert eval1["new_status"] == "DOWN" or eval1["new_status"] == "UNKNOWN"

        # Check rule failure streak
        cur = db_conn.execute("SELECT current_failure_streak FROM alert_rules WHERE service_id = ? AND rule_type = 'ENDPOINT_FAILURE'", (service_id,))
        assert cur.fetchone()["current_failure_streak"] == 1

        # Failure 2: Reaches threshold -> opens incident
        outcome2 = CheckOutcome(is_available=False, http_status=500, response_time_ms=10.0, error_message="HTTP 500")
        eval2 = evaluate_check_rules(db_conn, service, outcome2)
        assert len(eval2["opened_incidents"]) == 1
        assert eval2["new_status"] == "DOWN"

        # Failure 3: Continuous failure -> deduplication prevents opening duplicate incident!
        outcome3 = CheckOutcome(is_available=False, http_status=500, response_time_ms=10.0, error_message="HTTP 500")
        eval3 = evaluate_check_rules(db_conn, service, outcome3)
        assert len(eval3["opened_incidents"]) == 0

        # Check total open incidents in database: must be exactly 1
        cur_inc = db_conn.execute("SELECT COUNT(*) as cnt FROM incidents WHERE service_id = ? AND status = 'OPEN'", (service_id,))
        assert cur_inc.fetchone()["cnt"] == 1

def test_endpoint_recovery_lifecycle(db_conn):
    """Verifies that recovery resolves the incident after required consecutive successes."""
    with patch("incidentpulse.monitoring.rules.dispatch_incident_notification"):
        service = create_service(
            name="Recovery Service",
            url="http://127.0.0.1:5050/health",
            allow_local_demo=True,
            endpoint_failure_threshold=1,
            recovery_threshold=2
        )
        service_id = service["id"]

        # Trigger incident immediately (threshold=1)
        fail_outcome = CheckOutcome(is_available=False, http_status=503, response_time_ms=5.0, error_message="Service Unavailable")
        eval_fail = evaluate_check_rules(db_conn, service, fail_outcome)
        assert len(eval_fail["opened_incidents"]) == 1

        # Success 1: Below recovery threshold (recovery_threshold=2)
        succ1 = CheckOutcome(is_available=True, http_status=200, response_time_ms=12.0)
        eval_succ1 = evaluate_check_rules(db_conn, service, succ1)
        assert len(eval_succ1["resolved_incidents"]) == 0

        # Success 2: Reaches recovery threshold -> resolves incident!
        succ2 = CheckOutcome(is_available=True, http_status=200, response_time_ms=15.0)
        eval_succ2 = evaluate_check_rules(db_conn, service, succ2)
        assert len(eval_succ2["resolved_incidents"]) == 1
        assert eval_succ2["new_status"] == "UP"

        # Check database: 0 open incidents, 1 resolved incident with positive duration
        cur_open = db_conn.execute("SELECT COUNT(*) as cnt FROM incidents WHERE service_id = ? AND status = 'OPEN'", (service_id,))
        assert cur_open.fetchone()["cnt"] == 0

        cur_res = db_conn.execute("SELECT * FROM incidents WHERE service_id = ? AND status = 'RESOLVED'", (service_id,))
        res_row = cur_res.fetchone()
        assert res_row is not None
        assert res_row["duration_seconds"] is not None
        assert res_row["duration_seconds"] >= 0.0

def test_latency_threshold_independent_rule(db_conn):
    """Verifies that latency threshold rule operates independently from endpoint failure rule."""
    with patch("incidentpulse.monitoring.rules.dispatch_incident_notification"):
        service = create_service(
            name="Latency Service",
            url="http://127.0.0.1:5050/health",
            allow_local_demo=True,
            endpoint_failure_threshold=2,
            latency_threshold_ms=300.0,
            latency_consecutive_threshold=2,
            recovery_threshold=1
        )
        service_id = service["id"]

        # High latency check 1 (450ms > 300ms)
        outcome1 = CheckOutcome(is_available=True, http_status=200, response_time_ms=450.0)
        eval1 = evaluate_check_rules(db_conn, service, outcome1)
        assert len(eval1["opened_incidents"]) == 0

        # High latency check 2 (500ms > 300ms) -> triggers DEGRADED incident
        outcome2 = CheckOutcome(is_available=True, http_status=200, response_time_ms=500.0)
        eval2 = evaluate_check_rules(db_conn, service, outcome2)
        assert len(eval2["opened_incidents"]) == 1
        assert eval2["new_status"] == "DEGRADED"

        # Verify incident rule_type is LATENCY_THRESHOLD with severity WARNING
        cur = db_conn.execute("SELECT * FROM incidents WHERE id = ?", (eval2["opened_incidents"][0],))
        inc = cur.fetchone()
        assert inc["rule_type"] == "LATENCY_THRESHOLD"
        assert inc["severity"] == "WARNING"

        # Normal latency check (150ms <= 300ms) -> recovers immediately (threshold=1)
        outcome3 = CheckOutcome(is_available=True, http_status=200, response_time_ms=150.0)
        eval3 = evaluate_check_rules(db_conn, service, outcome3)
        assert len(eval3["resolved_incidents"]) == 1
        assert eval3["new_status"] == "UP"
