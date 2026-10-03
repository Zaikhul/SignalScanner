from app.db.models import MeasurementModel, ScanSessionModel, TargetModel
from app.db.web_scan_models import (
    WebScanFindingModel,
    WebScanJobModel,
    WebScanObservationModel,
    WebScanScopeModel,
)


def test_radio_and_web_scan_domain_isolation():
    # Verify MeasurementModel does not contain web scan columns
    measurement_cols = {c.name for c in MeasurementModel.__table__.columns}
    assert "url" not in measurement_cols
    assert "status_code" not in measurement_cols
    assert "headers" not in measurement_cols
    assert "http_method" not in measurement_cols

    # Verify WebScanJobModel has its own isolated table
    assert WebScanJobModel.__tablename__ == "web_scan_jobs"
    assert WebScanFindingModel.__tablename__ == "web_scan_findings"
    assert WebScanObservationModel.__tablename__ == "web_scan_observations"
    assert WebScanScopeModel.__tablename__ == "web_scan_scopes"

    # Verify WebScanJobModel is separate from ScanSessionModel
    assert ScanSessionModel.__tablename__ == "scan_sessions"
