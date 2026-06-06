import asyncio
import ipaddress
import os
import socket
from dataclasses import dataclass

from app.drivers.base import ConnectionMetadata, DriverConfigurationError


@dataclass(frozen=True)
class ResolvedDatabaseEndpoint:
    address: str
    certificate_name: str | None


async def resolve_database_endpoint(
    connection: ConnectionMetadata,
    timeout_ms: int,
) -> ResolvedDatabaseEndpoint:
    timeout_seconds = max(1.0, min(timeout_ms / 1000, 10.0))
    try:
        addresses = await asyncio.wait_for(
            asyncio.to_thread(
                _resolve_addresses,
                connection.host,
                connection.port,
            ),
            timeout=timeout_seconds,
        )
    except (TimeoutError, OSError) as exc:
        raise DriverConfigurationError(
            "Database destination could not be resolved."
        ) from exc

    allow_private = (
        connection.network_mode == "vpn"
        and os.getenv("QUERY_ENGINE_ALLOW_PRIVATE_NETWORKS") == "true"
    )
    parsed_addresses = [ipaddress.ip_address(address) for address in addresses]
    if not allow_private and any(not address.is_global for address in parsed_addresses):
        raise DriverConfigurationError(
            "Database destination is outside the allowed public network range."
        )
    if connection.network_mode == "vpn" and not allow_private:
        raise DriverConfigurationError(
            "Private database networking is not enabled for this runtime."
        )

    certificate_name = connection.tls_server_name
    if (
        connection.tls_required
        and certificate_name is None
        and _is_hostname(connection.host)
    ):
        certificate_name = connection.host.rstrip(".")

    return ResolvedDatabaseEndpoint(
        address=str(parsed_addresses[0]),
        certificate_name=certificate_name,
    )


def _resolve_addresses(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(
        host,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
    )
    addresses = sorted({str(info[4][0]) for info in infos})
    if not addresses:
        raise OSError("Database destination has no addresses.")
    return addresses


def _is_hostname(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return True
    return False
