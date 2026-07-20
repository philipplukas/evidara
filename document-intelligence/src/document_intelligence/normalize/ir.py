"""Shared intermediate representation for normalized documents."""

from dataclasses import dataclass, field
from typing import Any

# Block types that are apparatus rather than operative text. They are retained as
# blocks — the citations they carry are legally meaningful and a renderer should be
# able to show them — but they are excluded from `body_text`, which is what reaches
# search and the agentic layer. A footnote read as body text is a provision that does
# not exist (#754).
APPARATUS_BLOCK_TYPES = frozenset({"footnote"})


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
        """Operative text only — apparatus (footnotes) is excluded, see APPARATUS_BLOCK_TYPES."""
        return "\n\n".join(
            block.text for block in self.blocks if block.text and block.type not in APPARATUS_BLOCK_TYPES
        ).strip()

    @property
    def full_text(self) -> str:
        title = self.title
        if title and self.body_text and not self.body_text.startswith(title):
            return f"{title}\n\n{self.body_text}".strip()
        return self.body_text
