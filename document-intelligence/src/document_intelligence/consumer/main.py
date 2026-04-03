"""Run the DI runtime ingress service with uvicorn (optional ``[service]`` extra)."""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.environ.get("DOCUMENT_INTELLIGENCE_INGEST_HOST", "0.0.0.0")
    port = int(
        os.environ.get(
            "PORT", os.environ.get("DOCUMENT_INTELLIGENCE_INGEST_PORT", "8091")
        )
    )
    uvicorn.run(
        "document_intelligence.consumer.app:create_app",
        host=host,
        port=port,
        factory=True,
    )


if __name__ == "__main__":
    main()
