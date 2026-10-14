"""
Local development server runner for IncidentPulse.
Starts Flask web application with the built-in monitoring scheduler enabled for simple evaluation.
"""
import os
import sys

# Ensure root directory is on python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from incidentpulse.app import create_app
from incidentpulse.config import Config

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting IncidentPulse on http://localhost:{port}...")
    print("Press Ctrl+C to terminate.")
    
    # In local development runner, start worker thread in-process for single-command evaluation
    app = create_app(config_class=Config, start_in_process_worker=True)
    app.run(host="0.0.0.0", port=port, debug=False)
