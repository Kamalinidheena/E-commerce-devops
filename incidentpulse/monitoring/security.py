import ipaddress
import socket
import urllib.parse
from typing import Tuple, List, Optional
from incidentpulse.config import Config

# Standard permitted external web ports
ALLOWED_EXTERNAL_PORTS = {80, 443, 8080, 8443}

# Authorized local demo ports (e.g. for demo_service.py on 5050)
ALLOWED_LOCAL_DEMO_PORTS = set(range(5000, 10000))

class SecurityValidationError(Exception):
    """Raised when URL or network destination fails security validation."""
    pass

def is_ip_private_or_restricted(ip_str: str) -> Tuple[bool, str]:
    """
    Checks if an IP address string belongs to private, loopback, link-local,
    multicast, reserved, or cloud metadata ranges.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True, f"Invalid IP address format: {ip_str}"

    if ip.is_loopback:
        return True, f"Loopback address rejected: {ip}"
    if ip.is_private:
        return True, f"Private IP address rejected: {ip}"
    if ip.is_link_local:
        return True, f"Link-local address rejected: {ip}"
    if ip.is_multicast:
        return True, f"Multicast address rejected: {ip}"
    if ip.is_reserved:
        return True, f"Reserved address rejected: {ip}"
    if ip.is_unspecified:
        return True, f"Unspecified address rejected: {ip}"
    
    # Specific check for AWS/GCP/Azure link-local metadata address
    if str(ip) == "169.254.169.254":
        return True, "Cloud metadata service IP rejected"

    return False, ""

def resolve_hostname(hostname: str) -> List[str]:
    """
    Resolves a hostname to a list of IP addresses using socket.getaddrinfo.
    """
    resolved_ips = []
    try:
        # Resolve for both IPv4 and IPv6
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in addr_infos:
            ip = sockaddr[0]
            if ip not in resolved_ips:
                resolved_ips.append(ip)
    except socket.gaierror as e:
        raise SecurityValidationError(f"DNS resolution failed for hostname '{hostname}': {e}")
    except Exception as e:
        raise SecurityValidationError(f"Error resolving hostname '{hostname}': {e}")

    if not resolved_ips:
        raise SecurityValidationError(f"No IP address found for hostname '{hostname}'")

    return resolved_ips

def validate_monitoring_url(url: str, allow_local_demo: bool = False) -> Tuple[str, List[str]]:
    """
    Validates a URL against SSRF and security requirements.
    
    Returns:
        (normalized_url, resolved_ips)
    
    Raises:
        SecurityValidationError: if validation fails.
    """
    if not url or not isinstance(url, str):
        raise SecurityValidationError("URL must be a non-empty string.")

    if len(url) > Config.MAX_URL_LENGTH:
        raise SecurityValidationError(f"URL exceeds maximum allowed length of {Config.MAX_URL_LENGTH} characters.")

    parsed = urllib.parse.urlsplit(url.strip())

    # 1. Check scheme
    if parsed.scheme.lower() not in ("http", "https"):
        raise SecurityValidationError(f"Unsupported protocol scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted.")

    # 2. Reject embedded user credentials
    if parsed.username or parsed.password:
        raise SecurityValidationError("Embedded credentials (username/password in URL) are strictly forbidden.")

    # 3. Check hostname
    hostname = parsed.hostname
    if not hostname:
        raise SecurityValidationError("Invalid URL: Missing hostname.")

    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80

    # 4. Local Demo Mode check
    is_localhost = hostname.lower() in ("localhost", "127.0.0.1", "::1")
    
    if is_localhost:
        # Check if local demo is authorized both globally and for this service
        if allow_local_demo and Config.ALLOW_LOCAL_DEMO:
            if port not in ALLOWED_LOCAL_DEMO_PORTS and port not in (80, 443):
                raise SecurityValidationError(
                    f"Port {port} is not allowed for local demo monitoring. "
                    f"Allowed demo ports: 5000-9999 or 80/443."
                )
            return url.strip(), ["127.0.0.1"]
        else:
            raise SecurityValidationError(
                "Access to localhost/loopback is blocked by SSRF policy. "
                "Enable 'Authorized Local Demo' on the service to monitor local test endpoints."
            )

    # 5. External monitoring: Port validation
    if port not in ALLOWED_EXTERNAL_PORTS:
        raise SecurityValidationError(
            f"Port {port} is not permitted for external monitoring. "
            f"Allowed external ports: {sorted(list(ALLOWED_EXTERNAL_PORTS))}."
        )

    # 6. DNS resolution & IP verification
    resolved_ips = resolve_hostname(hostname)
    for ip in resolved_ips:
        is_restricted, reason = is_ip_private_or_restricted(ip)
        if is_restricted:
            raise SecurityValidationError(
                f"Security policy violation: Hostname '{hostname}' resolves to restricted IP ({reason})."
            )

    normalized_url = urllib.parse.urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc,
        parsed.path or "/",
        parsed.query,
        ""  # strip fragments
    ))

    return normalized_url, resolved_ips
