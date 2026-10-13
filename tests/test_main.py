"""Comprehensive API tests for InspectAgent FastAPI service."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import Settings, get_settings


@pytest.fixture
def client() -> TestClient:
    """Fixture to provide a clean TestClient instance."""
    return TestClient(app)


def test_health_check(client: TestClient):
    """Verify GET /health returns 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_and_openapi_available(client: TestClient):
    """Verify /docs and /openapi.json properly include the required endpoints."""
    # Check OpenAPI schema contains our endpoints
    openapi_resp = client.get("/openapi.json")
    assert openapi_resp.status_code == 200
    schema = openapi_resp.json()
    assert "/health" in schema["paths"]
    assert "/test-image" in schema["paths"]

    # Verify response schema for /test-image specifies 200, 404, and 422 responses
    test_image_paths = schema["paths"]["/test-image"]["get"]["responses"]
    assert "200" in test_image_paths
    assert "404" in test_image_paths
    assert "422" in test_image_paths

    # Check /docs endpoint is accessible
    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200


def test_test_image_success_with_actual_dataset(client: TestClient):
    """Verify GET /test-image loads real bottle image and returns correct metadata."""
    settings = get_settings()
    actual_img_path = settings.absolute_dataset_path / "train" / "good" / "000.png"

    if not actual_img_path.exists():
        pytest.skip(f"Actual dataset image not found at {actual_img_path}, skipping real image test.")

    response = client.get("/test-image")
    assert response.status_code == 200
    data = response.json()

    assert data["filename"] == "000.png"
    assert data["width"] == 900
    assert data["height"] == 900
    assert data["channels"] == 3


def test_test_image_not_found_404(client: TestClient, tmp_path: Path):
    """Verify GET /test-image returns 404 when no image exists, without modifying original dataset."""
    # Create empty mock dataset directory structure
    mock_dataset = tmp_path / "dataset"
    (mock_dataset / "train" / "good").mkdir(parents=True)

    # Mock settings pointing to empty mock dataset
    def mock_get_settings():
        s = Settings()
        s.DATASET_PATH = str(mock_dataset)
        return s

    app.dependency_overrides[get_settings] = mock_get_settings
    try:
        response = client.get("/test-image")
        assert response.status_code == 404
        assert "No PNG image found" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_test_image_corrupted_422(client: TestClient, tmp_path: Path):
    """Verify GET /test-image returns 422 when image is corrupted, without modifying original dataset."""
    # Create mock dataset directory with a corrupted (invalid) image file
    mock_dataset = tmp_path / "dataset"
    target_dir = mock_dataset / "train" / "good"
    target_dir.mkdir(parents=True)

    corrupted_file = target_dir / "000_corrupted.png"
    corrupted_file.write_bytes(b"This is corrupted header not a valid PNG binary data.")

    # Mock settings pointing to corrupted image dataset
    def mock_get_settings():
        s = Settings()
        s.DATASET_PATH = str(mock_dataset)
        return s

    app.dependency_overrides[get_settings] = mock_get_settings
    try:
        response = client.get("/test-image")
        assert response.status_code == 422
        assert "Failed to decode image file" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
