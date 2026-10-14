import pytest
from unittest.mock import patch, MagicMock
from incidentpulse.monitoring.security import (
    validate_monitoring_url,
    is_ip_private_or_restricted,
    SecurityValidationError
)
from incidentpulse.monitoring.checker import SafeRedirectSession

def test_security_rejects_private_ips():
    """Verifies that RFC 1918 private and cloud metadata IPs are identified as restricted."""
    private_ips = [
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "192.168.1.1",
        "127.0.0.1",
        "::1",
        "169.254.169.254",  # AWS/GCP metadata
        "169.254.1.1"       # link-local
    ]
    for ip in private_ips:
        is_restricted, reason = is_ip_private_or_restricted(ip)
        assert is_restricted is True, f"Failed to restrict {ip}"

def test_security_rejects_localhost_in_external_mode():
    """Verifies that localhost is rejected unless allow_local_demo is explicitly True."""
    with pytest.raises(SecurityValidationError) as exc:
        validate_monitoring_url("http://localhost:80/health", allow_local_demo=False)
    assert "blocked by SSRF policy" in str(exc.value)

    with pytest.raises(SecurityValidationError) as exc:
        validate_monitoring_url("http://127.0.0.1:80/health", allow_local_demo=False)
    assert "blocked by SSRF policy" in str(exc.value)

def test_security_allows_authorized_local_demo():
    """Verifies that authorized local demo mode explicitly permits safe local test ports."""
    url, ips = validate_monitoring_url("http://127.0.0.1:5050/health", allow_local_demo=True)
    assert url == "http://127.0.0.1:5050/health"
    assert "127.0.0.1" in ips

def test_security_rejects_embedded_credentials():
    """Verifies that credentials in URLs are blocked to prevent leaks."""
    with pytest.raises(SecurityValidationError) as exc:
        validate_monitoring_url("http://admin:secretpassword@example.com/health")
    assert "Embedded credentials" in str(exc.value)

def test_security_rejects_unsupported_schemes():
    """Verifies that non-HTTP/HTTPS schemes (ftp, file, gopher, etc.) are blocked."""
    schemes = [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "gopher://example.com",
        "javascript:alert(1)"
    ]
    for url in schemes:
        with pytest.raises(SecurityValidationError) as exc:
            validate_monitoring_url(url)
        assert "Unsupported protocol scheme" in str(exc.value)

def test_security_rejects_dangerous_ports():
    """Verifies that non-web ports (ssh, smtp, etc.) are blocked for external targets."""
    # Mock DNS to return a public IP
    with patch("incidentpulse.monitoring.security.resolve_hostname", return_value=["93.184.216.34"]):
        with pytest.raises(SecurityValidationError) as exc:
            validate_monitoring_url("http://example.com:22/ssh")
        assert "Port 22 is not permitted" in str(exc.value)

def test_security_redirect_validation_blocks_ssrf():
    """Verifies that safe redirect session intercepts redirects to restricted IPs."""
    import requests
    session = SafeRedirectSession(allow_local_demo=False)

    mock_resp = MagicMock()
    mock_resp.is_redirect = True
    mock_resp.url = "http://example.com/test"
    mock_resp.headers = {"location": "http://169.254.169.254/latest/meta-data"}

    with pytest.raises(requests.exceptions.RequestException) as exc:
        list(session.resolve_redirects(mock_resp, MagicMock()))
    assert "SSRF" in str(exc.value)
