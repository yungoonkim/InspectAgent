"""Separate session-protected offline Vision review routes."""

from pathlib import Path
import threading

from fastapi import APIRouter, Request

from backend.capture_store import CaptureError
from backend.grab_inspection import GrabInspectionError, get_grab_runtime
from backend.video_api import get_video_runtime, public_error, require_origin
from backend.vision_review import VisionRequest, VisionReviewError, VisionReviewService, validate_crop


_runtime_lock = threading.Lock()


def build_router(storage_getter):
    router = APIRouter()

    def prepare(request, inspection_id, write=False):
        runtime = get_video_runtime(request)
        if write or request.headers.get("origin") is not None:
            require_origin(request, runtime)
        owner = runtime.captures.authorize(request.cookies.get(runtime.captures.cookie_name),
            request.headers.get("x-capture-csrf"), write=write)
        record = storage_getter().get_inspection(inspection_id)
        if record is None:
            raise VisionReviewError(404, "VISION_INSPECTION_NOT_FOUND")
        if record.metrics.get("input_source") != "LIVEVIEW_GRAB" or record.final_result != "REINSPECT":
            raise VisionReviewError(409, "VISION_INPUT_NOT_ELIGIBLE")
        raw = get_grab_runtime(request, runtime.settings).authorize_record(record, owner)
        with _runtime_lock:
            if not hasattr(request.app.state, "vision_review_service"):
                request.app.state.vision_review_service = VisionReviewService(Path(runtime.settings.absolute_output_path) / "vision_reviews")
            service = request.app.state.vision_review_service
        return service, owner, validate_crop(record, raw, service.policy), raw

    @router.get("/inspections/{inspection_id}/vision-review")
    def get_review(inspection_id: str, request: Request):
        try:
            service, owner, image, raw = prepare(request, inspection_id)
            review = service.get(owner, image)
            return {"available": review is not None, "review": review, "capabilities": service.capabilities()}
        except (CaptureError, GrabInspectionError, VisionReviewError) as error:
            public_error(error)

    @router.post("/inspections/{inspection_id}/vision-review")
    async def create_review(inspection_id: str, payload: VisionRequest, request: Request):
        try:
            service, owner, image, raw = prepare(request, inspection_id, write=True)
            def revalidate():
                try:
                    return prepare(request, inspection_id)[2]
                except (CaptureError, GrabInspectionError, VisionReviewError):
                    raise VisionReviewError(409, "VISION_INPUT_CHANGED") from None
            review = await service.create(owner, image, raw, payload.request_id,
                revalidate)
            return {"available": True, "review": review, "capabilities": service.capabilities()}
        except (CaptureError, GrabInspectionError, VisionReviewError) as error:
            public_error(error)

    return router
