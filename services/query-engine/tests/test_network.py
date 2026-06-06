import asyncio
import socket

import pytest

from app.drivers.base import ConnectionMetadata, DriverConfigurationError
from app.models import Engine
from app.network import resolve_database_endpoint


def _connection(**overrides) -> ConnectionMetadata:
    values = {
        "tenant_id": "11111111-1111-4111-8111-111111111111",
        "connection_id": "33333333-3333-4333-8333-333333333333",
        "name": "Network validation",
        "engine": Engine.sqlserver,
        "network_mode": "public_allowlist",
        "host": "sql.example.com",
        "port": 1433,
        "database_name": "demo",
        "username": "readonly_user",
        "secret_ref": "gcp-secret-manager://projects/demo/secrets/customer-db",
        "tls_required": True,
        "trust_server_certificate": False,
        "tls_server_name": None,
    }
    values.update(overrides)
    return ConnectionMetadata(**values)


def test_public_database_endpoint_is_pinned_to_validated_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("8.8.8.8", 1433),
            )
        ],
    )

    endpoint = asyncio.run(resolve_database_endpoint(_connection(), 30000))

    assert endpoint.address == "8.8.8.8"
    assert endpoint.certificate_name == "sql.example.com"


def test_public_database_endpoint_rejects_private_and_mixed_dns_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("8.8.8.8", 1433),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("10.0.0.5", 1433),
            ),
        ],
    )

    with pytest.raises(DriverConfigurationError):
        asyncio.run(resolve_database_endpoint(_connection(), 30000))


def test_private_database_endpoint_requires_vpn_runtime_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("10.0.0.5", 1433),
            )
        ],
    )
    connection = _connection(network_mode="vpn")

    with pytest.raises(DriverConfigurationError):
        asyncio.run(resolve_database_endpoint(connection, 30000))

    monkeypatch.setenv("QUERY_ENGINE_ALLOW_PRIVATE_NETWORKS", "true")
    endpoint = asyncio.run(resolve_database_endpoint(connection, 30000))
    assert endpoint.address == "10.0.0.5"
