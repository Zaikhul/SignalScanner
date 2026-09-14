from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field


class ExportRequest(BaseModel):
    format: Literal["json", "csv"] = "json"
    include_raw_samples: bool = True
    include_summary: bool = True
    include_markers: bool = True


class ExportResponse(BaseModel):
    id: str
    session_id: str
    format: Literal["json", "csv"]
    status: Literal["pending", "processing", "completed", "failed"]
    file_size_bytes: Optional[int] = None
    checksum_sha256: Optional[str] = None
    download_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
