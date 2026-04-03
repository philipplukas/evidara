"""Run the Document Service with uvicorn (optional ``[service]`` extra)."""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.environ.get("DOCUMENT_SERVICE_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("DOCUMENT_SERVICE_PORT", "8090")))
    uvicorn.run(
        "document_intelligence.service.app:create_app",
        host=host,
        port=port,
        factory=True,
    )


if __name__ == "__main__":
    main()
