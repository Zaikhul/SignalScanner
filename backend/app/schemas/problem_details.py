from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProblemDetails(BaseModel):
    """RFC 9457 Problem Details for HTTP APIs."""
    type: str = Field(default="about:blank", description="URI reference that identifies the problem type")
    title: str = Field(..., description="Short, human-readable summary of the problem")
    status: int = Field(..., description="HTTP status code")
    detail: str = Field(..., description="Human-readable explanation specific to this occurrence")
    instance: Optional[str] = Field(None, description="URI reference identifying the specific occurrence")
    code: str = Field(..., description="Machine-readable stable application error code")
    request_id: Optional[str] = Field(None, description="Correlation / trace request identifier")
    invalid_params: Optional[List[Dict[str, Any]]] = Field(None, description="List of invalid parameter details")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of the error")
