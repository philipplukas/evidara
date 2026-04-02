"""Shared intermediate representation for normalized documents."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Block:
    id: str
    type: str
    text: str
    order: int
    artifact_id: str
    level: Optional[int] = None
    parent_id: Optional[str] = None
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedDocumentIR:
    blocks: List[Block]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> Optional[str]:
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
            return "{title}\n\n{body}".format(title=title, body=self.body_text).strip()
        return self.body_text
