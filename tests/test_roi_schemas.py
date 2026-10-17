import pytest
from pydantic import ValidationError

from backend.db import RoiSettings, database_engine
from backend.roi_schemas import ActivateVersion, CreatePreset, Rectangle


@pytest.mark.parametrize("field,value", [
    ("x", -1), ("y", -1), ("width", 0), ("height", 0), ("x", True), ("height", False),
    ("width", 1.0), ("x", "1"), ("height", 100001), ("x", 2**100), ("y", None),
    ("width", float("inf")), ("height", float("nan")),
])
def test_rectangle_strict_invalid(field, value):
    values = {"x": 0, "y": 0, "width": 32, "height": 32}
    values[field] = value
    with pytest.raises(ValidationError):
        Rectangle(**values)


def test_rectangle_extra_and_valid():
    assert Rectangle(x=0, y=0, width=32, height=32).width == 32
    with pytest.raises(ValidationError):
        Rectangle(x=0, y=0, width=32, height=32, approved=True)


@pytest.mark.parametrize("value", [True, 0, 1.0, "1"])
def test_strict_version(value):
    with pytest.raises(ValidationError):
        ActivateVersion(version=value, expected_active_revision=0)


def test_no_sqlite_fallback():
    with pytest.raises(ValueError, match="POSTGRESQL_REQUIRED"):
        database_engine("sqlite://")


def test_secrets_hidden():
    settings = RoiSettings(_env_file=None, database_url="postgresql+psycopg://user:private@localhost/db",
                           roi_admin_token="another-private-value")
    assert "another-private-value" not in repr(settings)
    assert "user:private" not in repr(settings)


def test_creation_cannot_claim_approval():
    with pytest.raises(ValidationError):
        CreatePreset(video_id="VID-000001", source_revision="a" * 64,
                     source_width=1920, source_height=480, product_id="PRODUCT-0001",
                     roi={"x": 0, "y": 0, "width": 32, "height": 32}, active=True)
