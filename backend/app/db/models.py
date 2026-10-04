import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CollectorModel(Base):
    __tablename__ = "collectors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), default="windows")
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    status: Mapped[str] = mapped_column(String(32), default="ready")
    public_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    capabilities: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    adapters: Mapped[List["AdapterModel"]] = relationship(
        "AdapterModel", back_populates="collector", cascade="all, delete-orphan"
    )
    sessions: Mapped[List["ScanSessionModel"]] = relationship(
        "ScanSessionModel", back_populates="collector"
    )


class AdapterModel(Base):
    __tablename__ = "adapters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    collector_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("collectors.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # wifi, bluetooth, radio
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    capabilities: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    driver_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    collector: Mapped["CollectorModel"] = relationship(
        "CollectorModel", back_populates="adapters"
    )


class ScanSessionModel(Base):
    __tablename__ = "scan_sessions"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"ses_{uuid.uuid4().hex[:12]}"
    )
    name: Mapped[str] = mapped_column(String(128), default="Live Scan Session")
    mode: Mapped[str] = mapped_column(String(32), nullable=False)  # wifi, bluetooth, radio
    collector_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("collectors.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), default="collector", nullable=False)  # collector, simulator
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft, active, paused, completed, stopped, failed
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    collector: Mapped["CollectorModel"] = relationship(
        "CollectorModel", back_populates="sessions"
    )
    targets: Mapped[List["TargetModel"]] = relationship(
        "TargetModel", back_populates="session", cascade="all, delete-orphan"
    )
    measurements: Mapped[List["MeasurementModel"]] = relationship(
        "MeasurementModel", back_populates="session", cascade="all, delete-orphan"
    )
    markers: Mapped[List["SessionMarkerModel"]] = relationship(
        "SessionMarkerModel", back_populates="session", cascade="all, delete-orphan"
    )
    manifests: Mapped[List["SessionManifestModel"]] = relationship(
        "SessionManifestModel", back_populates="session", cascade="all, delete-orphan"
    )
    channel_metrics: Mapped[List["ChannelMetricModel"]] = relationship(
        "ChannelMetricModel", back_populates="session", cascade="all, delete-orphan"
    )
    associations: Mapped[List["WifiAssociationModel"]] = relationship(
        "WifiAssociationModel", back_populates="session", cascade="all, delete-orphan"
    )
    lan_hosts: Mapped[List["LanHostModel"]] = relationship(
        "LanHostModel", back_populates="session", cascade="all, delete-orphan"
    )
    channel_health_snapshots: Mapped[List["ChannelHealthSnapshotModel"]] = relationship(
        "ChannelHealthSnapshotModel", back_populates="session", cascade="all, delete-orphan"
    )
    channel_recommendations: Mapped[List["ChannelRecommendationModel"]] = relationship(
        "ChannelRecommendationModel", back_populates="session", cascade="all, delete-orphan"
    )
    channel_validations: Mapped[List["ChannelValidationRunModel"]] = relationship(
        "ChannelValidationRunModel", back_populates="session", cascade="all, delete-orphan"
    )


class TargetModel(Base):
    __tablename__ = "targets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)  # HMAC hash
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    band: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["ScanSessionModel"] = relationship(
        "ScanSessionModel", back_populates="targets"
    )
    measurements: Mapped[List["MeasurementModel"]] = relationship(
        "MeasurementModel", back_populates="target_rel"
    )


class MeasurementModel(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_db_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("targets.id", ondelete="CASCADE"), nullable=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    signal_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="dBm")
    noise_floor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    snr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frequency_hz: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    channel: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    band: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    
    # Enhanced FQ-01 & OBS-01 Measurement Quality Columns
    scan_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    freshness: Mapped[str] = mapped_column(String(32), default="fresh")
    source_method: Mapped[str] = mapped_column(String(64), default="unknown")
    rssi_processing: Mapped[str] = mapped_column(String(32), default="unknown")
    
    quality_flags: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    raw_extra: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    session: Mapped["ScanSessionModel"] = relationship(
        "ScanSessionModel", back_populates="measurements"
    )
    target_rel: Mapped[Optional["TargetModel"]] = relationship(
        "TargetModel", back_populates="measurements"
    )


class SessionMarkerModel(Base):
    __tablename__ = "session_markers"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"mrk_{uuid.uuid4().hex[:8]}"
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["ScanSessionModel"] = relationship(
        "ScanSessionModel", back_populates="markers"
    )


class SessionManifestModel(Base):
    """Immutable session evidence and provenance manifest table (PROV-01)."""
    __tablename__ = "session_manifests"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"mnf_{uuid.uuid4().hex[:12]}"
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    manifest_version: Mapped[str] = mapped_column(String(16), default="1.0")
    manifest_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["ScanSessionModel"] = relationship(
        "ScanSessionModel", back_populates="manifests"
    )


class ChannelMetricModel(Base):
    """Typed channel metrics table with unambiguous evidence taxonomy (CHAN-01)."""
    __tablename__ = "channel_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[int] = mapped_column(Integer, nullable=False)
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)  # bss_overlap_index, advertised_channel_load, measured_airtime_utilization, energy_occupancy
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), default="ratio")
    evidence: Mapped[str] = mapped_column(String(32), default="inferred")  # measured, advertised, inferred, unknown
    method: Mapped[str] = mapped_column(String(64), default="weighted_bssid_overlap_v2")
    window_ms: Mapped[int] = mapped_column(Integer, default=10000)
    uncertainty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["ScanSessionModel"] = relationship(
        "ScanSessionModel", back_populates="channel_metrics"
    )


class ExportAuditLogModel(Base):
    """Auditable export history with policy verification & checksums (PRIV-01 & EVID-01)."""
    __tablename__ = "export_audit_logs"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"aud_{uuid.uuid4().hex[:8]}"
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    format: Mapped[str] = mapped_column(String(64), default="json")
    scope: Mapped[str] = mapped_column(String(64), default="full_session")
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    exported_by: Mapped[str] = mapped_column(String(64), default="anonymous_user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ExportJobModel(Base):
    __tablename__ = "export_jobs"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"exp_{uuid.uuid4().hex[:8]}"
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False
    )
    format: Mapped[str] = mapped_column(String(16), default="json")
    status: Mapped[str] = mapped_column(String(32), default="completed")
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    file_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class WifiAssociationModel(Base):
    """WiFi Association session entity (PRD v1.1 - Section 16.1). Zero secret storage."""
    __tablename__ = "wifi_associations"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"asc_{uuid.uuid4().hex[:12]}"
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False
    )
    collector_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("collectors.id"), nullable=False
    )
    adapter_id: Mapped[str] = mapped_column(String(64), default="win_wlan_01")
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ssid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    bssid_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    security_type: Mapped[str] = mapped_column(String(32), default="wpa2_personal")
    state: Mapped[str] = mapped_column(String(32), default="idle")
    associated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ipv4: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    ipv6: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    prefix: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    gateway: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    dns: Mapped[List[str]] = mapped_column(JSON, default=list)
    dhcp_server: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    captive_state: Mapped[str] = mapped_column(String(32), default="unknown")
    save_profile_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    forget_profile_on_exit: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["ScanSessionModel"] = relationship(
        "ScanSessionModel", back_populates="associations"
    )
    hosts: Mapped[List["LanHostModel"]] = relationship(
        "LanHostModel", back_populates="association", cascade="all, delete-orphan"
    )
    events: Mapped[List["AssociationEventModel"]] = relationship(
        "AssociationEventModel", back_populates="association", cascade="all, delete-orphan"
    )


class LanHostModel(Base):
    """LAN host discovery entity (PRD v1.1 - Section 16.1)."""
    __tablename__ = "lan_hosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    association_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("wifi_associations.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False
    )
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    ip_version: Mapped[int] = mapped_column(Integer, default=4)
    hostname: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    mac_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    oui_vendor: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    discovery_methods: Mapped[List[str]] = mapped_column(JSON, default=list)
    reachability: Mapped[str] = mapped_column(String(32), default="up")
    rtt_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_self: Mapped[bool] = mapped_column(Boolean, default=False)
    is_gateway: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_flags: Mapped[List[str]] = mapped_column(JSON, default=list)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    association: Mapped["WifiAssociationModel"] = relationship(
        "WifiAssociationModel", back_populates="hosts"
    )
    session: Mapped["ScanSessionModel"] = relationship(
        "ScanSessionModel", back_populates="lan_hosts"
    )


class AssociationEventModel(Base):
    """Audit log of association state transitions (PRD v1.1 - Section 16.1)."""
    __tablename__ = "association_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    association_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("wifi_associations.id", ondelete="CASCADE"), nullable=False
    )
    from_state: Mapped[str] = mapped_column(String(32), nullable=False)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), default="user")
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    association: Mapped["WifiAssociationModel"] = relationship(
        "WifiAssociationModel", back_populates="events"
    )


class ChannelHealthSnapshotModel(Base):
    """Immutable channel health observation window snapshot (PRD v1.2 - Section 17.4)."""
    __tablename__ = "channel_health_snapshots"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"chs_{uuid.uuid4().hex[:12]}"
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False
    )
    band: Mapped[str] = mapped_column(String(32), default="2.4GHz")
    channel_width_mhz: Mapped[int] = mapped_column(Integer, default=20)
    observation_window: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    regulatory_domain: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    channels_data: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    quality_flags: Mapped[List[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["ScanSessionModel"] = relationship(
        "ScanSessionModel", back_populates="channel_health_snapshots"
    )
    recommendations: Mapped[List["ChannelRecommendationModel"]] = relationship(
        "ChannelRecommendationModel", back_populates="snapshot", cascade="all, delete-orphan"
    )


class ChannelRecommendationModel(Base):
    """Immutable channel recommendation decision record (PRD v1.2 - Section 17.5)."""
    __tablename__ = "channel_recommendations"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"chr_{uuid.uuid4().hex[:12]}"
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("channel_health_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    algorithm_version: Mapped[str] = mapped_column(String(32), default="channel-health-1.0.0")
    primary_channel: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    alternatives: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[str] = mapped_column(String(16), default="medium")  # high, medium, low
    confidence_reasons: Mapped[List[str]] = mapped_column(JSON, default=list)
    missing_evidence: Mapped[List[str]] = mapped_column(JSON, default=list)
    supporting_factors: Mapped[List[str]] = mapped_column(JSON, default=list)
    counter_signals: Mapped[List[str]] = mapped_column(JSON, default=list)
    conflict_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["ScanSessionModel"] = relationship(
        "ScanSessionModel", back_populates="channel_recommendations"
    )
    snapshot: Mapped["ChannelHealthSnapshotModel"] = relationship(
        "ChannelHealthSnapshotModel", back_populates="recommendations"
    )
    validations: Mapped[List["ChannelValidationRunModel"]] = relationship(
        "ChannelValidationRunModel", back_populates="baseline_recommendation"
    )


class ChannelValidationRunModel(Base):
    """Before-after channel change observation & validation run (PRD v1.2 - Section 19 & 10.4.7)."""
    __tablename__ = "channel_validation_runs"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"chv_{uuid.uuid4().hex[:12]}"
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False
    )
    baseline_recommendation_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("channel_recommendations.id", ondelete="SET NULL"), nullable=True
    )
    marker_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("session_markers.id", ondelete="SET NULL"), nullable=True
    )
    before_window: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    after_window: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    metric_deltas: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    summary_label: Mapped[str] = mapped_column(
        String(256), default="Perubahan teramati pada observation window"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["ScanSessionModel"] = relationship(
        "ScanSessionModel", back_populates="channel_validations"
    )
    baseline_recommendation: Mapped[Optional["ChannelRecommendationModel"]] = relationship(
        "ChannelRecommendationModel", back_populates="validations"
    )
