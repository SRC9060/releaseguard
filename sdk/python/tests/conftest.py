"""
Pytest configuration for SDK tests.
Re-uses backend database fixtures for integration testing.
"""
import importlib.util
from pathlib import Path

backend_conftest_path = Path(__file__).resolve().parents[3] / "backend" / "tests" / "conftest.py"
spec = importlib.util.spec_from_file_location("backend_conftest", backend_conftest_path)
backend_conftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend_conftest)

engine = backend_conftest.engine
clean_db = backend_conftest.clean_db
client = backend_conftest.client

__all__ = ["engine", "clean_db", "client"]
