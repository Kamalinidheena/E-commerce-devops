"""
WSGI entrypoint for IncidentPulse production deployment.
Run with Gunicorn:
    gunicorn -w 4 -b 0.0.0.0:5000 wsgi:application
"""
import os
import sys

# Ensure root directory is on python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from incidentpulse.app import create_app
from incidentpulse.config import Config

application = create_app(config_class=Config, start_in_process_worker=False)

if __name__ == "__main__":
    application.run(host=Config.HOST, port=Config.PORT)
