from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.services.health_service import HealthService

router = APIRouter()


def get_health_service(request: Request) -> HealthService:
    service: HealthService = request.app.state.health_service
    return service


@router.get("/health")
async def health(service: Annotated[HealthService, Depends(get_health_service)]) -> JSONResponse:
    report = await service.report()
    return JSONResponse(
        {"status": "ok" if report.healthy else "degraded", "checks": report.checks},
        status_code=200 if report.healthy else 503,
    )
