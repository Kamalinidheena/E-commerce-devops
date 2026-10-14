import time
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from incidentpulse.database import get_db_connection
from incidentpulse.monitoring.security import validate_monitoring_url, SecurityValidationError
from incidentpulse.monitoring.checker import perform_health_check
from incidentpulse.monitoring.rules import evaluate_check_rules
from incidentpulse.monitoring.notifications import (
    get_notification_config,
    send_test_notification
)
from incidentpulse.models import (
    create_service,
    get_service_by_id,
    get_all_services,
    update_service,
    delete_service,
    get_dashboard_summary,
    get_service_check_history,
    get_incidents_list,
    get_incident_by_id,
    get_notification_logs,
    get_audit_logs,
    now_iso
)
from incidentpulse.config import Config

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Rate limit tracker for manual checks (service_id -> timestamp)
_manual_check_tracker = {}

@api_bp.route("/health", methods=["GET"])
def health():
    """System health endpoint reporting database and component state."""
    db_ok = False
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False

    return jsonify({
        "status": "healthy" if db_ok else "unhealthy",
        "service": "IncidentPulse",
        "database": "connected" if db_ok else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200 if db_ok else 503

@api_bp.route("/state", methods=["GET"])
def get_state():
    """Returns the live aggregated dashboard summary state."""
    summary = get_dashboard_summary()
    return jsonify({
        "success": True,
        "data": summary
    }), 200

# ==================== SERVICES ====================

@api_bp.route("/services", methods=["GET"])
def list_services():
    """Lists all monitored services."""
    services = get_all_services()
    return jsonify({
        "success": True,
        "count": len(services),
        "data": services
    }), 200

@api_bp.route("/services", methods=["POST"])
def add_service():
    """Creates a new service with validated URL and alert thresholds."""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body provided"}), 400

    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    description = data.get("description", "").strip()

    if not name or len(name) < 2 or len(name) > 100:
        return jsonify({"error": "Service name must be between 2 and 100 characters"}), 400

    if not url:
        return jsonify({"error": "Service URL is required"}), 400

    # Service count limit
    existing = get_all_services()
    if len(existing) >= Config.MAX_SERVICES:
        return jsonify({"error": f"Maximum service capacity reached ({Config.MAX_SERVICES} services)"}), 400

    # Numeric options with bounded validation
    try:
        check_interval = int(data.get("check_interval", 30))
        if check_interval < Config.MONITORING_MIN_INTERVAL or check_interval > Config.MONITORING_MAX_INTERVAL:
            return jsonify({"error": f"Check interval must be between {Config.MONITORING_MIN_INTERVAL} and {Config.MONITORING_MAX_INTERVAL} seconds"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid check_interval format"}), 400

    try:
        timeout = int(data.get("timeout", 5))
        if timeout < 1 or timeout > Config.MONITORING_MAX_TIMEOUT:
            return jsonify({"error": f"Timeout must be between 1 and {Config.MONITORING_MAX_TIMEOUT} seconds"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid timeout format"}), 400

    try:
        expected_status = int(data.get("expected_status", 200))
        if expected_status < 100 or expected_status > 599:
            return jsonify({"error": "Expected status must be a valid HTTP status code (100-599)"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid expected_status format"}), 400

    follow_redirects = bool(data.get("follow_redirects", True))
    allow_local_demo = bool(data.get("allow_local_demo", False))

    # Alert thresholds
    try:
        endpoint_failure_thresh = int(data.get("endpoint_failure_threshold", 2))
        if endpoint_failure_thresh < 1 or endpoint_failure_thresh > 20:
            return jsonify({"error": "Endpoint failure threshold must be between 1 and 20"}), 400

        latency_thresh_ms = float(data.get("latency_threshold_ms", 500.0))
        if latency_thresh_ms < 10.0 or latency_thresh_ms > 30000.0:
            return jsonify({"error": "Latency threshold must be between 10ms and 30,000ms"}), 400

        latency_consec_thresh = int(data.get("latency_consecutive_threshold", 2))
        if latency_consec_thresh < 1 or latency_consec_thresh > 20:
            return jsonify({"error": "Latency consecutive threshold must be between 1 and 20"}), 400

        recovery_thresh = int(data.get("recovery_threshold", 2))
        if recovery_thresh < 1 or recovery_thresh > 20:
            return jsonify({"error": "Recovery threshold must be between 1 and 20"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid threshold parameter provided"}), 400

    # SSRF & URL validation
    try:
        validate_monitoring_url(url, allow_local_demo=allow_local_demo)
    except SecurityValidationError as e:
        return jsonify({"error": str(e)}), 400

    service = create_service(
        name=name,
        url=url,
        description=description,
        check_interval=check_interval,
        timeout=timeout,
        expected_status=expected_status,
        follow_redirects=follow_redirects,
        allow_local_demo=allow_local_demo,
        endpoint_failure_threshold=endpoint_failure_thresh,
        latency_threshold_ms=latency_thresh_ms,
        latency_consecutive_threshold=latency_consec_thresh,
        recovery_threshold=recovery_thresh
    )

    return jsonify({
        "success": True,
        "message": f"Service '{name}' added successfully",
        "data": service
    }), 201

@api_bp.route("/services/<int:service_id>", methods=["GET"])
def get_service(service_id: int):
    """Retrieves full service details, rules, and latest checks."""
    service = get_service_by_id(service_id)
    if not service:
        return jsonify({"error": f"Service #{service_id} not found"}), 404
    return jsonify({"success": True, "data": service}), 200

@api_bp.route("/services/<int:service_id>", methods=["PATCH"])
def patch_service(service_id: int):
    """Updates service configuration or pauses/resumes monitoring."""
    service = get_service_by_id(service_id)
    if not service:
        return jsonify({"error": f"Service #{service_id} not found"}), 404

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body provided"}), 400

    updates = {}
    if "name" in data:
        name = str(data["name"]).strip()
        if len(name) < 2 or len(name) > 100:
            return jsonify({"error": "Service name must be between 2 and 100 characters"}), 400
        updates["name"] = name

    if "description" in data:
        updates["description"] = str(data["description"]).strip()

    if "url" in data:
        url = str(data["url"]).strip()
        allow_local_demo = bool(data.get("allow_local_demo", service["allow_local_demo"]))
        try:
            validate_monitoring_url(url, allow_local_demo=allow_local_demo)
        except SecurityValidationError as e:
            return jsonify({"error": str(e)}), 400
        updates["url"] = url

    if "check_interval" in data:
        try:
            interval = int(data["check_interval"])
            if interval < Config.MONITORING_MIN_INTERVAL or interval > Config.MONITORING_MAX_INTERVAL:
                return jsonify({"error": f"Check interval must be between {Config.MONITORING_MIN_INTERVAL} and {Config.MONITORING_MAX_INTERVAL}s"}), 400
            updates["check_interval"] = interval
        except ValueError:
            return jsonify({"error": "Invalid check_interval"}), 400

    if "timeout" in data:
        try:
            t = int(data["timeout"])
            if t < 1 or t > Config.MONITORING_MAX_TIMEOUT:
                return jsonify({"error": f"Timeout must be between 1 and {Config.MONITORING_MAX_TIMEOUT}s"}), 400
            updates["timeout"] = t
        except ValueError:
            return jsonify({"error": "Invalid timeout"}), 400

    if "is_active" in data:
        updates["is_active"] = 1 if data["is_active"] else 0

    if "follow_redirects" in data:
        updates["follow_redirects"] = 1 if data["follow_redirects"] else 0

    if "allow_local_demo" in data:
        updates["allow_local_demo"] = 1 if data["allow_local_demo"] else 0

    updated = update_service(service_id, updates)
    return jsonify({"success": True, "data": updated}), 200

@api_bp.route("/services/<int:service_id>", methods=["DELETE"])
def remove_service(service_id: int):
    """Deletes a service and all its associated data."""
    success = delete_service(service_id)
    if not success:
        return jsonify({"error": f"Service #{service_id} not found"}), 404
    return jsonify({"success": True, "message": f"Service #{service_id} deleted successfully"}), 200

@api_bp.route("/services/<int:service_id>/check", methods=["POST"])
def manual_check(service_id: int):
    """Triggers an immediate health check, rate-limited by cooldown."""
    service = get_service_by_id(service_id)
    if not service:
        return jsonify({"error": f"Service #{service_id} not found"}), 404

    now = time.time()
    last_manual = _manual_check_tracker.get(service_id, 0)
    cooldown = Config.MANUAL_CHECK_COOLDOWN_SECONDS
    if (now - last_manual) < cooldown:
        remaining = round(cooldown - (now - last_manual), 1)
        return jsonify({
            "error": f"Rate limit reached. Please wait {remaining}s before checking this service again."
        }), 429

    _manual_check_tracker[service_id] = now

    outcome = perform_health_check(
        url=service["url"],
        timeout=service["timeout"],
        expected_status=service["expected_status"],
        follow_redirects=bool(service["follow_redirects"]),
        allow_local_demo=bool(service["allow_local_demo"])
    )

    conn = get_db_connection()
    try:
        with conn:
            eval_result = evaluate_check_rules(conn, service, outcome)
    finally:
        conn.close()

    return jsonify({
        "success": True,
        "service_id": service_id,
        "outcome": {
            "is_available": outcome.is_available,
            "http_status": outcome.http_status,
            "response_time_ms": outcome.response_time_ms,
            "error_message": outcome.error_message,
            "resolved_ip": outcome.resolved_ip
        },
        "evaluation": {
            "new_status": eval_result["new_status"],
            "opened_incidents": eval_result["opened_incidents"],
            "resolved_incidents": eval_result["resolved_incidents"]
        }
    }), 200

@api_bp.route("/services/<int:service_id>/checks", methods=["GET"])
def get_service_checks(service_id: int):
    """Returns chronological check history for charting and logs."""
    service = get_service_by_id(service_id)
    if not service:
        return jsonify({"error": f"Service #{service_id} not found"}), 404

    limit = min(int(request.args.get("limit", 60)), 500)
    history = get_service_check_history(service_id, limit=limit)
    return jsonify({
        "success": True,
        "service_id": service_id,
        "count": len(history),
        "data": history
    }), 200

# ==================== INCIDENTS ====================

@api_bp.route("/incidents", methods=["GET"])
def list_incidents():
    """Lists incidents with filtering and pagination."""
    service_id = request.args.get("service_id", type=int)
    status = request.args.get("status")
    severity = request.args.get("severity")
    limit = min(request.args.get("limit", default=50, type=int), 200)
    offset = max(request.args.get("offset", default=0, type=int), 0)

    incidents, total = get_incidents_list(
        service_id=service_id,
        status=status,
        severity=severity,
        limit=limit,
        offset=offset
    )

    return jsonify({
        "success": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": incidents
    }), 200

@api_bp.route("/incidents/<int:incident_id>", methods=["GET"])
def get_incident(incident_id: int):
    """Returns incident detail, timing, and delivery logs."""
    incident = get_incident_by_id(incident_id)
    if not incident:
        return jsonify({"error": f"Incident #{incident_id} not found"}), 404
    return jsonify({"success": True, "data": incident}), 200

# ==================== NOTIFICATIONS ====================

@api_bp.route("/notifications", methods=["GET"])
def get_notifications():
    """Returns notification config and recent delivery logs."""
    conn = get_db_connection()
    try:
        config = get_notification_config(conn)
        limit = min(request.args.get("limit", default=25, type=int), 100)
        offset = max(request.args.get("offset", default=0, type=int), 0)
        logs, total = get_notification_logs(limit=limit, offset=offset)
        return jsonify({
            "success": True,
            "config": dict(config) if config else None,
            "total_logs": total,
            "logs": logs
        }), 200
    finally:
        conn.close()

@api_bp.route("/notifications/config", methods=["POST"])
def update_notification_settings():
    """Updates the webhook notification settings."""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body provided"}), 400

    webhook_url = data.get("webhook_url", "").strip()
    timeout = int(data.get("timeout_seconds", 5))
    max_retries = int(data.get("max_retries", 3))
    is_enabled = 1 if data.get("is_enabled", True) else 0

    if webhook_url:
        try:
            validate_monitoring_url(webhook_url, allow_local_demo=Config.ALLOW_LOCAL_DEMO)
        except SecurityValidationError as e:
            return jsonify({"error": f"Invalid webhook URL: {e}"}), 400

    if timeout < 1 or timeout > 30:
        return jsonify({"error": "Timeout must be between 1 and 30 seconds"}), 400

    if max_retries < 1 or max_retries > 5:
        return jsonify({"error": "Max retries must be between 1 and 5"}), 400

    conn = get_db_connection()
    try:
        with conn:
            ts = now_iso()
            cur = conn.execute("SELECT id FROM notification_configs ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                conn.execute("""
                    UPDATE notification_configs 
                    SET webhook_url = ?, timeout_seconds = ?, max_retries = ?, is_enabled = ?, updated_at = ?
                    WHERE id = ?
                """, (webhook_url, timeout, max_retries, is_enabled, ts, row["id"]))
            else:
                conn.execute("""
                    INSERT INTO notification_configs (channel_type, webhook_url, timeout_seconds, max_retries, is_enabled, created_at, updated_at)
                    VALUES ('WEBHOOK', ?, ?, ?, ?, ?, ?)
                """, (webhook_url, timeout, max_retries, is_enabled, ts, ts))
        return jsonify({"success": True, "message": "Notification configuration saved"}), 200
    finally:
        conn.close()

@api_bp.route("/notifications/test", methods=["POST"])
def test_notification():
    """Sends a real test notification to verify delivery."""
    data = request.get_json(silent=True) or {}
    custom_url = data.get("webhook_url")

    conn = get_db_connection()
    try:
        with conn:
            result = send_test_notification(conn, target_url=custom_url)
    finally:
        conn.close()

    status_code = 200 if result["success"] else 400
    return jsonify({
        "success": result["success"],
        "result": result
    }), status_code

# ==================== ALERT RULES ====================

@api_bp.route("/services/<int:service_id>/rules", methods=["GET"])
def get_service_rules(service_id: int):
    """Retrieves alert rules for a specific service."""
    service = get_service_by_id(service_id)
    if not service:
        return jsonify({"error": f"Service #{service_id} not found"}), 404
    return jsonify({"success": True, "data": service.get("alert_rules", [])}), 200

@api_bp.route("/services/<int:service_id>/rules/<int:rule_id>", methods=["PATCH"])
def update_service_rule(service_id: int, rule_id: int):
    """Updates a specific alert rule's thresholds."""
    data = request.get_json(silent=True) or {}
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.execute("SELECT * FROM alert_rules WHERE id = ? AND service_id = ?", (rule_id, service_id))
            rule = cur.fetchone()
            if not rule:
                return jsonify({"error": f"Rule #{rule_id} not found for service #{service_id}"}), 404

            updates = []
            params = []
            if "threshold_value" in data:
                updates.append("threshold_value = ?")
                params.append(float(data["threshold_value"]))
            if "consecutive_threshold" in data:
                updates.append("consecutive_threshold = ?")
                params.append(int(data["consecutive_threshold"]))
            if "recovery_threshold" in data:
                updates.append("recovery_threshold = ?")
                params.append(int(data["recovery_threshold"]))
            if "is_enabled" in data:
                updates.append("is_enabled = ?")
                params.append(1 if data["is_enabled"] else 0)

            if updates:
                ts = now_iso()
                updates.append("updated_at = ?")
                params.append(ts)
                params.append(rule_id)
                conn.execute(f"UPDATE alert_rules SET {', '.join(updates)} WHERE id = ?", params)

        return jsonify({"success": True, "message": "Alert rule updated"}), 200
    finally:
        conn.close()

# ==================== AUDIT LOGS ====================

@api_bp.route("/audit", methods=["GET"])
def list_audit_logs():
    """Returns persistent audit log trail."""
    limit = min(request.args.get("limit", default=50, type=int), 200)
    offset = max(request.args.get("offset", default=0, type=int), 0)
    logs, total = get_audit_logs(limit=limit, offset=offset)
    return jsonify({
        "success": True,
        "total": total,
        "data": logs
    }), 200
