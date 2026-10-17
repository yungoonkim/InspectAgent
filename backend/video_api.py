from pathlib import Path
import threading
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from backend.capture_store import CaptureError, CaptureStore
from backend.config import PROJECT_ROOT, Settings, get_settings
from backend.video_source import VideoError, VideoFileSource


router = APIRouter(tags=["Video and captures"])
_runtime_lock = threading.Lock()


def allowed_origins(settings: Settings) -> list[str]:
    origins = [origin.strip() for origin in settings.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]
    for origin in origins:
        parsed = urlsplit(origin)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password or "*" in origin:
            raise ValueError("CORS origins must be explicit HTTP origins")
    return origins


def configured_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


class VideoRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.origins = allowed_origins(settings)
        self.source = VideoFileSource(
            configured_path(settings.VIDEO_ROOT), max_bytes=settings.VIDEO_MAX_BYTES,
            max_width=settings.VIDEO_MAX_WIDTH, max_height=settings.VIDEO_MAX_HEIGHT,
            max_frames=settings.VIDEO_MAX_FRAMES, max_decoders=settings.VIDEO_MAX_DECODERS,
        )
        self.captures = CaptureStore(
            configured_path(settings.CAPTURE_DIR), ttl_seconds=settings.CAPTURE_TTL_SECONDS,
            session_seconds=settings.CAPTURE_SESSION_SECONDS, max_bytes=settings.CAPTURE_MAX_BYTES,
            max_captures=settings.CAPTURE_MAX_COUNT, max_per_session=settings.CAPTURE_MAX_PER_SESSION,
            max_sessions=settings.CAPTURE_MAX_SESSIONS,
        )


def get_video_runtime(request: Request) -> VideoRuntime:
    with _runtime_lock:
        if not hasattr(request.app.state, "video_runtime"):
            request.app.state.video_runtime = VideoRuntime(get_settings())
        return request.app.state.video_runtime


def public_error(error):
    raise HTTPException(status_code=error.status_code, detail={"error_code": error.code}) from None


def require_origin(request: Request, runtime: VideoRuntime):
    if request.headers.get("origin") not in runtime.origins:
        raise HTTPException(status_code=403, detail={"error_code": "CAPTURE_ORIGIN_FORBIDDEN"})


class VideoMetadata(BaseModel):
    video_id: str
    source_revision: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float
    codec: str
    stream_url: str
    frame_index_min: int
    frame_index_max: int


class VideoList(BaseModel):
    videos: list[VideoMetadata]


class GrabRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_index: StrictInt = Field(ge=0)
    source_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class CaptureMetadata(BaseModel):
    capture_id: str
    video_id: str
    frame_index: int
    source_revision: str
    frame_timestamp_ms: float
    timestamp_basis: str
    pts_ms: float | None
    width: int
    height: int
    image_url: str
    created_at: str
    expires_at: str
    status: str


@router.get("/videos", response_model=VideoList)
def videos(runtime: VideoRuntime = Depends(get_video_runtime)):
    try:
        return {"videos": runtime.source.list_videos()}
    except VideoError as error:
        public_error(error)


@router.get("/videos/{video_id}", response_model=VideoMetadata)
def video_metadata(video_id: str, runtime: VideoRuntime = Depends(get_video_runtime)):
    try:
        return runtime.source.metadata(video_id)
    except VideoError as error:
        public_error(error)


@router.get("/videos/{video_id}/stream", operation_id="get_video_stream", response_class=FileResponse,
            responses={200: {"content": {"video/mp4": {}}}, 206: {"description": "Partial video content"}, 416: {"description": "Range not satisfiable"}})
@router.head("/videos/{video_id}/stream", operation_id="head_video_stream", response_class=FileResponse)
def video_stream(video_id: str, runtime: VideoRuntime = Depends(get_video_runtime)):
    try:
        runtime.source.metadata(video_id)
        path = runtime.source.verified_path(video_id)
        revision = runtime.source.entry(video_id).source_revision
        return FileResponse(path, media_type="video/mp4", headers={
            "ETag": f'"{revision}"', "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff",
        })
    except VideoError as error:
        public_error(error)


@router.post("/capture-sessions")
def capture_session(request: Request, response: Response, runtime: VideoRuntime = Depends(get_video_runtime)):
    require_origin(request, runtime)
    try:
        token, csrf = runtime.captures.bootstrap(request.cookies.get(CaptureStore.cookie_name))
        secure = runtime.settings.CAPTURE_COOKIE_SECURE or runtime.settings.ENVIRONMENT != "local"
        response.set_cookie(CaptureStore.cookie_name, token, httponly=True, secure=secure,
                            samesite="strict", path="/", max_age=runtime.settings.CAPTURE_SESSION_SECONDS)
        response.headers["Cache-Control"] = "no-store"
        return {"csrf_token": csrf, "session_ttl_seconds": runtime.settings.CAPTURE_SESSION_SECONDS,
                "capture_ttl_seconds": runtime.settings.CAPTURE_TTL_SECONDS}
    except CaptureError as error:
        public_error(error)


@router.post("/videos/{video_id}/grab", response_model=CaptureMetadata, status_code=201)
def grab_video(video_id: str, payload: GrabRequest, request: Request,
               runtime: VideoRuntime = Depends(get_video_runtime)):
    try:
        runtime.source.validate_request(video_id, payload.source_revision, payload.frame_index)
        require_origin(request, runtime)
        token = request.cookies.get(CaptureStore.cookie_name)
        csrf = request.headers.get("x-capture-csrf")
        runtime.captures.authorize(token, csrf, write=True)
        frame, metadata = runtime.source.grab_frame(video_id, payload.frame_index, payload.source_revision)
        return runtime.captures.save(token, csrf, frame, metadata, payload.frame_index)
    except (VideoError, CaptureError) as error:
        public_error(error)


@router.get("/captures/{capture_id}", response_model=CaptureMetadata)
def capture_metadata(capture_id: str, request: Request, response: Response,
                     runtime: VideoRuntime = Depends(get_video_runtime)):
    try:
        response.headers["Cache-Control"] = "no-store"
        return runtime.captures.metadata(request.cookies.get(CaptureStore.cookie_name), capture_id)
    except CaptureError as error:
        public_error(error)


@router.get("/captures/{capture_id}/image", response_class=Response,
            responses={200: {"content": {"image/png": {}}}})
def capture_image(capture_id: str, request: Request, runtime: VideoRuntime = Depends(get_video_runtime)):
    try:
        payload = runtime.captures.image(request.cookies.get(CaptureStore.cookie_name), capture_id)
        return Response(payload, media_type="image/png", headers={
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        })
    except CaptureError as error:
        public_error(error)
