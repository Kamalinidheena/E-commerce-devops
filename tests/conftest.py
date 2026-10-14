import os
import sys
import tempfile
import pytest

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from incidentpulse.app import create_app
from incidentpulse.config import TestConfig
from incidentpulse.database import init_db, set_db_path, get_db_connection

@pytest.fixture
def temp_db():
    """Creates an isolated temporary SQLite database for each test."""
    fd, path = tempfile.mkstemp(suffix="_test.db")
    os.close(fd)
    set_db_path(path)
    init_db(path)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass

@pytest.fixture
def app(temp_db):
    """Creates a Flask test application with an isolated temporary database."""
    app = create_app(config_class=TestConfig, db_path=temp_db, start_in_process_worker=False)
    app.config["TESTING"] = True
    return app

@pytest.fixture
def client(app):
    """Test client for HTTP requests."""
    return app.test_client()

@pytest.fixture
def db_conn(temp_db):
    """Direct database connection to temporary database."""
    conn = get_db_connection()
    yield conn
    conn.close()
