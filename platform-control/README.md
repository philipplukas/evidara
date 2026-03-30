# Platform Control

FastAPI service for source lifecycle, run orchestration, approvals, and raw artifact control-plane workflows in Evidara.

## Local development

```bash
uv sync --group dev
uv run uvicorn platform_control.main:app --reload --app-dir src
```

Local configuration starts from `.env.example`. Keep real secrets out of Git.

## Checks

```bash
../scripts/check-platform-control.sh
```
