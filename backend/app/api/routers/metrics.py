"""Prometheus metrics exposition endpoint."""

from fastapi import APIRouter
from fastapi.responses import Response

from backend.app.infrastructure.metrics import CONTENT_TYPE_LATEST, generate_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def metrics() -> Response:
    """Expose Prometheus metrics in text exposition format."""
    return Response(content=generate_metrics(), media_type=CONTENT_TYPE_LATEST)
