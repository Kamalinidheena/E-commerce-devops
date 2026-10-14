import os
import atexit
import threading
from flask import Flask, jsonify, render_template, request
from incidentpulse.config import Config
from incidentpulse.database import init_db, set_db_path
from incidentpulse.routes.api import api_bp
from incidentpulse.routes.web import web_bp

_in_process_worker_thread = None

def create_app(config_class=Config, db_path=None, start_in_process_worker=False) -> Flask:
    """Application factory for IncidentPulse."""
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates"
    )
    app.config.from_object(config_class)

    # Configure database
    if db_path:
        set_db_path(db_path)
    else:
        set_db_path(app.config.get("DB_PATH", Config.DB_PATH))

    # Initialize tables and indices
    init_db()

    # Register blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(web_bp)

    # Template context helpers
    @app.context_processor
    def inject_globals():
        return {
            "app_name": "IncidentPulse",
            "app_version": "1.0.0",
            "year": 2026
        }

    # Error Handlers
    @app.errorhandler(404)
    def not_found_error(err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found"}), 404
        return render_template("base.html", error_title="404 - Page Not Found", error_message="The requested page does not exist."), 404

    @app.errorhandler(500)
    def internal_error(err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "An internal server error occurred"}), 500
        return render_template("base.html", error_title="500 - Server Error", error_message="An unexpected internal server error occurred."), 500

    # Optional controlled in-process worker for simple single-command local demo execution
    # Strictly controlled so Gunicorn or multi-worker setups won't duplicate!
    if start_in_process_worker and os.environ.get("WERKZEUG_RUN_MAIN") != "false":
        global _in_process_worker_thread
        from incidentpulse.monitoring.worker import get_monitoring_worker
        worker = get_monitoring_worker()
        if not worker.running:
            _in_process_worker_thread = threading.Thread(target=worker.start, daemon=True)
            _in_process_worker_thread.start()
            atexit.register(worker.stop)

    return app
