FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY document-intelligence/ /app/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

CMD ["sh", "-c", "document_intelligence_runtime_consumer --project-id \"$DI_GCP_PROJECT_ID\" --subscription-name \"${DI_SUBSCRIPTION_NAME:-document-intelligence-artifact-bundle-available}\" --status-topic-name \"${DI_STATUS_TOPIC_NAME:-document-processing-status-updated}\" --processed-topic-name \"${DI_PROCESSED_TOPIC_NAME:-document-processed}\""]
