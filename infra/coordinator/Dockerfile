FROM python:3.12-slim@sha256:804ddf3251a60bbf9c92e73b7566c40428d54d0e79d3428194edf40da6521286

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

COPY human-gates.yaml .

EXPOSE 8080

CMD ["uvicorn", "coordinator.app:app", "--host", "0.0.0.0", "--port", "8080"]
