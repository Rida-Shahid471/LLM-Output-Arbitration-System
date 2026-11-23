from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field

from src.config import settings
from src.errors import ArbitrationError, PersistenceError
from src.input_parser import parse_input
from src.schemas import ArbitrationRequest, ArbitrationResult, StrictModel
from src.workflow import ArbitrationEngine

app = FastAPI(title="LLM Output Arbitration System", version="1.0.0", description="Audits an LLM answer using three specialist critics and evidence-based adjudication.")


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    if request.url.path == "/v1/arbitrate/batch" and any(
        error.get("type") == "too_long" and "items" in error.get("loc", ())
        for error in exc.errors()
    ):
        return JSONResponse(status_code=413, content={"detail": f"Batch limit is {settings.max_batch_size} items (absolute maximum 20)."})
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


class BatchRequest(StrictModel):
    # Enforce the configured limit in the route so every over-limit request
    # receives the documented 413 response instead of a Pydantic 422.
    items: list[ArbitrationRequest] = Field(min_length=1, max_length=20)


@lru_cache(maxsize=1)
def _engine() -> ArbitrationEngine:
    return ArbitrationEngine()


@app.get("/v1/health/live")
def health_live() -> dict[str, str]:
    """Liveness only; deliberately does not initialize storage or call providers."""
    return {"status": "ok"}


@app.get("/v1/health/ready")
@app.get("/v1/health")
def health_ready() -> dict[str, str]:
    """Configuration readiness; provider connectivity is not probed here."""
    try:
        return {"status": "configured", "provider": _engine().provider, "provider_connectivity": "not_checked"}
    except ArbitrationError as exc:
        raise HTTPException(status_code=503, detail="Arbitration service is not ready.") from exc


@app.post("/v1/arbitrate", response_model=ArbitrationResult)
def arbitrate(request: ArbitrationRequest) -> ArbitrationResult:
    try:
        return _engine().arbitrate(request.original_prompt, request.candidate_answer)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ArbitrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/arbitrate/batch", response_model=list[ArbitrationResult])
def arbitrate_batch(request: BatchRequest) -> list[ArbitrationResult]:
    if len(request.items) > settings.max_batch_size:
        raise HTTPException(status_code=413, detail=f"Batch limit is {settings.max_batch_size} items.")
    try:
        # Validate the entire batch, including configured character limits,
        # before invoking the workflow or writing any audit records.
        validated = [parse_input(item.original_prompt, item.candidate_answer) for item in request.items]
        engine = _engine()
        for item in validated:
            engine.validate_provider_input(item)
        results = [engine.arbitrate(item.original_prompt, item.candidate_answer, persist=False) for item in validated]
        if engine.store:
            engine.store.save_many(results)
        return results
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ArbitrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/v1/arbitrations/{arbitration_id}", response_model=ArbitrationResult)
def get_arbitration(arbitration_id: str) -> ArbitrationResult:
    try:
        result = _engine().store.get(arbitration_id) if _engine().store else None
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Arbitration not found.")
    return result


@app.get("/v1/arbitrations", response_model=list[ArbitrationResult])
def list_arbitrations(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> list[ArbitrationResult]:
    try:
        return _engine().store.list(limit=limit, offset=offset) if _engine().store else []
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/v1/analytics")
def analytics() -> dict:
    try:
        return _engine().store.analytics() if _engine().store else {"total_arbitrations": 0}
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
