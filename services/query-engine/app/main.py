import json
import os
import secrets
from dataclasses import asdict
from datetime import UTC, datetime
from time import perf_counter

from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.drivers.base import (
    ConnectionMetadata,
    DriverConfigurationError,
    DriverIntrospectionError,
    DriverNotImplementedError,
)
from app.drivers.registry import get_driver
from app.models import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    SchemaIntrospectionRequest,
    SchemaIntrospectionResponse,
)
from app.secrets import GcpSecretResolver, SecretResolutionError

app = FastAPI(title="Atlante BI Query Engine", version="0.1.0")
app.state.secret_resolver = GcpSecretResolver()
MAX_SCHEMA_SNAPSHOT_BYTES = 32 * 1024 * 1024


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
        if os.getenv("QUERY_ENGINE_AUTH_MODE") == "cloud_run_iam":
            return
        if os.getenv("QUERY_ENGINE_ALLOW_UNAUTHENTICATED") == "true":
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Query-engine authentication is not configured.",
        )

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
    connection = _connection_metadata_from_request(request.connection)

    try:
        driver = get_driver(connection.engine)
        credentials = await app.state.secret_resolver.resolve_database_credentials(
            connection,
            timeout_ms=request.timeout_ms,
        )
        result = await driver.test_connection(
            connection=connection,
            credentials=credentials,
            timeout_ms=_remaining_timeout_ms(started, request.timeout_ms),
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


@app.post(
    "/schema/introspect",
    response_model=SchemaIntrospectionResponse,
    response_model_exclude_none=True,
)
async def introspect_schema(
    request: SchemaIntrospectionRequest,
    _: None = Depends(require_internal_auth),
) -> SchemaIntrospectionResponse:
    started = perf_counter()
    introspected_at = datetime.now(UTC).isoformat()
    connection = _connection_metadata_from_request(request.connection)

    try:
        driver = get_driver(connection.engine)
        credentials = await app.state.secret_resolver.resolve_database_credentials(
            connection,
            timeout_ms=request.timeout_ms,
        )
        result = await driver.introspect_schema(
            connection=connection,
            credentials=credentials,
            timeout_ms=_remaining_timeout_ms(started, request.timeout_ms),
        )
        response_payload = {
            "status": "ok",
            "message": "Schema introspection completed.",
            "introspected_at": introspected_at,
            "duration_ms": int((perf_counter() - started) * 1000),
            "engine": result.engine,
            "database_name": result.database_name,
            "engine_version": result.engine_version,
            "schema_hash": result.schema_hash,
            "coverage_status": result.coverage_status,
            "tables": [asdict(table) for table in result.tables],
            "foreign_keys": [
                asdict(foreign_key) for foreign_key in result.foreign_keys
            ],
            "unique_constraints": [
                asdict(unique_constraint)
                for unique_constraint in result.unique_constraints
            ],
            "check_constraints": [
                asdict(check_constraint) for check_constraint in result.check_constraints
            ],
            "default_constraints": [
                asdict(default_constraint)
                for default_constraint in result.default_constraints
            ],
            "indexes": [asdict(index) for index in result.indexes],
            "coverage_warnings": [
                asdict(coverage_warning)
                for coverage_warning in result.coverage_warnings
            ],
        }
        if (
            len(
                json.dumps(
                    response_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            > MAX_SCHEMA_SNAPSHOT_BYTES
        ):
            raise DriverIntrospectionError(
                "SQL Server schema snapshot size limit exceeded."
            )
        return SchemaIntrospectionResponse(**response_payload)
    except SecretResolutionError as exc:
        return _schema_introspection_error(
            introspected_at=introspected_at,
            started=started,
            status="engine_error",
            message="Schema introspection failed before reaching the customer database.",
            sanitized_error=str(exc),
        )
    except (DriverConfigurationError, DriverNotImplementedError) as exc:
        return _schema_introspection_error(
            introspected_at=introspected_at,
            started=started,
            status="engine_error",
            message="Schema introspection cannot run with the current engine configuration.",
            sanitized_error=str(exc),
        )
    except DriverIntrospectionError as exc:
        return _schema_introspection_error(
            introspected_at=introspected_at,
            started=started,
            status="failed",
            message="Schema introspection failed against the customer database.",
            sanitized_error=str(exc),
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


def _remaining_timeout_ms(started: float, timeout_ms: int) -> int:
    remaining = timeout_ms - int((perf_counter() - started) * 1000)
    if remaining < 1000:
        raise SecretResolutionError("Operation deadline exceeded.")
    return remaining


def _schema_introspection_error(
    introspected_at: str,
    started: float,
    status: str,
    message: str,
    sanitized_error: str,
) -> SchemaIntrospectionResponse:
    return SchemaIntrospectionResponse(
        status=status,
        message=message,
        introspected_at=introspected_at,
        duration_ms=int((perf_counter() - started) * 1000),
        coverage_status="blocked",
        sanitized_error=sanitized_error,
    )


def _connection_metadata_from_request(connection_input) -> ConnectionMetadata:
    return ConnectionMetadata(
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
