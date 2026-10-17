import hashlib
import json
import uuid

from sqlalchemy import select, text

from backend.roi_models import ActiveBinding, Approval, Preset, SCOPE_FIELDS, Version
from backend.roi_schemas import RoiError


class RoiRepository:
    def __init__(self, session):
        self.session = session

    def preset(self, identifier, *, lock=False):
        query = select(Preset).where(Preset.roi_config_id == identifier)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        record = self.session.scalar(query)
        if record is None:
            raise RoiError(404, "ROI_NOT_FOUND")
        return record

    def version(self, identifier, version):
        record = self.session.get(Version, (identifier, version))
        if record is None:
            raise RoiError(404, "ROI_VERSION_NOT_FOUND")
        return record

    def binding(self, scope):
        return self.session.get(ActiveBinding, tuple(scope[field] for field in SCOPE_FIELDS))

    def view(self, preset, version):
        record = self.version(preset.roi_config_id, version)
        approval = self.session.get(Approval, (preset.roi_config_id, version))
        scope = {field: getattr(preset, field) for field in SCOPE_FIELDS}
        binding = self.binding(scope)
        return {
            "roi_config_id": preset.roi_config_id, "version": version, "head_version": preset.head_version,
            **scope, "coordinate_system": "ORIGINAL_IMAGE_PIXELS_TOP_LEFT",
            "roi": {field: getattr(record, field) for field in ("x", "y", "width", "height")},
            "approved_for_auto": approval is not None,
            "active": binding is not None and binding.roi_config_id == preset.roi_config_id and binding.version == version,
            "binding_revision": binding.binding_revision if binding else 0,
            "created_at": record.created_at.isoformat(),
            "approved_at": approval.approved_at.isoformat() if approval else None,
        }

    def create(self, scope, rectangle):
        preset = Preset(roi_config_id=f"ROI-{uuid.uuid4().hex}", head_version=1, **scope)
        self.session.add(preset)
        self.session.flush()
        self.session.add(Version(roi_config_id=preset.roi_config_id, version=1, **rectangle))
        self.session.flush()
        return self.view(preset, 1)

    def add_version(self, identifier, expected, rectangle):
        preset = self.preset(identifier, lock=True)
        if preset.head_version != expected:
            raise RoiError(409, "ROI_VERSION_CONFLICT")
        preset.head_version += 1
        self.session.add(Version(roi_config_id=identifier, version=preset.head_version, **rectangle))
        self.session.flush()
        return self.view(preset, preset.head_version)

    def approve(self, identifier, version):
        preset = self.preset(identifier, lock=True)
        self.version(identifier, version)
        if self.session.get(Approval, (identifier, version)) is None:
            self.session.add(Approval(roi_config_id=identifier, version=version))
            self.session.flush()
        return self.view(preset, version)

    def activate(self, identifier, version, expected):
        preset = self.preset(identifier)
        self.version(identifier, version)
        scope = {field: getattr(preset, field) for field in SCOPE_FIELDS}
        encoded = json.dumps([scope[field] for field in SCOPE_FIELDS], separators=(",", ":")).encode()
        lock_key = int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big", signed=True)
        self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        if self.session.get(Approval, (identifier, version)) is None:
            raise RoiError(409, "ROI_APPROVAL_REQUIRED")
        binding = self.binding(scope)
        if (binding.binding_revision if binding else 0) != expected:
            raise RoiError(409, "ROI_ACTIVE_CONFLICT")
        if binding is None:
            binding = ActiveBinding(**scope, roi_config_id=identifier, version=version, binding_revision=1)
            self.session.add(binding)
        else:
            binding.roi_config_id = identifier
            binding.version = version
            binding.binding_revision += 1
            binding.updated_at = self.session.scalar(text("SELECT CURRENT_TIMESTAMP"))
        self.session.flush()
        return self.view(preset, version)
