import os
import secrets
from datetime import UTC, datetime
from time import perf_counter

from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.drivers.base import (
    ConnectionMetadata,
    DriverConfigurationError,
    DriverNotImplementedError,
)
from app.drivers.registry import get_driver
from app.models import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    HealthResponse,
    QueryRequest,
    QueryResponse,
)
from app.secrets import GcpSecretResolver, SecretResolutionError

app = FastAPI(title="Atlante BI Query Engine", version="0.1.0")
app.state.secret_resolver = GcpSecretResolver()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(service="atlantebi-query-engine", status="ok", version="0.1.0")


def require_internal_auth(
    authorization: str | None = Header(default=None),
    internal_token: str | None = Header(
        default=None,
        alias="x-atlante-query-engine-token",
    ),
) -> None:
    expected_token = os.getenv("QUERY_ENGINE_API_TOKEN")

    if not expected_token:
        return

    expected_header = f"Bearer {expected_token}"
    authorization_valid = authorization is not None and secrets.compare_digest(
        authorization,
        expected_header,
    )
    internal_token_valid = internal_token is not None and secrets.compare_digest(
        internal_token,
        expected_token,
    )

    if authorization_valid or internal_token_valid:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid query-engine credentials.",
    )


@app.post(
    "/connections/test",
    response_model=ConnectionTestResponse,
    response_model_exclude_none=True,
)
async def test_connection(
    request: ConnectionTestRequest,
    _: None = Depends(require_internal_auth),
) -> ConnectionTestResponse:
    started = perf_counter()
    checked_at = datetime.now(UTC).isoformat()
    connection_input = request.connection
    connection = ConnectionMetadata(
        tenant_id=str(connection_input.tenant_id),
        connection_id=str(connection_input.connection_id),
        name=connection_input.name,
        engine=connection_input.engine,
        network_mode=connection_input.network_mode.value,
        host=connection_input.host,
        port=connection_input.port,
        database_name=connection_input.database_name,
        username=connection_input.username,
        secret_ref=connection_input.secret_ref,
        tls_required=connection_input.tls_required,
        trust_server_certificate=connection_input.trust_server_certificate,
        tls_server_name=connection_input.tls_server_name,
    )

    try:
        credentials = await app.state.secret_resolver.resolve_database_credentials(
            connection.secret_ref
        )
        driver = get_driver(connection.engine)
        result = await driver.test_connection(
            connection=connection,
            credentials=credentials,
            timeout_ms=request.timeout_ms,
        )
        duration_ms = int((perf_counter() - started) * 1000)
        response = {
            "status": result.status,
            "message": result.message,
            "checked_at": checked_at,
            "duration_ms": duration_ms,
        }
        if result.status != "ok":
            response["sanitized_error"] = result.message
        return ConnectionTestResponse(**response)
    except SecretResolutionError as exc:
        return _connection_test_error(
            checked_at=checked_at,
            started=started,
            message=str(exc),
        )
    except (DriverConfigurationError, DriverNotImplementedError):
        return _connection_test_error(
            checked_at=checked_at,
            started=started,
            message="Connection test cannot run with the current engine configuration.",
        )


def _connection_test_error(
    checked_at: str,
    started: float,
    message: str,
) -> ConnectionTestResponse:
    return ConnectionTestResponse(
        status="engine_error",
        message="Connection test failed before reaching the customer database.",
        checked_at=checked_at,
        duration_ms=int((perf_counter() - started) * 1000),
        sanitized_error=message,
    )


@app.post("/query/run", response_model=QueryResponse, response_model_exclude_none=True)
async def run_query(
    request: QueryRequest,
    _: None = Depends(require_internal_auth),
) -> QueryResponse:
    raise HTTPException(
        status_code=501,
        detail=(
            "Query execution is not implemented in the foundation milestone. "
            f"Validated request for tenant {request.tenant_id}."
        ),
    )
