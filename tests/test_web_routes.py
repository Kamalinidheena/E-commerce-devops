from incidentpulse.models import create_service

def test_web_dashboard_renders(client):
    """Verifies that the main dashboard HTML page loads with 200 OK and brand text."""
    res = client.get("/")
    assert res.status_code == 200
    assert b"IncidentPulse" in res.data
    assert b"Operational Overview" in res.data
    assert b"Monitored Services" in res.data

def test_web_services_page_renders(client):
    """Verifies that the Services management page renders properly."""
    res = client.get("/services")
    assert res.status_code == 200
    assert b"Health Endpoints Management" in res.data

def test_web_service_detail_page_renders(client):
    """Verifies that the Service Detail page renders service metrics or 404."""
    svc = create_service(name="Detail Test Svc", url="http://127.0.0.1:5050/health", allow_local_demo=True)
    
    # Existing service
    res = client.get(f"/services/{svc['id']}")
    assert res.status_code == 200
    assert b"Detail Test Svc" in res.data
    assert b"Endpoint Availability vs. Complete Workflow Health" in res.data

    # Non-existent service returns 404
    res404 = client.get("/services/999999")
    assert res404.status_code == 404

def test_web_alert_rules_renders(client):
    """Verifies Alert Rules configuration page rendering."""
    res = client.get("/alert-rules")
    assert res.status_code == 200
    assert b"Independent Alert Condition Engine" in res.data
    assert b"RULE 1" in res.data
    assert b"RULE 2" in res.data

def test_web_incidents_page_renders(client):
    """Verifies Incident Center renders with filter controls."""
    res = client.get("/incidents")
    assert res.status_code == 200
    assert b"Active & Historical Incidents" in res.data

def test_web_notifications_page_renders(client):
    """Verifies Notification Center renders configuration form and test button."""
    res = client.get("/notifications")
    assert res.status_code == 200
    assert b"Webhook Alert Configuration" in res.data
    assert b"Send Test Notification Now" in res.data

def test_web_audit_page_renders(client):
    """Verifies persistent Audit and Event history page rendering."""
    res = client.get("/audit")
    assert res.status_code == 200
    assert b"Immutable Audit & Event Trail" in res.data

def test_web_settings_page_renders(client):
    """Verifies Settings and documentation page rendering."""
    res = client.get("/settings")
    assert res.status_code == 200
    assert b"Settings & Documentation" in res.data
    assert b"Deep Dive: Endpoint Availability" in res.data
