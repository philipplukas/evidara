---
name: ci-image-builds-non-required
description: Docker image-build checks are non-required, so auto-merge fires before they finish
metadata:
  type: project
---

On evidara, the Docker **image-build** checks ("Build legal-search frontend image", "Build platform-control admin image", "Runtime Images") are **not required** for merge. The required gates are the per-surface `check`/`frontend`/typecheck jobs. Consequently `gh pr merge --squash --auto` fires as soon as the required checks are green — often **before** the slow image builds complete or even if they fail.

**Why:** This means a broken image build can land on `main` (e.g. #547 introduced the first production `@evidara/shell` import without the Dockerfiles copying `styles/shell`, and merged anyway — main's image builds went red).

**How to apply:** (1) If you push a follow-up fix *after* arming auto-merge, it can miss the merge — the PR auto-merges at the pre-fix head (this happened on #548 → the fix had to go out as separate PR #599). Verify the merged head sha includes your latest commit. (2) When touching shared modules under `styles/` (`tokens`, `ui`, `shell`), remember both `legal-search/frontend/Dockerfile` and `platform-control/admin/Dockerfile` must `COPY` the dir explicitly — local `npm run build` passes via the tsconfig path alias but the Docker build only sees what's COPY'd. Build the image locally to verify, don't trust local `npm run build`.
