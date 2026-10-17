from contextlib import asynccontextmanager
import hmac
import ipaddress
import os
import re
import threading

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.db import RoiSettings, database_engine, sessions
from backend.roi_models import Preset
from backend.roi_repository import RoiRepository
from backend.roi_schemas import ActivateVersion, ApproveVersion, CreatePreset, CreateVersion, RoiError, Scope
from backend.video_source import VideoError, VideoFileSource


def error(status, code):
    return HTTPException(status_code=status, detail={"error_code": code})


class RoiRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise error(422, "ROI_INPUT_INVALID") from None
            except RoiError as failure:
                raise error(failure.status, failure.code) from None
            except VideoError as failure:
                raise error(failure.status_code, failure.code) from None
            except IntegrityError:
                raise error(409, "ROI_DATABASE_CONFLICT") from None
            except SQLAlchemyError:
                raise error(503, "ROI_DATABASE_UNAVAILABLE") from None
        return guarded


router = APIRouter(prefix="/roi-presets", tags=["ROI administration"], route_class=RoiRoute)
_lock = threading.Lock()


class RoiRuntime:
    def __init__(self, settings=None):
        self.settings = settings or RoiSettings()
        self.engine = None
        self.source = VideoFileSource(self.settings.roi_video_root)

    def connection(self):
        with _lock:
            if self.engine is None:
                if self.settings.database_url is None:
                    raise RoiError(503, "ROI_DATABASE_UNCONFIGURED")
                try:
                    self.engine = database_engine(self.settings.database_url.get_secret_value())
                except (ValueError, SQLAlchemyError):
                    raise RoiError(503, "ROI_DATABASE_UNAVAILABLE") from None
        return sessions(self.engine)()

    def validate_scope(self, scope):
        entry = self.source.entry(scope.video_id)
        self.source.verified_path(scope.video_id)
        if entry.source_revision != scope.source_revision:
            raise RoiError(409, "ROI_SOURCE_REVISION_MISMATCH")
        if (entry.width, entry.height) != (scope.source_width, scope.source_height):
            raise RoiError(422, "ROI_SOURCE_SIZE_MISMATCH")
        products = {value.strip() for value in self.settings.roi_product_ids.split(",") if value.strip()}
        if scope.product_id not in products or any(marker in scope.product_id.lower() for marker in
                ("ground_truth", "broken", "contamination", "evaluation")):
            raise RoiError(422, "ROI_PRODUCT_NOT_REGISTERED")

    def validate_rectangle(self, scope, rectangle):
        if (min(rectangle.width, rectangle.height) < self.settings.roi_min_size
            or rectangle.x + rectangle.width > scope.source_width
            or rectangle.y + rectangle.height > scope.source_height):
            raise RoiError(422, "ROI_BOUNDS_INVALID")

    def close(self):
        if self.engine is not None:
            self.engine.dispose()


def get_roi_runtime(request: Request):
    if not hasattr(request.app.state, "roi_runtime"):
        with _lock:
            if not hasattr(request.app.state, "roi_runtime"):
                request.app.state.roi_runtime = RoiRuntime()
    return request.app.state.roi_runtime


def administrator(request: Request, runtime=Depends(get_roi_runtime)):
    settings = runtime.settings
    try:
        peer_is_local = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        peer_is_local = False
    if (settings.roi_environment != "local" or settings.application_environment != "local"
        or os.getenv("ENVIRONMENT", "local") != "local"
        or not peer_is_local or request.url.hostname not in ("localhost", "127.0.0.1", "::1")
        or "x-forwarded-for" in request.headers or "forwarded" in request.headers):
        raise error(403, "ROI_ADMIN_LOCAL_ONLY")
    origin = request.headers.get("origin")
    origins = {value.strip() for value in settings.roi_origins.split(",") if value.strip()}
    if origin is not None and origin not in origins:
        raise error(403, "ROI_ORIGIN_FORBIDDEN")
    expected = settings.roi_admin_token.get_secret_value() if settings.roi_admin_token else ""
    if re.fullmatch(r"[A-Za-z0-9_-]{32,128}", expected) is None:
        raise error(503, "ROI_ADMIN_UNCONFIGURED")
    provided = request.headers.get("authorization", "")
    if not hmac.compare_digest(provided.encode("utf8"), f"Bearer {expected}".encode("utf8")):
        raise error(401, "ROI_ADMIN_UNAUTHORIZED")
    return runtime


def repository(runtime=Depends(administrator)):
    try:
        with runtime.connection() as session:
            with session.begin():
                yield RoiRepository(session)
    except IntegrityError:
        raise error(409, "ROI_DATABASE_CONFLICT") from None
    except SQLAlchemyError:
        raise error(503, "ROI_DATABASE_UNAVAILABLE") from None


def stored_scope(preset):
    return Scope.model_validate({field: getattr(preset, field) for field in Scope.model_fields})


@router.get("")
def list_presets(limit: int = Query(default=50, ge=1, le=100), repo=Depends(repository, scope="function")):
    records = repo.session.scalars(select(Preset).order_by(Preset.created_at.desc(), Preset.roi_config_id).limit(limit)).all()
    return {"roi_presets": [repo.view(preset, preset.head_version) for preset in records]}


@router.get("/active")
def active_preset(video_id: str, source_revision: str, product_id: str,
                  source_width: int = Query(gt=0, le=1920), source_height: int = Query(gt=0, le=1080),
                  runtime=Depends(administrator), repo=Depends(repository, scope="function")):
    try:
        scope = Scope(video_id=video_id, source_revision=source_revision, product_id=product_id,
                      source_width=source_width, source_height=source_height)
    except ValueError:
        raise error(422, "ROI_INPUT_INVALID") from None
    runtime.validate_scope(scope)
    binding = repo.binding(scope.model_dump())
    if binding is None:
        raise RoiError(404, "ROI_ACTIVE_NOT_FOUND")
    return repo.view(repo.preset(binding.roi_config_id), binding.version)


@router.post("", status_code=201)
def create_preset(payload: CreatePreset, runtime=Depends(administrator), repo=Depends(repository, scope="function")):
    runtime.validate_scope(payload)
    runtime.validate_rectangle(payload, payload.roi)
    return repo.create(payload.model_dump(exclude={"roi"}), payload.roi.model_dump())


@router.get("/{roi_config_id}")
def get_preset(roi_config_id: str, repo=Depends(repository, scope="function")):
    preset = repo.preset(roi_config_id)
    return repo.view(preset, preset.head_version)


@router.get("/{roi_config_id}/versions")
def get_versions(roi_config_id: str, limit: int = Query(default=50, ge=1, le=100),
                 offset: int = Query(default=0, ge=0), repo=Depends(repository, scope="function")):
    preset = repo.preset(roi_config_id)
    return {"total_versions": preset.head_version,
            "versions": [repo.view(preset, version) for version in range(offset + 1, min(preset.head_version, offset + limit) + 1)]}


@router.post("/{roi_config_id}/versions", status_code=201)
def add_version(roi_config_id: str, payload: CreateVersion, runtime=Depends(administrator), repo=Depends(repository, scope="function")):
    scope = stored_scope(repo.preset(roi_config_id))
    runtime.validate_scope(scope)
    runtime.validate_rectangle(scope, payload.roi)
    return repo.add_version(roi_config_id, payload.expected_version, payload.roi.model_dump())


@router.post("/{roi_config_id}/approve")
def approve_version(roi_config_id: str, payload: ApproveVersion, runtime=Depends(administrator), repo=Depends(repository, scope="function")):
    runtime.validate_scope(stored_scope(repo.preset(roi_config_id)))
    return repo.approve(roi_config_id, payload.version)


@router.post("/{roi_config_id}/activate")
def activate_version(roi_config_id: str, payload: ActivateVersion, runtime=Depends(administrator), repo=Depends(repository, scope="function")):
    runtime.validate_scope(stored_scope(repo.preset(roi_config_id)))
    return repo.activate(roi_config_id, payload.version, payload.expected_active_revision)


def create_roi_app(runtime=None):
    runtime = runtime or RoiRuntime()

    @asynccontextmanager
    async def lifespan(app):
        yield
        runtime.close()

    app = FastAPI(lifespan=lifespan)
    app.state.roi_runtime = runtime
    app.include_router(router)
    return app
