"""API v1 master router aggregating sub-routers."""

from fastapi import APIRouter

from backend.app.api.v1.alerts import router as alerts_router
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.feedback import router as feedback_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.models import router as models_router
from backend.app.api.v1.monitoring import router as monitoring_router
from backend.app.api.v1.transactions import router as transactions_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health")
api_router.include_router(auth_router)
api_router.include_router(transactions_router)
api_router.include_router(feedback_router)
api_router.include_router(monitoring_router)
api_router.include_router(models_router, prefix="/models")
api_router.include_router(alerts_router)


