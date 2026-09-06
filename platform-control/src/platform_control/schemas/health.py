from pydantic import BaseModel

from platform_control.build_info import BuildInfo


class HealthResponse(BaseModel):
    status: str
    service: str
    # Which commit this process was built from. `unknown` outside a released
    # image — see `platform_control.build_info`.
    build: BuildInfo


class DependencyCheck(BaseModel):
    status: str
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    service: str
    checks: dict[str, DependencyCheck]
