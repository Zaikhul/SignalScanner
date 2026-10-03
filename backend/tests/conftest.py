import pytest
from app.main import app
from app.core.security import verify_operator_auth, verify_collector_auth

@pytest.fixture(autouse=True)
def override_auth_for_legacy_tests():
    """Allows existing functional test suites to run while enabling explicit auth testing."""
    app.dependency_overrides[verify_operator_auth] = lambda: "test-operator"
    app.dependency_overrides[verify_collector_auth] = lambda: "test-collector"
    yield
    app.dependency_overrides.pop(verify_operator_auth, None)
    app.dependency_overrides.pop(verify_collector_auth, None)
