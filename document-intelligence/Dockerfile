FROM python:3.12-slim@sha256:804ddf3251a60bbf9c92e73b7566c40428d54d0e79d3428194edf40da6521286

# uv, pinned by digest, is here to install from `uv.lock` (#848). `pip install ".[service]"`
# resolved `pyproject.toml`'s floors against PyPI **at build time** and ignored the lock
# entirely, so the image shipped `deltalake` 1.6.3 / `pyarrow` 25.0.1 while the documented
# gate ran 1.5.0 / 23.0.1 — and two images built a week apart were not the same software.
# `uv sync --frozen` also fails the build outright when `uv.lock` and `pyproject.toml`
# disagree, which is the drift guard: it asks nobody to remember anything.
COPY --from=ghcr.io/astral-sh/uv@sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY document-intelligence/ /app/

RUN uv sync --frozen --no-dev --no-editable --extra service

CMD ["document_intelligence_runtime_ingress"]
