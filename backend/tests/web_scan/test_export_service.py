import json
import pytest
from app.db.session import AsyncSessionLocal
from app.schemas.web_scan import CreateScanRequest, ScanConfiguration
from app.services.web_scan_export_service import WebScanExportService
from app.services.web_scan_service import WebScanService


@pytest.mark.asyncio
async def test_export_formats_and_checksums():
    async with AsyncSessionLocal() as db:
        req = CreateScanRequest(
            target="http://export-test.com",
            authorization_acknowledged=True,
            configuration=ScanConfiguration(allow_private=True),
        )
        job = await WebScanService.create_scan_job(
            db=db,
            tenant_id="tenant_export",
            principal_id="principal_export",
            req=req,
        )

        # 1. Native JSON export
        content_json, ctype_json, fname_json, checksum_json = await WebScanExportService.export_scan(
            db=db,
            tenant_id="tenant_export",
            principal_id="principal_export",
            scan_id=job.id,
            export_format="json",
        )
        assert ctype_json == "application/json"
        assert len(checksum_json) == 64
        parsed = json.loads(content_json)
        assert parsed["schema_version"] == "web_scan.v1"
        assert parsed["job"]["id"] == job.id

        # 2. Ghost v2 compat JSON export
        content_v2, ctype_v2, fname_v2, checksum_v2 = await WebScanExportService.export_scan(
            db=db,
            tenant_id="tenant_export",
            principal_id="principal_export",
            scan_id=job.id,
            export_format="v2_json",
        )
        assert ctype_v2 == "application/json"
        parsed_v2 = json.loads(content_v2)
        assert "risk_score" in parsed_v2
        assert "risk_level" in parsed_v2
        assert "stats" in parsed_v2

        # 3. TXT export
        content_txt, ctype_txt, fname_txt, checksum_txt = await WebScanExportService.export_scan(
            db=db,
            tenant_id="tenant_export",
            principal_id="principal_export",
            scan_id=job.id,
            export_format="txt",
        )
        assert ctype_txt == "text/plain"
        assert "SIGNAL SCANNER - WEB SECURITY AUDIT REPORT" in content_txt

        # 4. Safe SQLite SQL data export
        content_sql, ctype_sql, fname_sql, checksum_sql = await WebScanExportService.export_scan(
            db=db,
            tenant_id="tenant_export",
            principal_id="principal_export",
            scan_id=job.id,
            export_format="sql",
        )
        assert ctype_sql == "application/sql"
        # Must strictly NOT contain DROP TABLE
        assert "DROP TABLE" not in content_sql.upper()
        assert "CREATE TABLE" not in content_sql.upper()
