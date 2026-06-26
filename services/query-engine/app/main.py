import json
import os
import secrets
from dataclasses import asdict
from datetime import UTC, datetime
from time import perf_counter

from fastapi import Depends, FastAPI, Header, HTTPException, status
from openai import AsyncOpenAI, OpenAIError

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
    QueryabilityCompileRequest,
    QueryabilityGraphArtifact,
    QueryabilityPathRequest,
    QueryabilityPathResult,
    SchemaIntrospectionRequest,
    SchemaIntrospectionResponse,
    SemanticLayer,
    SemanticGenerationRequest,
    SemanticGenerationResult,
    SemanticRebaseRequest,
    SemanticRebaseResult,
    SemanticReviewRequest,
    SemanticSeedRequest,
    SemanticValidationRequest,
)
from app.queryability import build_queryability_graph, find_queryability_paths
from app.semantic import (
    build_semantic_seed,
    rebase_semantic_layer,
    review_semantic_layer,
    validate_semantic_layer,
)
from app.semantic_discovery import (
    AnthropicSemanticDiscoveryGateway,
    OpenAISemanticDiscoveryGateway,
    SemanticDiscoveryError,
    SemanticDiscoveryInputTooLarge,
    SemanticDiscoveryProviderConfigurationError,
    SemanticDiscoveryProviderCredentialsRejected,
    SemanticDiscoveryProviderModelUnavailable,
    SemanticDiscoveryProviderRateLimited,
    SemanticDiscoveryRefused,
    SemanticProposalInvalid,
    generate_semantic_layer,
)
from app.secrets import (
    AIProviderSecretBinding,
    GcpSecretResolver,
    SecretResolutionError,
)

app = FastAPI(title="Atlante BI Query Engine", version="0.1.0")
app.state.secret_resolver = GcpSecretResolver()
app.state.semantic_discovery_gateway = None
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
            "snapshot_hash": result.snapshot_hash,
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


@app.post(
    "/queryability/compile",
    response_model=QueryabilityGraphArtifact,
    response_model_exclude_none=True,
)
async def compile_queryability_graph(
    request: QueryabilityCompileRequest,
    _: None = Depends(require_internal_auth),
) -> QueryabilityGraphArtifact:
    snapshot = request.snapshot
    if (
        snapshot.status != "ok"
        or snapshot.engine != "sqlserver"
        or snapshot.schema_hash is None
        or snapshot.snapshot_hash is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A successful SQL Server technical snapshot is required.",
        )

    return build_queryability_graph(
        snapshot=snapshot,
        tenant_id=str(request.tenant_id),
        connection_id=str(request.connection_id),
        schema_snapshot_id=str(request.schema_snapshot_id),
    )


@app.post(
    "/queryability/paths",
    response_model=QueryabilityPathResult,
    response_model_exclude_none=True,
)
async def queryability_paths(
    request: QueryabilityPathRequest,
    _: None = Depends(require_internal_auth),
) -> QueryabilityPathResult:
    return find_queryability_paths(
        graph=request.graph,
        from_node_key=request.from_node_key,
        to_node_key=request.to_node_key,
        max_hops=request.max_hops,
    )


@app.post(
    "/semantic/seed",
    response_model=SemanticLayer,
    response_model_exclude_none=True,
)
async def semantic_seed(
    request: SemanticSeedRequest,
    _: None = Depends(require_internal_auth),
) -> SemanticLayer:
    return build_semantic_seed(
        graph=request.graph,
        semantic_version_id=str(request.semantic_version_id),
        queryability_graph_version_id=str(
            request.queryability_graph_version_id
        ),
        version=request.version,
        semantic_policy=request.semantic_policy,
    )


@app.post(
    "/semantic/generate",
    response_model=SemanticGenerationResult,
)
async def semantic_generate(
    request: SemanticGenerationRequest,
    _: None = Depends(require_internal_auth),
) -> SemanticGenerationResult:
    try:
        gateway = await _get_semantic_discovery_gateway(request)
        return await generate_semantic_layer(
            graph=request.graph,
            seed=request.seed,
            gateway=gateway,
            semantic_policy=request.semantic_policy,
        )
    except SemanticDiscoveryInputTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except (SemanticDiscoveryRefused, SemanticProposalInvalid) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except SecretResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Semantic discovery provider credentials are not available.",
        ) from exc
    except SemanticDiscoveryProviderCredentialsRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Semantic discovery provider credentials were rejected.",
        ) from exc
    except SemanticDiscoveryProviderModelUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Semantic discovery provider model is unavailable.",
        ) from exc
    except SemanticDiscoveryProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Semantic discovery provider request configuration is invalid.",
        ) from exc
    except SemanticDiscoveryProviderRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Semantic discovery provider rate limit reached.",
        ) from exc
    except (SemanticDiscoveryError, OpenAIError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Semantic discovery provider request failed.",
        ) from exc


@app.post(
    "/semantic/review",
    response_model=SemanticLayer,
    response_model_exclude_none=True,
)
async def semantic_review(
    request: SemanticReviewRequest,
    _: None = Depends(require_internal_auth),
) -> SemanticLayer:
    try:
        return review_semantic_layer(
            source_layer=request.source_layer,
            graph=request.graph,
            semantic_policy=request.semantic_policy,
            patch=request.patch,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@app.post(
    "/semantic/validate",
    response_model=SemanticLayer,
    response_model_exclude_none=True,
)
async def semantic_validate(
    request: SemanticValidationRequest,
    _: None = Depends(require_internal_auth),
) -> SemanticLayer:
    return validate_semantic_layer(
        layer=request.semantic_layer,
        graph=request.graph,
        semantic_policy=request.semantic_policy,
    )


@app.post(
    "/semantic/rebase",
    response_model=SemanticRebaseResult,
    response_model_exclude_none=True,
)
async def semantic_rebase(
    request: SemanticRebaseRequest,
    _: None = Depends(require_internal_auth),
) -> SemanticRebaseResult:
    try:
        return rebase_semantic_layer(
            source_layer=request.source_layer,
            target_graph=request.target_graph,
            semantic_version_id=str(request.semantic_version_id),
            queryability_graph_version_id=str(
                request.queryability_graph_version_id
            ),
            version=request.version,
            semantic_policy=request.semantic_policy,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


async def _get_semantic_discovery_gateway(
    request: SemanticGenerationRequest,
) -> OpenAISemanticDiscoveryGateway | AnthropicSemanticDiscoveryGateway:
    gateway = app.state.semantic_discovery_gateway
    if gateway is not None:
        if os.getenv("PYTEST_CURRENT_TEST") or (
            os.getenv("ATLANTE_ALLOW_SEMANTIC_GATEWAY_OVERRIDE") == "true"
        ):
            return gateway
        app.state.semantic_discovery_gateway = None

    provider_config = request.provider_config
    api_key = await app.state.secret_resolver.resolve_ai_provider_api_key(
        binding=AIProviderSecretBinding(
            tenant_id=str(request.seed.tenant_id),
            setting_id=str(provider_config.setting_id),
            provider=provider_config.provider,
        ),
        secret_ref=provider_config.secret_ref,
        timeout_ms=30_000,
    )

    if provider_config.provider == "openai":
        return OpenAISemanticDiscoveryGateway(
            client=AsyncOpenAI(api_key=api_key),
            config=provider_config,
        )

    if provider_config.provider == "anthropic":
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Anthropic semantic discovery provider is not installed.",
            ) from exc
        return AnthropicSemanticDiscoveryGateway(
            client=AsyncAnthropic(api_key=api_key, max_retries=0),
            config=provider_config,
        )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Unsupported semantic discovery provider.",
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
