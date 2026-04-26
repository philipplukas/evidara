from __future__ import annotations

from pathlib import Path

from temporalio.client import Client
from temporalio.service import TLSConfig

from platform_control.config import Settings


def _read_optional(path: Path | None) -> bytes | None:
    if path is None:
        return None
    return path.read_bytes()


def build_temporal_tls_config(settings: Settings) -> TLSConfig | bool:
    """Build Temporal client TLS config from settings.

    Temporal's Python SDK accepts ``False`` for plaintext, ``True`` for default TLS,
    or a ``TLSConfig`` for custom roots/client certs. The Hetzner staging Temporal
    frontend requires mTLS, so platform-control needs to pass the mounted client
    certificate when those paths are configured.
    """

    if (
        settings.temporal_tls_ca_path is None
        and settings.temporal_tls_cert_path is None
        and settings.temporal_tls_key_path is None
        and settings.temporal_tls_server_name is None
    ):
        return False

    return TLSConfig(
        server_root_ca_cert=_read_optional(settings.temporal_tls_ca_path),
        domain=settings.temporal_tls_server_name,
        client_cert=_read_optional(settings.temporal_tls_cert_path),
        client_private_key=_read_optional(settings.temporal_tls_key_path),
    )


async def connect_temporal(
    settings: Settings,
    *,
    target: str | None = None,
    namespace: str | None = None,
) -> Client:
    return await Client.connect(
        target or settings.temporal_target,
        namespace=namespace or settings.temporal_namespace,
        tls=build_temporal_tls_config(settings),
    )
