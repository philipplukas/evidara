from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class DependencyCheck(BaseModel):
    status: str
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    service: str
    checks: dict[str, DependencyCheck]
