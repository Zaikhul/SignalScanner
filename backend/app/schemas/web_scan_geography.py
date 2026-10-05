from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class GeoPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None


class GeoEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique, deterministic identifier for this endpoint")
    role: Literal["source", "target"]
    display_name: str
    ip: Optional[str] = None
    address_basis: Literal[
        "configured",
        "dns_candidate",
        "transport_selected",
        "observed_connection",
        "unresolved",
    ]
    executor_id: Optional[str] = None
    location: Optional[GeoPoint] = None
    location_level: Literal["coordinates", "city", "region", "country", "unknown"] = "unknown"
    location_basis: Literal["configured", "ip_lookup_estimate", "unknown"] = "unknown"
    location_status: Literal["located", "unknown", "unsupported", "lookup_failed", "disallowed"] = "unknown"
    status_reason: Optional[str] = None
    provider_info: Optional[str] = None


class GeoRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique deterministic identifier for this relationship")
    source_endpoint_id: str
    target_endpoint_id: str
    direction: Literal["source_to_target"] = "source_to_target"
    relation_basis: Literal["observed_http", "transport_attempt", "configured_target"]
    record_count: int = Field(default=1, ge=1)
    unit: Literal["records"] = "records"
    status_codes: List[int] = Field(default_factory=list)
    methods: List[str] = Field(default_factory=list)
    supporting_observation_ids: List[str] = Field(default_factory=list)
    linked_finding_ids: List[str] = Field(default_factory=list)


class GeoCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observations_total: int = 0
    observations_stored: int = 0
    eligible_records: int = 0
    both_located_count: int = 0
    partial_located_count: int = 0
    unlocated_count: int = 0
    is_subset: bool = False
    storage_ceiling: int = 200


class WebScanGeographyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_id: str
    schema_version: Literal["web_scan.geo.v1"] = "web_scan.geo.v1"
    data_revision: int = 1
    generated_at: datetime
    readiness_status: Literal["ready", "processing", "empty", "no_locations", "partial"]
    target_display: str
    scan_status: str
    coverage: GeoCoverage
    endpoints: List[GeoEndpoint] = Field(default_factory=list)
    relations: List[GeoRelation] = Field(default_factory=list)
    time_info: Dict[str, Any] = Field(default_factory=dict)
    disclaimers: Dict[str, str] = Field(default_factory=dict)
