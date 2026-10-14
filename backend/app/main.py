"""FastAPI application entrypoint for the Cost-Sensitive Fraud Detection API.

Configures application metadata, CORS policies, global error handling,
health monitoring probes, and versioned API routers.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.router import api_router
from backend.app.core.config import settings

logging.basicConfig(
    level=logging.INFO if not settings.APP_DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fraud_api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and teardown lifecycles."""
    logger.info("Initializing %s (v%s) [%s]", settings.PROJECT_NAME, settings.VERSION, settings.APP_ENV)
    yield
    logger.info("Shutting down %s", settings.PROJECT_NAME)


def create_application() -> FastAPI:
    """Factory creating and configuring the primary FastAPI application instance."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=(
            "Research-grade decision-support API for cost-sensitive fraud risk estimation, "
            "calibrated probability assessment, and human-in-the-loop operator feedback."
        ),
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
        lifespan=lifespan,
    )

    # Configure CORS safely
    cors_origins = [str(origin) for origin in settings.CORS_ORIGINS]
    has_wildcard = "*" in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=not has_wildcard,  # Wildcard + credentials prohibited by specification
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Global Exception Handler protecting against data/infrastructure leakage
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled exception on %s %s: %s",
            request.method,
            request.url.path,
            str(exc),
            exc_info=settings.APP_DEBUG,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred. Please contact system support."},
        )

    # Mount Root Health Probes (e.g. GET /health/live, GET /health/ready)
    app.include_router(health_router, prefix="/health")

    # Mount API v1 Routers (e.g. /api/v1/auth/login, /api/v1/health/ready)
    app.include_router(api_router, prefix=settings.API_V1_STR)

    return app


# Application singleton
app = create_application()
