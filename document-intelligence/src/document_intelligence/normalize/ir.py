"""Shared intermediate representation for normalized documents."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Block:
    id: str
    type: str
    text: str
    order: int
    artifact_id: str
    level: int | None = None
    parent_id: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedDocumentIR:
    blocks: list[Block]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str | None:
        value = self.metadata.get("title")
        if value is None:
            return None
        return str(value)

    @property
    def body_text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks if block.text).strip()

    @property
    def full_text(self) -> str:
        title = self.title
        if title and self.body_text and not self.body_text.startswith(title):
            return f"{title}\n\n{self.body_text}".strip()
        return self.body_text
