from __future__ import annotations

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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base


class WebScanScopeModel(Base):
    __tablename__ = "web_scan_scopes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default_tenant")
    authorization_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    assigned_principals: Mapped[List[str]] = mapped_column(JSON, default=list)
    rules: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    budget: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    allow_tls_unverified: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_geolocation: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_load: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_header_variants: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="admin")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    jobs: Mapped[List["WebScanJobModel"]] = relationship("WebScanJobModel", back_populates="scope")

    __table_args__ = (
        Index("ix_web_scan_scopes_tenant_created", "tenant_id", "created_at"),
    )


class WebScanJobModel(Base):
    __tablename__ = "web_scan_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default_tenant")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="operator")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    idempotency_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scope_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("web_scan_scopes.id", ondelete="SET NULL"), nullable=True
    )
    scope_revision: Mapped[int] = mapped_column(Integer, default=1)
    scope_hash: Mapped[str] = mapped_column(String(64), default="inline_scope")
    raw_target: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_target: Mapped[str] = mapped_column(Text, nullable=False)
    target_display: Mapped[str] = mapped_column(String(256), nullable=False)
    requested_configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    effective_configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    status_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot_sequence: Mapped[int] = mapped_column(Integer, default=0)
    summary_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    scope: Mapped[Optional["WebScanScopeModel"]] = relationship("WebScanScopeModel", back_populates="jobs")
    observations: Mapped[List["WebScanObservationModel"]] = relationship(
        "WebScanObservationModel", back_populates="job", cascade="all, delete-orphan"
    )
    findings: Mapped[List["WebScanFindingModel"]] = relationship(
        "WebScanFindingModel", back_populates="job", cascade="all, delete-orphan"
    )
    events: Mapped[List["WebScanEventRecordModel"]] = relationship(
        "WebScanEventRecordModel", back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_web_scan_jobs_tenant_created", "tenant_id", "created_at"),
        Index("ix_web_scan_jobs_status_queued", "status", "queued_at"),
        UniqueConstraint("tenant_id", "created_by", "idempotency_key", name="uq_web_scan_jobs_idempotency"),
    )


class WebScanObservationModel(Base):
    __tablename__ = "web_scan_observations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("web_scan_jobs.id", ondelete="CASCADE"), nullable=False
    )
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    job: Mapped["WebScanJobModel"] = relationship("WebScanJobModel", back_populates="observations")

    __table_args__ = (
        Index("ix_web_scan_obs_scan_kind", "scan_id", "kind"),
        Index("ix_web_scan_obs_scan_time", "scan_id", "observed_at"),
    )


class WebScanFindingModel(Base):
    __tablename__ = "web_scan_findings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("web_scan_jobs.id", ondelete="CASCADE"), nullable=False
    )
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    check_id: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    source_category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    source_severity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    severity_reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    remediation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    assessment_version: Mapped[str] = mapped_column(String(32), default="web_scan.v1")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    job: Mapped["WebScanJobModel"] = relationship("WebScanJobModel", back_populates="findings")

    __table_args__ = (
        UniqueConstraint("scan_id", "fingerprint", name="uq_web_scan_findings_fingerprint"),
        Index("ix_web_scan_findings_scan_sev", "scan_id", "severity"),
        Index("ix_web_scan_findings_scan_time", "scan_id", "first_seen_at"),
    )


class WebScanEventRecordModel(Base):
    __tablename__ = "web_scan_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("web_scan_jobs.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    job: Mapped["WebScanJobModel"] = relationship("WebScanJobModel", back_populates="events")

    __table_args__ = (
        UniqueConstraint("scan_id", "sequence", name="uq_web_scan_events_scan_seq"),
        Index("ix_web_scan_events_scan_seq", "scan_id", "sequence"),
    )


class WebScanAuditRecordModel(Base):
    __tablename__ = "web_scan_audit"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default_tenant")
    principal_id: Mapped[str] = mapped_column(String(64), nullable=False, default="operator")
    scan_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_web_scan_audit_tenant_time", "tenant_id", "created_at"),
        Index("ix_web_scan_audit_scan_action", "scan_id", "action"),
    )


class WebScanWsTicketModel(Base):
    __tablename__ = "web_scan_ws_tickets"

    ticket_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    scan_id: Mapped[str] = mapped_column(String(64), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_web_scan_ws_tickets_scan_exp", "scan_id", "expires_at"),
    )
