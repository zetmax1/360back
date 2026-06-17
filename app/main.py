"""
FastAPI application factory.

Registers:
  - All routers under /api/v1
  - Global exception handlers
  - Static file serving for /uploads
  - Lifespan events (Redis connect/disconnect)
  - Rate limiter
  - CORS middleware
  - Security headers (HSTS, X-Frame-Options, etc.)
  - Structured logging
"""
from __future__ import annotations

import logging
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.config import settings
from app.database import close_redis, get_db, get_redis
from app.exceptions import (
    AppError,
    app_error_handler,
    generic_exception_handler,
    validation_exception_handler,
)
from app.links.router import router as links_router
from app.scenes.router import router as scenes_router
from app.tours.router import router as tours_router
from app.upload.router import router as upload_router
from app.admin.cache_router import router as cache_router
from app.database import _get_session_factory
from app.cache.warmup import warm_cache
from app.cache.service import CacheService
from app.dependencies import get_cache


# ── Structured logging setup ─────────────────────────────────────────────────
def _configure_logging() -> None:
    """Configure logging based on environment settings."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    if settings.LOG_FORMAT == "json":
        try:
            from pythonjsonlogger import jsonlogger
            handler.setFormatter(
                jsonlogger.JsonFormatter(
                    "%(asctime)s %(name)s %(levelname)s %(message)s",
                    rename_fields={"asctime": "timestamp", "levelname": "level"},
                )
            )
        except ImportError:
            # Fallback if python-json-logger not installed
            handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
            )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )

    root_logger.addHandler(handler)

    # Suppress noisy loggers in production
    if settings.is_production:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)

_configure_logging()
logger = logging.getLogger(__name__)


# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ── Sentry integration (optional) ────────────────────────────────────────────
def _init_sentry() -> None:
    """Initialize Sentry if DSN is configured."""
    if not settings.SENTRY_DSN:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        def _scrub_sensitive_data(event, hint):
            if "request" in event and "headers" in event["request"]:
                headers = event["request"]["headers"]
                # Remove sensitive headers
                for key in ("Authorization", "Cookie", "authorization", "cookie"):
                    headers.pop(key, None)
            return event

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            integrations=[FastApiIntegration()],
            before_send=_scrub_sensitive_data,
        )
        logger.info("Sentry initialized for environment: %s", settings.ENVIRONMENT)
    except ImportError:
        logger.warning("sentry-sdk not installed — error tracking disabled")


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — connecting to Redis…")
    await get_redis()

    # Ensure upload directory exists
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    logger.info("Upload directory ready: %s", settings.UPLOAD_DIR)

    # Initialize Sentry
    _init_sentry()

    # Warm cache
    try:
        factory = _get_session_factory()
        async with factory() as db:
            cache = CacheService(await get_redis())
            await warm_cache(db, cache)
    except Exception as e:
        logger.error("Failed to warm cache on startup: %s", e)

    yield

    logger.info("Shutting down — closing Redis connection…")
    await close_redis()


# ── App factory ───────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="360° Virtual Tour API",
        description=(
            "Backend for a self-hosted 360° virtual tour application.\n\n"
            "Scenes are connected via directional links — each link carries a compass "
            "bearing (0–359°) that the frontend uses to overlay navigation arrows "
            "on the equirectangular panorama, similar to Google Street View."
        ),
        version="1.0.0",
        # Disable interactive docs in production for security
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Rate limiter state ────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
        expose_headers=["X-Total-Count"],
        max_age=600,
    )

    # ── GZip compression ─────────────────────────────────────────────────
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # ── Security Headers ──────────────────────────────────────────────────────
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # HSTS — tell browsers to always use HTTPS (1 year, include subdomains)
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Force CORS headers for static files
        if request.url.path.startswith("/scenes/"):
            response.headers["Access-Control-Allow-Origin"] = "*"

        return response

    # ── Exception handlers ────────────────────────────────────────────────────
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # ── Routers ───────────────────────────────────────────────────────────────
    prefix = "/api/v1"
    app.include_router(auth_router, prefix=prefix)
    app.include_router(tours_router, prefix=prefix)
    app.include_router(scenes_router, prefix=prefix)
    app.include_router(links_router, prefix=prefix)
    app.include_router(upload_router, prefix=prefix)
    app.include_router(admin_router, prefix=prefix)
    app.include_router(cache_router, prefix=prefix)

    # ── Static files: custom endpoint with aggressive caching ────────────
    _SCENE_FILE_PATTERN = re.compile(
        r'^[a-f0-9]+(_thumb|_low|_medium|_high)?\.jpe?g$'
    )

    @app.get("/scenes/{filename}", tags=["Static"])
    async def serve_scene_image(filename: str):
        """Serve scene images with immutable cache headers (UUID filenames never change)."""
        if not _SCENE_FILE_PATTERN.match(filename):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")

        file_path = Path(settings.UPLOAD_DIR) / filename
        if not file_path.exists():
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")

        return FileResponse(
            file_path,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",
                "ETag": f'"{filename}"',
                "Access-Control-Allow-Origin": "*",
            },
        )

    # ── Health Check — checks DB + Redis connectivity ─────────────────────
    @app.get("/health", tags=["Health"])
    async def health_check():
        """
        Comprehensive health check endpoint.
        Returns 200 if all dependencies are healthy, 503 if any are degraded.
        Use this for load balancer health checks and uptime monitoring.
        """
        db_ok = False
        redis_ok = False

        # Check database
        try:
            factory = _get_session_factory()
            async with factory() as db:
                await db.execute(text("SELECT 1"))
                db_ok = True
        except Exception:
            pass

        # Check Redis
        try:
            redis = await get_redis()
            redis_ok = await redis.ping()
        except Exception:
            pass

        all_healthy = db_ok and redis_ok
        status_code = 200 if all_healthy else 503

        return JSONResponse(
            status_code=status_code,
            content={
                "status": "healthy" if all_healthy else "degraded",
                "environment": settings.ENVIRONMENT,
                "checks": {
                    "database": "up" if db_ok else "down",
                    "redis": "up" if redis_ok else "down",
                },
            },
        )

    return app


app = create_app()
