from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    memberships: Mapped[list[BusinessMembership]] = relationship(back_populates="user")
    sessions: Mapped[list[AuthSession]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    niche: Mapped[str] = mapped_column(String(160), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    service_offerings: Mapped[str] = mapped_column(Text, nullable=False)
    target_audience: Mapped[str] = mapped_column(Text, nullable=False)
    brand_tone: Mapped[str] = mapped_column(String(200), nullable=False)
    posting_goals: Mapped[str] = mapped_column(Text, nullable=False)
    brand_colors: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    memberships: Mapped[list[BusinessMembership]] = relationship(back_populates="business", cascade="all, delete-orphan")
    assets: Mapped[list[ContentAsset]] = relationship(back_populates="business", cascade="all, delete-orphan")
    owner: Mapped[User] = relationship(foreign_keys=[owner_user_id])


class BusinessMembership(Base):
    __tablename__ = "business_memberships"
    __table_args__ = (UniqueConstraint("user_id", "business_id", name="uq_membership_user_business"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(40), default="owner", nullable=False)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="memberships")
    business: Mapped[Business] = relationship(back_populates="memberships")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user_expiry", "user_id", "expires_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    device_label: Mapped[str | None] = mapped_column(String(160))

    user: Mapped[User] = relationship(back_populates="sessions")


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("business_id", "platform", "external_account_id", name="uq_social_account_business_platform_external"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(200), nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    granted_scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    connection_state: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    token_ciphertext: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ContentAsset(Base):
    __tablename__ = "content_assets"
    __table_args__ = (
        Index("ix_content_assets_business_created", "business_id", "created_at"),
        Index("ix_content_assets_business_status", "business_id", "status"),
        CheckConstraint("byte_size IS NULL OR byte_size >= 0", name="ck_content_assets_nonnegative_size"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str | None] = mapped_column(String(240))
    source_text: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    object_key: Mapped[str | None] = mapped_column(String(500), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="ready", nullable=False)
    processing_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    business: Mapped[Business] = relationship(back_populates="assets")
    derivatives: Mapped[list[AssetDerivative]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    analyses: Mapped[list[AssetAnalysis]] = relationship(back_populates="asset", cascade="all, delete-orphan")


class AssetDerivative(Base):
    __tablename__ = "asset_derivatives"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    derivative_type: Mapped[str] = mapped_column(String(40), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="ready", nullable=False)

    asset: Mapped[ContentAsset] = relationship(back_populates="derivatives")


class AssetAnalysis(Base):
    __tablename__ = "asset_analyses"
    __table_args__ = (Index("ix_asset_analyses_asset_created", "asset_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False)
    processor_name: Mapped[str] = mapped_column(String(160), nullable=False)
    processor_version: Mapped[str | None] = mapped_column(String(120))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    quality_scores: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    asset: Mapped[ContentAsset] = relationship(back_populates="analyses")


class GeneratedDraft(Base):
    __tablename__ = "generated_drafts"
    __table_args__ = (Index("ix_generated_drafts_business_created", "business_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    call_to_action: Mapped[str] = mapped_column(Text, nullable=False)
    overlays: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    production_specs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class GeneratedContent(Base):
    """Generated copy and media briefs saved in a business's content library."""
    __tablename__ = "generated_contents"
    __table_args__ = (
        Index("ix_generated_contents_business_created", "business_id", "created_at"),
        CheckConstraint("content_type IN ('text', 'image', 'video')", name="ck_generated_contents_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_analysis_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class DraftAsset(Base):
    __tablename__ = "draft_assets"
    __table_args__ = (UniqueConstraint("draft_id", "asset_id", name="uq_draft_asset"),)

    draft_id: Mapped[UUID] = mapped_column(ForeignKey("generated_drafts.id", ondelete="CASCADE"), primary_key=True)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("content_assets.id", ondelete="CASCADE"), primary_key=True)


class ContentRating(Base):
    __tablename__ = "content_ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "draft_id", name="uq_rating_user_draft"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_content_rating_range"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    draft_id: Mapped[UUID] = mapped_column(ForeignKey("generated_drafts.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PublishedPost(Base):
    __tablename__ = "published_posts"
    __table_args__ = (UniqueConstraint("platform", "external_post_id", name="uq_published_platform_external"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    draft_id: Mapped[UUID | None] = mapped_column(ForeignKey("generated_drafts.id", ondelete="SET NULL"))
    social_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("social_accounts.id", ondelete="SET NULL"))
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    external_post_id: Mapped[str] = mapped_column(String(240), nullable=False)
    publish_state: Mapped[str] = mapped_column(String(40), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PostPerformanceSnapshot(Base):
    __tablename__ = "post_performance_snapshots"
    __table_args__ = (Index("ix_performance_post_captured", "published_post_id", "captured_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    published_post_id: Mapped[UUID] = mapped_column(ForeignKey("published_posts.id", ondelete="CASCADE"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    reach: Mapped[int | None] = mapped_column(Integer)
    impressions: Mapped[int | None] = mapped_column(Integer)
    views: Mapped[int | None] = mapped_column(Integer)
    likes: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    saves: Mapped[int | None] = mapped_column(Integer)
    clicks: Mapped[int | None] = mapped_column(Integer)
    conversions: Mapped[int | None] = mapped_column(Integer)
    followers: Mapped[int | None] = mapped_column(Integer)
    source_version: Mapped[str | None] = mapped_column(String(120))


class ContentChunk(Base):
    __tablename__ = "content_chunks"
    __table_args__ = (Index("ix_content_chunks_business_source", "business_id", "source_type", "source_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("content_assets.id", ondelete="CASCADE"))
    draft_id: Mapped[UUID | None] = mapped_column(ForeignKey("generated_drafts.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    embedding_model: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (Index("ix_processing_jobs_state_retry", "state", "retry_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("content_assets.id", ondelete="CASCADE"))
    job_type: Mapped[str] = mapped_column(String(60), nullable=False)
    state: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentGenerationResult(Base):
    """Connect a durable generation job to the saved content items it produced."""
    __tablename__ = "content_generation_results"

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    generated_content_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID | None] = mapped_column(ForeignKey("businesses.id", ondelete="SET NULL"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_type: Mapped[str | None] = mapped_column(String(80))
    subject_id: Mapped[str | None] = mapped_column(String(80))
    request_id: Mapped[str | None] = mapped_column(String(120), index=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
