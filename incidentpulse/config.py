import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Config:
    """IncidentPulse Application Configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "incidentpulse-dev-secret-key-replace-in-prod")
    DEBUG = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    
    # Database
    DB_NAME = os.environ.get("DB_NAME", "incidentpulse.db")
    DB_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "instance" / DB_NAME))
    
    # Monitoring Engine Limits
    MONITORING_DEFAULT_INTERVAL = int(os.environ.get("MONITORING_DEFAULT_INTERVAL", "30"))
    MONITORING_MIN_INTERVAL = int(os.environ.get("MONITORING_MIN_INTERVAL", "5"))
    MONITORING_MAX_INTERVAL = int(os.environ.get("MONITORING_MAX_INTERVAL", "3600"))
    MONITORING_DEFAULT_TIMEOUT = int(os.environ.get("MONITORING_DEFAULT_TIMEOUT", "5"))
    MONITORING_MAX_TIMEOUT = int(os.environ.get("MONITORING_MAX_TIMEOUT", "30"))
    
    # SSRF & Security
    # ALLOW_LOCAL_DEMO should be strictly set to False in real production environments!
    ALLOW_LOCAL_DEMO = os.environ.get("ALLOW_LOCAL_DEMO", "true").lower() in ("1", "true", "yes")
    MAX_URL_LENGTH = 2048
    MAX_REDIRECTS = 5
    MAX_SERVICES = int(os.environ.get("MAX_SERVICES", "50"))
    
    # Rate Limiting & Notifications
    MANUAL_CHECK_COOLDOWN_SECONDS = int(os.environ.get("MANUAL_CHECK_COOLDOWN_SECONDS", "3"))
    DEFAULT_WEBHOOK_URL = os.environ.get("DEFAULT_WEBHOOK_URL", "")
    WEBHOOK_TIMEOUT_SECONDS = int(os.environ.get("WEBHOOK_TIMEOUT_SECONDS", "5"))
    WEBHOOK_MAX_RETRIES = int(os.environ.get("WEBHOOK_MAX_RETRIES", "3"))
    
    # Server Binding
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", "5000"))


class TestConfig(Config):
    """Configuration for automated test suite."""
    TESTING = True
    DEBUG = False
    DB_NAME = "test_incidentpulse.db"
    DB_PATH = ":memory:"
    ALLOW_LOCAL_DEMO = True
    MONITORING_DEFAULT_INTERVAL = 5
    MONITORING_MIN_INTERVAL = 1
    MONITORING_DEFAULT_TIMEOUT = 2
    WEBHOOK_TIMEOUT_SECONDS = 2
    WEBHOOK_MAX_RETRIES = 2
