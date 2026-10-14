import json
from unittest.mock import patch, MagicMock

def test_api_state_empty_db(client):
    """Verifies that an empty database returns accurate zero metrics, not fake data."""
    res = client.get("/api/state")
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["total_services"] == 0
    assert data["services_up"] == 0
    assert data["services_down"] == 0
    assert data["open_incidents"] == 0
    assert data["last_check_time"] is None

def test_create_service_valid(client):
    """Verifies successful creation of a monitored service."""
    payload = {
        "name": "Production API",
        "url": "http://127.0.0.1:5050/health",
        "check_interval": 10,
        "timeout": 3,
        "allow_local_demo": True,
        "endpoint_failure_threshold": 3,
        "latency_threshold_ms": 450.0
    }
    res = client.post("/api/services", json=payload)
    assert res.status_code == 201
    json_data = res.get_json()
    assert json_data["success"] is True
    svc = json_data["data"]
    assert svc["name"] == "Production API"
    assert svc["current_status"] == "UNKNOWN"  # Must not claim UP until check runs!
    assert len(svc["alert_rules"]) == 2

def test_create_service_invalid_input(client):
    """Verifies rejection of invalid interval, timeout, or missing name."""
    # Missing URL
    res1 = client.post("/api/services", json={"name": "Test"})
    assert res1.status_code == 400

    # Short name
    res2 = client.post("/api/services", json={"name": "x", "url": "http://127.0.0.1:5050/health"})
    assert res2.status_code == 400

    # Negative or too low check interval (< 1s in test config)
    res3 = client.post("/api/services", json={
        "name": "Valid Name",
        "url": "http://127.0.0.1:5050/health",
        "check_interval": 0,
        "allow_local_demo": True
    })
    assert res3.status_code == 400

def test_patch_and_delete_service(client):
    """Verifies update and deletion of a service."""
    # Create service
    create_res = client.post("/api/services", json={
        "name": "Old Name",
        "url": "http://127.0.0.1:5050/health",
        "allow_local_demo": True
    })
    service_id = create_res.get_json()["data"]["id"]

    # Patch service
    patch_res = client.patch(f"/api/services/{service_id}", json={
        "name": "New Name",
        "check_interval": 25
    })
    assert patch_res.status_code == 200
    assert patch_res.get_json()["data"]["name"] == "New Name"
    assert patch_res.get_json()["data"]["check_interval"] == 25

    # Delete service
    del_res = client.delete(f"/api/services/{service_id}")
    assert del_res.status_code == 200

    # Confirm 404 afterwards
    get_res = client.get(f"/api/services/{service_id}")
    assert get_res.status_code == 404

def test_manual_check_rate_limit(client):
    """Verifies that manual check executes and enforces rate limit cooldown."""
    create_res = client.post("/api/services", json={
        "name": "Check Svc",
        "url": "http://127.0.0.1:5050/health",
        "allow_local_demo": True
    })
    service_id = create_res.get_json()["data"]["id"]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.history = []

    with patch("requests.Session.get", return_value=mock_resp):
        # First check succeeds
        res1 = client.post(f"/api/services/{service_id}/check")
        assert res1.status_code == 200
        assert res1.get_json()["outcome"]["is_available"] is True

        # Immediate second check triggers 429 Rate Limit
        res2 = client.post(f"/api/services/{service_id}/check")
        assert res2.status_code == 429
        assert "Rate limit" in res2.get_json()["error"]
