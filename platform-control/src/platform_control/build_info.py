"""What commit this process was built from.

Production ran 27 commits behind `main` for two days, and before that 35 for six
weeks. Both were discoverable only by asking the cluster which image tag was
running — nothing the software itself said could answer "what is actually
deployed?". This module makes it answerable from `/health`.

The value is the same `github.sha` that `runtime-images.yml` tags the image with,
baked as `EVIDARA_GIT_SHA` at build time, so the version a process reports and the
tag it was pulled by cannot disagree.

**Unset reports `unknown`, never a guess.** A local `docker build`, a `uv run` from
a checkout, or a test process has no build provenance, and inventing one — reading
`git rev-parse` at runtime, say — would report the *developer's* working tree as
the deployed version. That is worse than admitting ignorance, because it looks
like an answer.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel

UNKNOWN = "unknown"


class BuildInfo(BaseModel):
    """Provenance of the running process."""

    git_sha: str
    """Full 40-character commit SHA, or `"unknown"` outside a released image."""

    build_date: str
    """RFC 3339 UTC timestamp of the image build, or `"unknown"`."""

    @property
    def short_sha(self) -> str:
        """First 8 characters, matching how commits are cited in this repo."""
        return self.git_sha[:8] if self.git_sha != UNKNOWN else UNKNOWN


def _clean(value: str | None) -> str:
    """A blank or whitespace-only env var is unset, not a version.

    The Dockerfiles default both ARGs to `""`, so an image built without
    `--build-arg` sets the variable to the empty string rather than leaving it
    absent — `os.environ.get(...)` alone would return `""` and render an empty
    version string in the UI.
    """
    stripped = (value or "").strip()
    return stripped or UNKNOWN


@lru_cache(maxsize=1)
def get_build_info() -> BuildInfo:
    """Build provenance for this process. Cached — env vars cannot change here."""
    return BuildInfo(
        git_sha=_clean(os.environ.get("EVIDARA_GIT_SHA")),
        build_date=_clean(os.environ.get("EVIDARA_BUILD_DATE")),
    )
