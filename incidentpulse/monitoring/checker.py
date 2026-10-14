import time
import requests
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from incidentpulse.config import Config
from incidentpulse.monitoring.security import validate_monitoring_url, SecurityValidationError

@dataclass
class CheckOutcome:
    """Encapsulates the result of a single health check execution."""
    is_available: bool
    http_status: Optional[int]
    response_time_ms: float
    error_message: Optional[str] = None
    resolved_ip: Optional[str] = None
    workflow_passed: bool = True
    details: Dict[str, Any] = field(default_factory=dict)

class SafeRedirectSession(requests.Session):
    """
    Requests session that re-validates each redirect target against SSRF rules.
    """
    def __init__(self, allow_local_demo: bool = False, max_redirects: int = 5):
        super().__init__()
        self.allow_local_demo = allow_local_demo
        self.max_redirect_limit = max_redirects

    def resolve_redirects(self, resp, req, stream=False, timeout=None,
                          verify=True, cert=None, proxies=None, yield_requests=False, **adapter_kwargs):
        history = [resp]
        current_resp = resp
        redirect_count = 0

        while current_resp.is_redirect:
            redirect_count += 1
            if redirect_count > self.max_redirect_limit:
                raise requests.exceptions.TooManyRedirects(
                    f"Exceeded maximum redirect limit of {self.max_redirect_limit}"
                )

            location = current_resp.headers.get("location")
            if not location:
                break

            target_url = urllib.parse.urljoin(current_resp.url, location)
            
            # Revalidate redirect URL against SSRF policy
            try:
                validate_monitoring_url(target_url, allow_local_demo=self.allow_local_demo)
            except SecurityValidationError as e:
                raise requests.exceptions.RequestException(f"Redirect blocked by SSRF policy: {e}")

            # Continue standard resolution
            gen = super().resolve_redirects(
                current_resp, req, stream=stream, timeout=timeout,
                verify=verify, cert=cert, proxies=proxies, yield_requests=yield_requests, **adapter_kwargs
            )
            try:
                current_resp = next(gen)
            except StopIteration:
                break
            yield current_resp

def perform_health_check(
    url: str,
    timeout: int = 5,
    expected_status: int = 200,
    follow_redirects: bool = True,
    allow_local_demo: bool = False,
    workflow_expected_json_key: Optional[str] = None,
    workflow_expected_json_val: Optional[str] = None
) -> CheckOutcome:
    """
    Performs an authentic, timed HTTP health check on the given URL.
    Validates the destination before connecting, handles network errors gracefully,
    and returns an authentic CheckOutcome.
    """
    # 1. URL validation & SSRF check
    try:
        normalized_url, resolved_ips = validate_monitoring_url(url, allow_local_demo=allow_local_demo)
        resolved_ip = resolved_ips[0] if resolved_ips else None
    except SecurityValidationError as e:
        return CheckOutcome(
            is_available=False,
            http_status=None,
            response_time_ms=0.0,
            error_message=f"Security/URL validation failed: {e}",
            resolved_ip=None,
            workflow_passed=False
        )

    # 2. Execute HTTP check with high-resolution timer
    headers = {
        "User-Agent": "IncidentPulse-HealthMonitor/1.0 (+https://github.com/incidentpulse)",
        "Accept": "application/json, text/html, */*"
    }

    session = SafeRedirectSession(allow_local_demo=allow_local_demo, max_redirects=Config.MAX_REDIRECTS)
    start_time = time.perf_counter()
    
    try:
        response = session.get(
            normalized_url,
            headers=headers,
            timeout=timeout,
            allow_redirects=follow_redirects,
            stream=False
        )
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        http_code = response.status_code

        # 3. Availability evaluation
        is_available = True
        error_msg = None
        workflow_passed = True

        # Check HTTP status code
        if http_code >= 500:
            is_available = False
            error_msg = f"HTTP Server Error: {http_code}"
        elif expected_status and http_code != expected_status:
            is_available = False
            error_msg = f"Unexpected HTTP status {http_code} (expected {expected_status})"

        # 4. Optional Workflow check (JSON content assertion)
        if is_available and workflow_expected_json_key:
            try:
                data = response.json()
                actual_val = str(data.get(workflow_expected_json_key, ""))
                if workflow_expected_json_val and actual_val != workflow_expected_json_val:
                    workflow_passed = False
                    error_msg = f"Workflow assertion failed: '{workflow_expected_json_key}' was '{actual_val}', expected '{workflow_expected_json_val}'"
            except Exception as e:
                workflow_passed = False
                error_msg = f"Workflow JSON parsing failed: {e}"

        return CheckOutcome(
            is_available=is_available,
            http_status=http_code,
            response_time_ms=round(duration_ms, 2),
            error_message=error_msg,
            resolved_ip=resolved_ip,
            workflow_passed=workflow_passed,
            details={
                "headers": dict(response.headers),
                "redirect_count": len(response.history)
            }
        )

    except requests.exceptions.Timeout:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return CheckOutcome(
            is_available=False,
            http_status=None,
            response_time_ms=round(duration_ms, 2),
            error_message=f"Request timed out after {timeout} seconds",
            resolved_ip=resolved_ip,
            workflow_passed=False
        )
    except requests.exceptions.ConnectionError as e:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        # Sanitize error message to avoid exposing raw stack or internal details
        clean_err = "Connection refused or host unreachable"
        err_str = str(e)
        if "ConnectionRefusedError" in err_str or "actively refused" in err_str:
            clean_err = "Connection refused by target host"
        elif "NameResolutionError" in err_str or "getaddrinfo failed" in err_str:
            clean_err = "DNS resolution error during connection"

        return CheckOutcome(
            is_available=False,
            http_status=None,
            response_time_ms=round(duration_ms, 2),
            error_message=clean_err,
            resolved_ip=resolved_ip,
            workflow_passed=False
        )
    except requests.exceptions.RequestException as e:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return CheckOutcome(
            is_available=False,
            http_status=None,
            response_time_ms=round(duration_ms, 2),
            error_message=f"Network error: {str(e)[:120]}",
            resolved_ip=resolved_ip,
            workflow_passed=False
        )
    finally:
        session.close()
