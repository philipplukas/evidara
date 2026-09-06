FROM python:3.12-slim@sha256:804ddf3251a60bbf9c92e73b7566c40428d54d0e79d3428194edf40da6521286

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY platform-control/ /app/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .


# Build provenance (ADR-0055 follow-up). `GIT_SHA` is the same value the image is
# tagged with in `runtime-images.yml`, so the version the app reports and the tag
# it was pulled by cannot disagree. Unset in a local build — the app then reports
# "unknown" rather than inventing a version.
ARG GIT_SHA=""
ARG BUILD_DATE=""
ENV EVIDARA_GIT_SHA=$GIT_SHA \
    EVIDARA_BUILD_DATE=$BUILD_DATE

EXPOSE 8080

CMD ["uvicorn", "platform_control.main:app", "--host", "0.0.0.0", "--port", "8080"]
