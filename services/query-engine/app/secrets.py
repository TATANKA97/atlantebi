import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass

from pydantic import ValidationError

from app.drivers.base import ConnectionMetadata, DatabaseCredentials
from app.models import DatabaseCredentialsInput

SECRET_REF_PATTERN = re.compile(
    r"^gcp-secret-manager://projects/(?P<project>[^/]+)/secrets/(?P<secret>[^/]+)(?:/versions/(?P<version>[^/]+))?$"
)


class SecretResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ParsedSecretRef:
    project: str
    secret: str
    version: str

    @property
    def resource_name(self) -> str:
        return f"projects/{self.project}/secrets/{self.secret}/versions/{self.version}"


@dataclass(frozen=True)
class AIProviderSecretBinding:
    tenant_id: str
    setting_id: str
    provider: str


def parse_secret_ref(secret_ref: str) -> ParsedSecretRef:
    match = SECRET_REF_PATTERN.fullmatch(secret_ref)
    if match is None:
        raise SecretResolutionError("Invalid Secret Manager reference.")

    return ParsedSecretRef(
        project=match.group("project"),
        secret=match.group("secret"),
        version=match.group("version") or "latest",
    )


def secret_binding_fingerprint(connection: ConnectionMetadata) -> str:
    canonical = "\n".join(
        [
            connection.tenant_id.lower(),
            connection.connection_id.lower(),
            connection.host.strip().lower().removesuffix("."),
            str(connection.port),
            connection.database_name,
            connection.username,
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def ai_secret_binding_fingerprint(binding: AIProviderSecretBinding) -> str:
    canonical = "\n".join(
        [
            binding.tenant_id.lower(),
            binding.setting_id.lower(),
            binding.provider.lower(),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def validate_secret_ref_for_connection(
    parsed: ParsedSecretRef,
    connection: ConnectionMetadata,
    expected_project: str,
) -> None:
    if parsed.project != expected_project:
        raise SecretResolutionError("Database secret project is not authorized.")

    tenant_id = connection.tenant_id.lower()
    connection_id = connection.connection_id.lower()
    expected_name = re.compile(
        rf"^atlantebi-{re.escape(tenant_id)}-{re.escape(connection_id)}"
        r"(?:-[0-9a-f-]{36})?-db-password(?:-test)?$"
    )
    if expected_name.fullmatch(parsed.secret) is None:
        raise SecretResolutionError(
            "Database secret is not bound to this tenant connection."
        )


def validate_secret_ref_for_ai_provider(
    parsed: ParsedSecretRef,
    binding: AIProviderSecretBinding,
    expected_project: str,
) -> None:
    if parsed.project != expected_project:
        raise SecretResolutionError("AI provider secret project is not authorized.")

    tenant_id = binding.tenant_id.lower()
    setting_id = binding.setting_id.lower()
    provider = binding.provider.lower()
    expected_name = re.compile(
        rf"^atlantebi-{re.escape(tenant_id)}-{re.escape(setting_id)}-"
        rf"{re.escape(provider)}-ai-key$"
    )
    if expected_name.fullmatch(parsed.secret) is None:
        raise SecretResolutionError(
            "AI provider secret is not bound to this tenant setting."
        )


class GcpSecretResolver:
    def __init__(self, timeout_seconds: int = 10) -> None:
        self._client = None
        self._timeout_seconds = timeout_seconds

    async def resolve_database_credentials(
        self,
        connection: ConnectionMetadata,
        timeout_ms: int,
    ) -> DatabaseCredentials:
        parsed = parse_secret_ref(connection.secret_ref)
        expected_project = os.getenv("GCP_PROJECT_ID") or os.getenv(
            "GOOGLE_CLOUD_PROJECT"
        )
        if not expected_project:
            raise SecretResolutionError("Secret Manager project is not configured.")
        validate_secret_ref_for_connection(parsed, connection, expected_project)
        timeout_seconds = min(self._timeout_seconds, timeout_ms / 1000)
        try:
            payload = await asyncio.wait_for(
                asyncio.to_thread(
                    self._access_bound_secret_payload,
                    connection,
                    parsed,
                    timeout_seconds,
                ),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            raise SecretResolutionError("Database credential lookup timed out.") from exc

        try:
            decoded = json.loads(payload)
            credentials = DatabaseCredentialsInput.model_validate(decoded)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise SecretResolutionError("Database secret payload is invalid.") from exc

        return DatabaseCredentials(
            password=credentials.password,
        )

    async def resolve_ai_provider_api_key(
        self,
        *,
        binding: AIProviderSecretBinding,
        secret_ref: str,
        timeout_ms: int,
    ) -> str:
        parsed = parse_secret_ref(secret_ref)
        expected_project = os.getenv("GCP_PROJECT_ID") or os.getenv(
            "GOOGLE_CLOUD_PROJECT"
        )
        if not expected_project:
            raise SecretResolutionError("Secret Manager project is not configured.")
        validate_secret_ref_for_ai_provider(parsed, binding, expected_project)
        timeout_seconds = min(self._timeout_seconds, timeout_ms / 1000)
        try:
            payload = await asyncio.wait_for(
                asyncio.to_thread(
                    self._access_bound_ai_secret_payload,
                    binding,
                    parsed,
                    timeout_seconds,
                ),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            raise SecretResolutionError("AI provider credential lookup timed out.") from exc

        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise SecretResolutionError("AI provider secret payload is invalid.") from exc
        api_key = decoded.get("api_key") if isinstance(decoded, dict) else None
        if not isinstance(api_key, str) or not api_key:
            raise SecretResolutionError("AI provider secret payload is invalid.")
        return api_key

    def _access_bound_secret_payload(
        self,
        connection: ConnectionMetadata,
        parsed: ParsedSecretRef,
        timeout_seconds: float,
    ) -> str:
        try:
            from google.cloud import secretmanager
        except ImportError as exc:
            raise SecretResolutionError("Secret Manager client library is not installed.") from exc

        try:
            if self._client is None:
                self._client = secretmanager.SecretManagerServiceClient()
            secret = self._client.get_secret(
                request={
                    "name": f"projects/{parsed.project}/secrets/{parsed.secret}"
                },
                timeout=timeout_seconds,
            )
            labels = dict(secret.labels)
            expected_labels = {
                "atlantebi_binding": secret_binding_fingerprint(connection),
                "atlantebi_connection": connection.connection_id.lower(),
                "atlantebi_tenant": connection.tenant_id.lower(),
            }
            if any(labels.get(key) != value for key, value in expected_labels.items()):
                raise SecretResolutionError(
                    "Database secret endpoint binding is invalid."
                )
            response = self._client.access_secret_version(
                request={"name": parsed.resource_name},
                timeout=timeout_seconds,
            )
            return response.payload.data.decode("utf-8")
        except SecretResolutionError:
            raise
        except Exception as exc:
            raise SecretResolutionError("Unable to access database credentials.") from exc

    def _access_bound_ai_secret_payload(
        self,
        binding: AIProviderSecretBinding,
        parsed: ParsedSecretRef,
        timeout_seconds: float,
    ) -> str:
        try:
            from google.cloud import secretmanager
        except ImportError as exc:
            raise SecretResolutionError("Secret Manager client library is not installed.") from exc

        try:
            if self._client is None:
                self._client = secretmanager.SecretManagerServiceClient()
            secret = self._client.get_secret(
                request={
                    "name": f"projects/{parsed.project}/secrets/{parsed.secret}"
                },
                timeout=timeout_seconds,
            )
            labels = dict(secret.labels)
            expected_labels = {
                "atlantebi_ai_binding": ai_secret_binding_fingerprint(binding),
                "atlantebi_ai_provider": binding.provider.lower(),
                "atlantebi_ai_setting": binding.setting_id.lower(),
                "atlantebi_tenant": binding.tenant_id.lower(),
            }
            if any(labels.get(key) != value for key, value in expected_labels.items()):
                raise SecretResolutionError(
                    "AI provider secret binding is invalid."
                )
            response = self._client.access_secret_version(
                request={"name": parsed.resource_name},
                timeout=timeout_seconds,
            )
            return response.payload.data.decode("utf-8")
        except SecretResolutionError:
            raise
        except Exception as exc:
            raise SecretResolutionError("Unable to access AI provider credentials.") from exc
