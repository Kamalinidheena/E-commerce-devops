from flask import Blueprint, render_template, abort
from incidentpulse.models import (
    get_all_services,
    get_service_by_id,
    get_dashboard_summary,
    get_incidents_list,
    get_incident_by_id,
    get_service_check_history,
    get_notification_logs,
    get_audit_logs
)
from incidentpulse.database import get_db_connection
from incidentpulse.monitoring.notifications import get_notification_config
from incidentpulse.config import Config

web_bp = Blueprint("web", __name__)

@web_bp.route("/")
def dashboard():
    """Renders the main Overview Dashboard with real database stats."""
    summary = get_dashboard_summary()
    services = get_all_services()
    incidents, _ = get_incidents_list(limit=10)
    return render_template(
        "index.html",
        summary=summary,
        services=services,
        recent_incidents=incidents
    )

@web_bp.route("/services")
def services_page():
    """Renders the Services management page."""
    services = get_all_services()
    return render_template(
        "services.html",
        services=services,
        allow_demo_default=Config.ALLOW_LOCAL_DEMO
    )

@web_bp.route("/services/<int:service_id>")
def service_detail_page(service_id: int):
    """Renders Service Details page."""
    service = get_service_by_id(service_id)
    if not service:
        abort(404)
    history = get_service_check_history(service_id, limit=30)
    incidents, _ = get_incidents_list(service_id=service_id, limit=20)
    return render_template(
        "service_detail.html",
        service=service,
        history=history,
        incidents=incidents
    )

@web_bp.route("/alert-rules")
def alert_rules_page():
    """Renders the Alert Rules configuration page."""
    services = get_all_services()
    return render_template(
        "alert_rules.html",
        services=services
    )

@web_bp.route("/incidents")
def incidents_page():
    """Renders the Incident Center."""
    services = get_all_services()
    incidents, total = get_incidents_list(limit=50)
    return render_template(
        "incidents.html",
        services=services,
        incidents=incidents,
        total=total
    )

@web_bp.route("/incidents/<int:incident_id>")
def incident_detail_page(incident_id: int):
    """Renders single Incident detail view with timeline and delivery logs."""
    incident = get_incident_by_id(incident_id)
    if not incident:
        abort(404)
    return render_template(
        "incident_detail.html",
        incident=incident
    )

@web_bp.route("/notifications")
def notifications_page():
    """Renders Notification Center with config and delivery history."""
    conn = get_db_connection()
    try:
        config = get_notification_config(conn)
        logs, total = get_notification_logs(limit=50)
        return render_template(
            "notifications.html",
            config=dict(config) if config else None,
            logs=logs,
            total=total
        )
    finally:
        conn.close()

@web_bp.route("/audit")
def audit_page():
    """Renders persistent Audit and Event History."""
    logs, total = get_audit_logs(limit=100)
    return render_template(
        "audit.html",
        logs=logs,
        total=total
    )

@web_bp.route("/settings")
def settings_page():
    """Renders system configuration, SSRF guidance, and demo help."""
    return render_template(
        "settings.html",
        config=Config
    )
