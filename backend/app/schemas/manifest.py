from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ClockQuality(BaseModel):
    offset_ms: float = Field(default=0.0, description="Estimated clock offset against reference in ms")
    uncertainty_ms: float = Field(default=0.0, description="Clock uncertainty in ms")
    source: str = Field(default="system_monotonic", description="Clock synchronization source (e.g. system_monotonic, ntp, ptp)")


class SequenceSummary(BaseModel):
    first_sequence: int = 0
    last_sequence: int = 0
    total_received: int = 0
    missing_ranges: List[List[int]] = Field(default_factory=list)


class SessionProvenanceManifest(BaseModel):
    """Immutable session evidence & provenance manifest (PROV-01)."""
    manifest_version: str = Field(default="1.0", description="Schema version of this manifest")
    session_id: str = Field(..., description="Unique session identifier")
    collector_id: str = Field(..., description="Collector device identifier")
    collector_version: str = Field(default="1.0.0", description="Collector daemon version")
    os: Dict[str, Any] = Field(default_factory=dict, description="Operating system details")
    adapter: Dict[str, Any] = Field(default_factory=dict, description="Physical/virtual radio adapter details")
    scan_config: Dict[str, Any] = Field(default_factory=dict, description="Scan configuration used during session")
    processing_version: str = Field(default="signal-pipeline@1.0", description="DSP and feature extraction version")
    processing_config_hash: str = Field(default="", description="SHA256 of processing configuration parameters")
    calibration_profile_id: Optional[str] = Field(None, description="Calibration profile ID if applied")
    clock: ClockQuality = Field(default_factory=ClockQuality, description="Clock synchronization and uncertainty")
    privacy_policy_id: str = Field(default="privacy-default-v1", description="Active privacy policy and HMAC salt version")
    schema_version: str = Field(default="measurement@2.0", description="Data model schema version")
    sequence_summary: SequenceSummary = Field(default_factory=SequenceSummary, description="Sequence continuity summary")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    manifest_checksum: str = Field(default="", description="SHA256 checksum of the canonical manifest content")

    def compute_checksum(self) -> str:
        """Computes deterministic SHA256 checksum of manifest fields (excluding manifest_checksum itself)."""
        data = self.model_dump(exclude={"manifest_checksum"})
        # Format datetime to isoformat
        if "created_at" in data and isinstance(data["created_at"], datetime):
            data["created_at"] = data["created_at"].isoformat()
        canonical_json = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
