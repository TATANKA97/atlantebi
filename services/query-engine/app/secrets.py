import asyncio
import json
import re
from dataclasses import dataclass

from pydantic import ValidationError

from app.drivers.base import DatabaseCredentials
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


def parse_secret_ref(secret_ref: str) -> ParsedSecretRef:
    match = SECRET_REF_PATTERN.fullmatch(secret_ref)
    if match is None:
        raise SecretResolutionError("Invalid Secret Manager reference.")

    return ParsedSecretRef(
        project=match.group("project"),
        secret=match.group("secret"),
        version=match.group("version") or "latest",
    )


class GcpSecretResolver:
    async def resolve_database_credentials(self, secret_ref: str) -> DatabaseCredentials:
        parsed = parse_secret_ref(secret_ref)
        payload = await asyncio.to_thread(self._access_secret_payload, parsed.resource_name)

        try:
            decoded = json.loads(payload)
            credentials = DatabaseCredentialsInput.model_validate(decoded)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise SecretResolutionError("Database secret payload is invalid.") from exc

        return DatabaseCredentials(
            password=credentials.password,
        )

    def _access_secret_payload(self, resource_name: str) -> str:
        try:
            from google.cloud import secretmanager
        except ImportError as exc:
            raise SecretResolutionError("Secret Manager client library is not installed.") from exc

        try:
            client = secretmanager.SecretManagerServiceClient()
            response = client.access_secret_version(request={"name": resource_name})
            return response.payload.data.decode("utf-8")
        except Exception as exc:
            raise SecretResolutionError("Unable to access database credentials.") from exc
