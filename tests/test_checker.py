from unittest.mock import patch, MagicMock
import requests
from incidentpulse.monitoring.checker import perform_health_check

def test_checker_successful_response():
    """Verifies that a 200 OK response marks service as available with valid latency."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.history = []

    with patch("requests.Session.get", return_value=mock_response):
        outcome = perform_health_check("http://127.0.0.1:5050/health", timeout=3, allow_local_demo=True)
        assert outcome.is_available is True
        assert outcome.http_status == 200
        assert outcome.response_time_ms >= 0.0
        assert outcome.error_message is None

def test_checker_http_500_server_error():
    """Verifies that HTTP 500 triggers availability failure."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.headers = {}
    mock_response.history = []

    with patch("requests.Session.get", return_value=mock_response):
        outcome = perform_health_check("http://127.0.0.1:5050/health", timeout=3, allow_local_demo=True)
        assert outcome.is_available is False
        assert outcome.http_status == 500
        assert "HTTP Server Error: 500" in outcome.error_message

def test_checker_connection_refused():
    """Verifies that a connection refused error is handled without crashing."""
    with patch("requests.Session.get", side_effect=requests.exceptions.ConnectionError("ConnectionRefusedError: Connection refused")):
        outcome = perform_health_check("http://127.0.0.1:5050/health", timeout=3, allow_local_demo=True)
        assert outcome.is_available is False
        assert outcome.http_status is None
        assert "refused" in outcome.error_message.lower()

def test_checker_timeout():
    """Verifies that request timeout is safely handled."""
    with patch("requests.Session.get", side_effect=requests.exceptions.Timeout("Read timed out")):
        outcome = perform_health_check("http://127.0.0.1:5050/health", timeout=2, allow_local_demo=True)
        assert outcome.is_available is False
        assert outcome.http_status is None
        assert "timed out" in outcome.error_message.lower()

def test_checker_invalid_url():
    """Verifies that an invalid URL returns a security validation error."""
    outcome = perform_health_check("not-a-valid-url")
    assert outcome.is_available is False
    assert "validation failed" in outcome.error_message.lower()

def test_checker_workflow_assertion_success():
    """Verifies that workflow JSON field assertions pass when matching."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "operational", "queue": 0}
    mock_response.headers = {}
    mock_response.history = []

    with patch("requests.Session.get", return_value=mock_response):
        outcome = perform_health_check(
            "http://127.0.0.1:5050/health",
            allow_local_demo=True,
            workflow_expected_json_key="status",
            workflow_expected_json_val="operational"
        )
        assert outcome.is_available is True
        assert outcome.workflow_passed is True

def test_checker_workflow_assertion_failure():
    """Verifies that workflow JSON field assertions fail when mismatch occurs."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "degraded"}
    mock_response.headers = {}
    mock_response.history = []

    with patch("requests.Session.get", return_value=mock_response):
        outcome = perform_health_check(
            "http://127.0.0.1:5050/health",
            allow_local_demo=True,
            workflow_expected_json_key="status",
            workflow_expected_json_val="operational"
        )
        assert outcome.workflow_passed is False
        assert "Workflow assertion failed" in outcome.error_message
