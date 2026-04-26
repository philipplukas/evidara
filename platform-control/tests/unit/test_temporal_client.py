from __future__ import annotations

from pathlib import Path

from platform_control.config import Settings
from platform_control.temporal.client import build_temporal_tls_config


def test_temporal_tls_config_defaults_to_plaintext() -> None:
    settings = Settings()

    assert build_temporal_tls_config(settings) is False


def test_temporal_tls_config_reads_mounted_certificates(tmp_path: Path) -> None:
    ca = tmp_path / "ca.crt"
    cert = tmp_path / "tls.crt"
    key = tmp_path / "tls.key"
    ca.write_bytes(b"ca")
    cert.write_bytes(b"cert")
    key.write_bytes(b"key")
    settings = Settings(
        temporal_tls_ca_path=ca,
        temporal_tls_cert_path=cert,
        temporal_tls_key_path=key,
        temporal_tls_server_name="temporal.evidare-staging.svc.cluster.local",
    )

    tls = build_temporal_tls_config(settings)

    assert tls is not False
    assert tls.server_root_ca_cert == b"ca"
    assert tls.client_cert == b"cert"
    assert tls.client_private_key == b"key"
    assert tls.domain == "temporal.evidare-staging.svc.cluster.local"
