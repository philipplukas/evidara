FROM python:3.12-slim@sha256:804ddf3251a60bbf9c92e73b7566c40428d54d0e79d3428194edf40da6521286

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY document-intelligence/ /app/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[service]"

CMD ["document_intelligence_runtime_ingress"]
