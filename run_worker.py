"""
Standalone monitoring worker runner for IncidentPulse.
Runs the background health check scheduler independently from the web server.
"""
import os
import sys

# Ensure root directory is on python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from incidentpulse.monitoring.worker import run_standalone_worker

if __name__ == "__main__":
    run_standalone_worker()
