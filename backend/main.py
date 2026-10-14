"""InspectAgent FastAPI Entry Point.

This module provides health check, image loading, brightness analysis,
and fault injection comparison endpoints for the MVTec AD Bottle inspection AI Agent service.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional
import cv2
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from backend.config import Settings, get_settings
from backend.tools.image_loader import find_first_png, load_image_metadata
from backend.vision import (
    analyze_brightness,
    compute_baseline_statistics,
    inject_brightness_fault,
    save_modified_image,
    evaluate_image_quality,
)
from backend.inspection import (
    execute_inspection,
    execute_inspection_workflow,
    get_image_registry,
)
from backend.storage import StorageError, get_inspection_storage
from backend.ml.patchcore_inferencer import get_patchcore_inferencer

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifespan context manager.

    Pre-loads PatchCore model into memory on server startup when enabled,
    avoiding per-request model loading overhead.
    """
    current_settings = get_settings()
    if getattr(current_settings, "ENABLE_PATCHCORE", True):
        try:
            get_patchcore_inferencer()
        except Exception:
            pass  # Warning/error logged internally
    yield


app = FastAPI(
    title="InspectAgent API",
    description="MVTec AD Bottle dataset-based industrial vision inspection anomaly diagnosis AI Agent service",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS middleware for development and deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Pydantic Response Models
# ==============================================================================

class HealthResponse(BaseModel):
    """Health status response model."""
    status: str = Field(default="ok", examples=["ok"])


class ImageMetadataResponse(BaseModel):
    """Loaded image metadata response model."""
    filename: str = Field(description="Name of the loaded image file", examples=["000.png"])
    width: int = Field(description="Width of the image in pixels", examples=[900])
    height: int = Field(description="Height of the image in pixels", examples=[900])
    channels: int = Field(description="Number of color channels", examples=[3])


class BrightnessMetrics(BaseModel):
    """Image brightness statistical metrics."""
    mean: float = Field(description="Grayscale average brightness", examples=[136.34])
    std: float = Field(description="Grayscale standard deviation", examples=[58.42])
    min: float = Field(description="Minimum pixel intensity (0-255)", examples=[0.0])
    max: float = Field(description="Maximum pixel intensity (0-255)", examples=[255.0])


class ProductInspectionStatus(BaseModel):
    """Decoupled product defect/anomaly inspection status."""
    status: str = Field(default="UNINSPECTED", description="Product inspection status (independent from image quality)")
    message: str = Field(
        default="Product defect/contamination inspection is separate from image quality assessment.",
        description="Clarification that image quality warning is not a product defect verdict",
    )


class QualityEvaluationResponse(BaseModel):
    """Image quality evaluation model decoupled from product defect inspection."""
    quality_status: str = Field(
        description="Quality status: NORMAL | WARNING_LOW_BRIGHTNESS | WARNING_HIGH_BRIGHTNESS",
        examples=["NORMAL"],
    )
    warning_triggered: bool = Field(description="Whether environmental brightness threshold warning was triggered")
    description: str = Field(description="Detailed evaluation description")
    applied_thresholds: Dict[str, float] = Field(description="Threshold values applied during evaluation")
    product_defect_inspection: ProductInspectionStatus = Field(description="Decoupled product anomaly status")


class ImageAnalysisResponse(BaseModel):
    """Single image brightness analysis and quality evaluation response."""
    filename: str
    metrics: BrightnessMetrics
    evaluation: QualityEvaluationResponse


class ComparisonItem(BaseModel):
    """Summary item for brightness comparison."""
    filename: str
    saved_path: Optional[str] = None
    factor: Optional[float] = None
    metrics: BrightnessMetrics
    quality_status: str
    warning_triggered: bool
    description: str


class FaultComparisonResponse(BaseModel):
    """Response comparing original sample against fault-injected sample."""
    original: ComparisonItem
    fault_injected: ComparisonItem
    comparison: Dict[str, Any]
    applied_thresholds: Dict[str, float]
    product_defect_inspection: ProductInspectionStatus


class InspectionCreateRequest(BaseModel):
    """Request payload for starting a vision inspection."""
    product_id: str = Field(
        ...,
        description="Product identifier (e.g., ABCD1541)",
        examples=["ABCD1541"],
    )
    image_id: str = Field(
        ...,
        description="Server-managed neutral image identifier (e.g., IMG-BOTTLE-0001)",
        examples=["IMG-BOTTLE-0001"],
    )


class InspectionResponse(BaseModel):
    """Inspection execution result model."""
    inspection_id: str = Field(description="Unique collision-free inspection ID", examples=["INSP-000001"])
    product_id: str = Field(description="Product identifier", examples=["ABCD1541"])
    image_id: str = Field(description="Server-managed image identifier", examples=["IMG-BOTTLE-0001"])
    status: str = Field(default="COMPLETED", description="Inspection execution status", examples=["COMPLETED"])
    result: str = Field(default="UNKNOWN", description="Inspection verdict (OK/NG/UNKNOWN)", examples=["UNKNOWN"])
    timestamp: str = Field(description="ISO 8601 formatted timestamp with timezone (UTC or +09:00)")
    image_quality_status: str = Field(
        default="NORMAL",
        description="Environmental image acquisition quality status: NORMAL | WARNING_LOW_BRIGHTNESS | WARNING_HIGH_BRIGHTNESS",
        examples=["NORMAL"],
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Vision inspection metrics (brightness, standard deviation, dimensions)",
    )
    image_metadata: ImageMetadataResponse
    anomaly_score: Optional[float] = Field(
        default=None,
        description="PatchCore anomaly distance score (None if model disabled or uninspected)",
        examples=[30.506],
    )
    inference_time_ms: Optional[float] = Field(
        default=None,
        description="PatchCore inference latency in milliseconds",
        examples=[45.2],
    )
    model_version: Optional[str] = Field(
        default=None,
        description="Anomaly detection model version or identifier",
        examples=["PatchCore"],
    )
    decision_threshold: Optional[float] = Field(
        default=None,
        description="Applied anomaly score threshold (None = uncalibrated)",
        examples=[None],
    )
    defect_detection_status: Optional[str] = Field(
        default=None,
        description="ML defect detection lifecycle status: COMPLETED | FAILED | SKIPPED | UNINSPECTED",
        examples=["COMPLETED"],
    )
    final_result: Optional[str] = Field(
        default=None,
        description="Authoritative final verdict: OK | NG | REINSPECT | ERROR",
        examples=["OK"],
    )
    final_reason_code: Optional[str] = Field(
        default=None,
        description="Reason code for authoritative final verdict",
        examples=["ALL_CHECKS_PASSED"],
    )



# ==============================================================================
# Endpoints
# ==============================================================================

@app.get("/", summary="Root status endpoint")
def read_root() -> Dict[str, Any]:
    """Return fundamental service details and runtime environment."""
    dataset_exists = settings.absolute_dataset_path.exists()
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "gemini_model": settings.GEMINI_MODEL,
        "status": "ready",
        "dataset_ready": dataset_exists,
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
    description="Returns simple status ok for service health monitoring.",
)
def health_check() -> HealthResponse:
    """Return service health status."""
    return HealthResponse(status="ok")


@app.get(
    "/test-image",
    response_model=ImageMetadataResponse,
    summary="Load a bottle dataset sample image",
    description=(
        "Locates the first PNG image from the dataset's train/good directory, "
        "loads it using OpenCV, and returns file metadata including dimensions and channels. "
        "Does not accept arbitrary external paths to prevent path traversal attacks."
    ),
    responses={
        404: {"description": "Target image not found in dataset directory"},
        422: {"description": "Target image file corrupted or unreadable by OpenCV"},
    },
)
def get_test_image(current_settings: Settings = Depends(get_settings)) -> ImageMetadataResponse:
    """Load a sample bottle image from train/good and return its dimensions."""
    target_dir = current_settings.absolute_dataset_path / "train" / "good"

    image_path = find_first_png(target_dir)
    if image_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"No PNG image found in dataset directory: {target_dir}",
        )

    try:
        metadata = load_image_metadata(image_path)
        return ImageMetadataResponse(**metadata)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))


@app.get(
    "/baseline/brightness",
    summary="Compute or fetch normal training dataset brightness baseline statistics",
    description="Calculates distribution statistics across all normal training bottle images.",
)
def get_baseline_brightness(current_settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    """Return baseline distribution statistics calculated from train/good images."""
    target_dir = current_settings.absolute_dataset_path / "train" / "good"
    return compute_baseline_statistics(target_dir)


@app.get(
    "/analyze-brightness",
    response_model=ImageAnalysisResponse,
    summary="Analyze brightness of a normal dataset sample image",
    description=(
        "Loads a sample bottle image, calculates mean, std, min, and max grayscale brightness, "
        "and evaluates image quality against configured thresholds."
    ),
    responses={
        404: {"description": "Target image not found in dataset directory"},
        422: {"description": "Target image file corrupted or unreadable by OpenCV"},
    },
)
def get_analyze_brightness(current_settings: Settings = Depends(get_settings)) -> ImageAnalysisResponse:
    """Analyze sample image brightness and evaluate quality status."""
    target_dir = current_settings.absolute_dataset_path / "train" / "good"
    image_path = find_first_png(target_dir)
    if image_path is None:
        raise HTTPException(status_code=404, detail=f"No PNG image found in {target_dir}")

    img = cv2.imread(str(image_path.resolve()))
    if img is None:
        raise HTTPException(status_code=422, detail=f"Failed to read image file: {image_path.name}")

    metrics = analyze_brightness(img)
    evaluation = evaluate_image_quality(
        metrics=metrics,
        low_threshold=current_settings.BRIGHTNESS_LOW_THRESHOLD,
        high_threshold=current_settings.BRIGHTNESS_HIGH_THRESHOLD,
    )

    return ImageAnalysisResponse(
        filename=image_path.name,
        metrics=BrightnessMetrics(**metrics),
        evaluation=QualityEvaluationResponse(**evaluation),
    )


@app.get(
    "/test-image/compare-fault",
    response_model=FaultComparisonResponse,
    summary="Inject 0.6x brightness fault, save separately, and compare before/after metrics",
    description=(
        "Demonstrates fault injection by reducing pixel brightness by 0.6x using NumPy. "
        "Saves the injected image in data/outputs/injected/ without modifying original dataset images, "
        "and compares quality status and metrics before and after."
    ),
    responses={
        404: {"description": "Target image not found in dataset directory"},
        422: {"description": "Target image file corrupted or unreadable by OpenCV"},
    },
)
def compare_fault_injection(current_settings: Settings = Depends(get_settings)) -> FaultComparisonResponse:
    """Compare original image against an artificially injected low-brightness version."""
    target_dir = current_settings.absolute_dataset_path / "train" / "good"
    image_path = find_first_png(target_dir)
    if image_path is None:
        raise HTTPException(status_code=404, detail=f"No PNG image found in {target_dir}")

    original_img = cv2.imread(str(image_path.resolve()))
    if original_img is None:
        raise HTTPException(status_code=422, detail=f"Failed to read image file: {image_path.name}")

    # 1. Analyze original image
    orig_metrics = analyze_brightness(original_img)
    orig_eval = evaluate_image_quality(
        orig_metrics,
        low_threshold=current_settings.BRIGHTNESS_LOW_THRESHOLD,
        high_threshold=current_settings.BRIGHTNESS_HIGH_THRESHOLD,
    )

    # 2. Inject fault (0.6x factor by default)
    factor = current_settings.FAULT_INJECTION_FACTOR
    faulty_img = inject_brightness_fault(original_img, factor=factor)

    # 3. Save modified image to separate output directory WITHOUT overwriting original
    injected_filename = f"fault_factor_{factor:.1f}_{image_path.name}"
    saved_path = save_modified_image(
        image=faulty_img,
        output_dir=current_settings.absolute_injected_path,
        filename=injected_filename,
    )

    # 4. Analyze fault-injected image
    faulty_metrics = analyze_brightness(faulty_img)
    faulty_eval = evaluate_image_quality(
        faulty_metrics,
        low_threshold=current_settings.BRIGHTNESS_LOW_THRESHOLD,
        high_threshold=current_settings.BRIGHTNESS_HIGH_THRESHOLD,
    )

    # 5. Formulate comparison report
    mean_diff = round(faulty_metrics["mean"] - orig_metrics["mean"], 2)
    ratio = round(faulty_metrics["mean"] / orig_metrics["mean"], 3) if orig_metrics["mean"] > 0 else 0.0

    return FaultComparisonResponse(
        original=ComparisonItem(
            filename=image_path.name,
            saved_path=str(image_path.resolve()),
            metrics=BrightnessMetrics(**orig_metrics),
            quality_status=orig_eval["quality_status"],
            warning_triggered=orig_eval["warning_triggered"],
            description=orig_eval["description"],
        ),
        fault_injected=ComparisonItem(
            filename=injected_filename,
            saved_path=str(saved_path),
            factor=factor,
            metrics=BrightnessMetrics(**faulty_metrics),
            quality_status=faulty_eval["quality_status"],
            warning_triggered=faulty_eval["warning_triggered"],
            description=faulty_eval["description"],
        ),
        comparison={
            "mean_difference": mean_diff,
            "measured_ratio": ratio,
            "expected_factor": factor,
            "quality_status_changed": orig_eval["quality_status"] != faulty_eval["quality_status"],
            "warning_escalated": not orig_eval["warning_triggered"] and faulty_eval["warning_triggered"],
        },
        applied_thresholds={
            "low_threshold": current_settings.BRIGHTNESS_LOW_THRESHOLD,
            "high_threshold": current_settings.BRIGHTNESS_HIGH_THRESHOLD,
        },
        product_defect_inspection=ProductInspectionStatus(),
    )


@app.post(
    "/inspections",
    response_model=InspectionResponse,
    status_code=201,
    summary="Create and execute an inspection with brightness analysis and event logging",
    description=(
        "Receives product_id and a server-managed neutral image_id, loads the image securely via OpenCV, "
        "calculates brightness and quality metrics, logs lifecycle events to inspection_logs.jsonl, "
        "persists the inspection outcome to inspections.jsonl, and returns the inspection result."
    ),
    responses={
        400: {"description": "Invalid or disallowed image_id"},
        404: {"description": "Image file not found on server"},
        422: {"description": "Image file corrupted or unreadable by OpenCV"},
        500: {"description": "Storage persistence failure"},
    },
)
def create_inspection_endpoint(
    payload: InspectionCreateRequest,
    current_settings: Settings = Depends(get_settings),
) -> InspectionResponse:
    """Execute inspection workflow with automated JSONL logging, brightness analysis, and PatchCore inference."""
    registry = get_image_registry(current_settings)
    storage = get_inspection_storage()
    inferencer = get_patchcore_inferencer() if getattr(current_settings, "ENABLE_PATCHCORE", True) else None

    try:
        record, logs = execute_inspection_workflow(
            product_id=payload.product_id,
            image_id=payload.image_id,
            registry=registry,
            storage=storage,
            low_threshold=current_settings.BRIGHTNESS_LOW_THRESHOLD,
            high_threshold=current_settings.BRIGHTNESS_HIGH_THRESHOLD,
            inferencer=inferencer,
            decision_threshold=current_settings.DECISION_THRESHOLD,
        )

        image_metadata = ImageMetadataResponse(
            filename=f"{record.image_id}.png",
            width=int(record.metrics.get("width", 0)),
            height=int(record.metrics.get("height", 0)),
            channels=int(record.metrics.get("channels", 3)),
        )

        return InspectionResponse(
            inspection_id=record.inspection_id,
            product_id=record.product_id,
            image_id=record.image_id,
            status=record.status,
            result=record.result,
            timestamp=record.timestamp,
            image_quality_status=record.image_quality_status,
            metrics=record.metrics,
            image_metadata=image_metadata,
            anomaly_score=record.anomaly_score,
            inference_time_ms=record.inference_time_ms,
            model_version=record.metrics.get("model_version"),
            decision_threshold=record.decision_threshold,
            defect_detection_status=record.defect_detection_status,
            final_result=record.final_result,
            final_reason_code=record.final_reason_code,
        )
    except KeyError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
    except StorageError as err:
        raise HTTPException(status_code=500, detail=f"Storage error: Failed to persist inspection record: {err}")



@app.get(
    "/inspections/images",
    summary="List available neutral image IDs for inspection",
    description="Returns list of registered neutral image IDs without leaking dataset directory names or labels.",
)
def list_inspection_images(
    current_settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """List neutral image IDs managed by the server."""
    registry = get_image_registry(current_settings)
    image_ids = registry.list_image_ids()
    return {
        "total_images": len(image_ids),
        "sample_ids": image_ids[:10],
        "image_ids": image_ids,
    }


if __name__ == "__main__":
    # Allows direct execution: python -m backend.main
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=(settings.ENVIRONMENT == "local"),
        reload_dirs=["backend"] if settings.ENVIRONMENT == "local" else None,
    )
