import time
import signal
import sys
import threading
from datetime import datetime, timezone
import sqlite3
from typing import Optional, Set
from incidentpulse.database import get_db_connection, init_db
from incidentpulse.monitoring.checker import perform_health_check
from incidentpulse.monitoring.rules import evaluate_check_rules

class MonitoringWorker:
    """
    Independent background monitoring worker.
    Runs periodic checks for all active services, evaluates alert rules,
    and handles graceful shutdown without overlapping executions.
    """
    def __init__(self, tick_seconds: int = 1):
        self.tick_seconds = tick_seconds
        self.running = False
        self._active_checks: Set[int] = set()
        self._lock = threading.Lock()

    def check_service(self, service_dict: dict):
        """Executes a health check for a single service in a thread-safe manner."""
        service_id = service_dict["id"]
        with self._lock:
            if service_id in self._active_checks:
                # Avoid overlapping checks for the same service
                return
            self._active_checks.add(service_id)

        conn = get_db_connection()
        try:
            outcome = perform_health_check(
                url=service_dict["url"],
                timeout=service_dict["timeout"],
                expected_status=service_dict["expected_status"],
                follow_redirects=bool(service_dict["follow_redirects"]),
                allow_local_demo=bool(service_dict["allow_local_demo"])
            )
            with conn:
                evaluate_check_rules(conn, service_dict, outcome)
        except Exception as e:
            # Avoid crashing the entire worker on a single check failure
            print(f"[Worker Error] Check failed for service {service_id}: {e}", file=sys.stderr)
        finally:
            conn.close()
            with self._lock:
                self._active_checks.discard(service_id)

    def run_check_cycle(self):
        """
        Queries all active services needing checks based on their configured interval
        and launches checks.
        """
        conn = get_db_connection()
        try:
            # Fetch active services
            cur = conn.execute("""
                SELECT * FROM services 
                WHERE is_active = 1
            """)
            services = [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

        now = datetime.now(timezone.utc)
        for s in services:
            last_checked = s.get("last_checked_at")
            interval = s.get("check_interval", 30)

            should_check = False
            if not last_checked:
                should_check = True
            else:
                try:
                    dt = datetime.fromisoformat(last_checked)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    elapsed = (now - dt).total_seconds()
                    if elapsed >= interval:
                        should_check = True
                except Exception:
                    should_check = True

            if should_check:
                # Run check in a lightweight worker thread so multiple services check concurrently
                t = threading.Thread(target=self.check_service, args=(s,), daemon=True)
                t.start()

    def start(self):
        """Starts the main monitoring worker loop."""
        self.running = True
        print("[IncidentPulse Worker] Monitoring engine started. Press Ctrl+C to terminate.")

        while self.running:
            try:
                self.run_check_cycle()
            except Exception as e:
                print(f"[Worker Error] Error in check cycle: {e}", file=sys.stderr)

            time.sleep(self.tick_seconds)

    def stop(self):
        """Signals the worker to stop gracefully."""
        print("[IncidentPulse Worker] Shutting down monitoring engine...")
        self.running = False


_worker_instance: Optional[MonitoringWorker] = None

def get_monitoring_worker() -> MonitoringWorker:
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = MonitoringWorker(tick_seconds=1)
    return _worker_instance

def run_standalone_worker():
    """Entry point for running the worker as an independent supervisor process."""
    init_db()
    worker = get_monitoring_worker()

    def handle_signal(sig, frame):
        worker.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    worker.start()

if __name__ == "__main__":
    run_standalone_worker()
