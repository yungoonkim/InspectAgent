from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


SCOPE_FIELDS = ("video_id", "source_revision", "product_id", "source_width", "source_height")


class Base(DeclarativeBase):
    pass


class Preset(Base):
    __tablename__ = "roi_presets"
    roi_config_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(String(10))
    source_revision: Mapped[str] = mapped_column(String(64))
    product_id: Mapped[str] = mapped_column(String(64))
    source_width: Mapped[int] = mapped_column(Integer)
    source_height: Mapped[int] = mapped_column(Integer)
    head_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("roi_config_id", *SCOPE_FIELDS, name="uq_roi_preset_scope"),
        CheckConstraint("source_width > 0 AND source_height > 0 AND head_version > 0", name="ck_roi_source"),
    )


class Version(Base):
    __tablename__ = "roi_preset_versions"
    roi_config_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["roi_config_id"], ["roi_presets.roi_config_id"], name="fk_roi_version_preset"),
        CheckConstraint("version > 0 AND x >= 0 AND y >= 0 AND width > 0 AND height > 0", name="ck_roi_rectangle"),
    )


class Approval(Base):
    __tablename__ = "roi_approvals"
    roi_config_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["roi_config_id", "version"],
                             ["roi_preset_versions.roi_config_id", "roi_preset_versions.version"], name="fk_roi_approval_version"),
    )


class ActiveBinding(Base):
    __tablename__ = "roi_active_bindings"
    video_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    source_revision: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_width: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_height: Mapped[int] = mapped_column(Integer, primary_key=True)
    roi_config_id: Mapped[str] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer)
    binding_revision: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["roi_config_id", "version"], ["roi_approvals.roi_config_id", "roi_approvals.version"],
                             name="fk_roi_active_approved"),
        ForeignKeyConstraint(["roi_config_id", *SCOPE_FIELDS],
                             ["roi_presets.roi_config_id", *(f"roi_presets.{field}" for field in SCOPE_FIELDS)],
                             name="fk_roi_active_scope"),
        CheckConstraint("binding_revision > 0", name="ck_roi_binding_revision"),
    )
