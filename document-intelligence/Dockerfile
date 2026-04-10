FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY document-intelligence/ /app/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[service]"

CMD ["document_intelligence_runtime_ingress"]
