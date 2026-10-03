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


@pytest.fixture(autouse=True)
async def ensure_db_init():
    """Initializes tables for test database and ensures isolation across test runs."""
    from app.db.session import init_db, AsyncSessionLocal
    await init_db()
    async with AsyncSessionLocal() as session:
        from app.db.web_scan_models import (
            WebScanFindingModel,
            WebScanObservationModel,
            WebScanEventRecordModel,
            WebScanWsTicketModel,
            WebScanAuditRecordModel,
            WebScanJobModel,
            WebScanScopeModel,
        )
        for model in (
            WebScanFindingModel,
            WebScanObservationModel,
            WebScanEventRecordModel,
            WebScanWsTicketModel,
            WebScanAuditRecordModel,
            WebScanJobModel,
            WebScanScopeModel,
        ):
            await session.execute(model.__table__.delete())
        await session.commit()
    yield


@pytest.fixture(autouse=True)
async def dispose_db_engine():
    """Disposes engine connection pool between async tests to prevent asyncpg loop conflicts."""
    yield
    from app.db.session import engine
    await engine.dispose()

