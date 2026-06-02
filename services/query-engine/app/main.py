from fastapi import FastAPI, HTTPException

from app.models import HealthResponse, QueryRequest

app = FastAPI(title="Atlante BI Query Engine", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(service="atlantebi-query-engine", status="ok", version="0.1.0")


@app.post("/query/run", status_code=501)
async def run_query(request: QueryRequest) -> dict[str, str]:
    raise HTTPException(
        status_code=501,
        detail=(
            "Query execution is not implemented in the foundation milestone. "
            f"Validated request for tenant {request.tenant_id}."
        ),
    )
