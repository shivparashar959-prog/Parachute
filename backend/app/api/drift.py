"""Compatibility endpoint that queues documentation drift analyses."""

from fastapi import APIRouter, Depends, Header, Request, status

from app.api.analyses import _create_analysis
from app.auth.csrf import require_trusted_origin
from app.auth.dependencies import AuthenticatedPrincipal, get_current_principal
from app.db.session import get_db
from app.schemas.analysis import AnalysisJobResponse
from app.schemas.drift import DriftAnalysisRequest
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/api/analyze",
    tags=["Drift Detection"],
    dependencies=[Depends(get_current_principal)],
)


@router.post(
    "/drift",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue deterministic documentation drift detection",
)
def analyze_documentation_drift_endpoint(
    payload: DriftAnalysisRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
    ),
) -> AnalysisJobResponse:
    require_trusted_origin(request)
    return _create_analysis(payload, principal, db, idempotency_key)
