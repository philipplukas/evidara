"""Section extraction from the shared intermediate representation."""

from dataclasses import dataclass, field
from typing import Any

from document_intelligence.normalize.ir import NormalizedDocumentIR


@dataclass(frozen=True)
class SectionCandidate:
    title: str | None
    content: str
    depth: int = 0
    section_type: str | None = "section"
    metadata: dict[str, Any] = field(default_factory=dict)


def build_sections_from_ir(document_ir: NormalizedDocumentIR) -> list[SectionCandidate]:
    sections: list[SectionCandidate] = []
    preamble_parts: list[str] = []
    current: dict[str, Any] | None = None
    # Enclosing headings, outermost first — e.g. an article under "Titel 2 > 1. Kapitel".
    # Tracked across *all* headings (including structural ones that end up with no direct
    # content and are dropped below) so a provision keeps its place in the norm hierarchy.
    ancestry: list[dict[str, Any]] = []

    for block in document_ir.blocks:
        if block.type == "heading":
            if current is not None:
                sections.append(_finalize_section(current))
            depth = max(0, (block.level or 1) - 1)
            while ancestry and ancestry[-1]["depth"] >= depth:
                ancestry.pop()
            metadata: dict[str, Any] = {
                "heading_level": block.level,
                "block_id": block.id,
                **dict(block.attrs),
            }
            if ancestry:
                metadata["ancestor_titles"] = [entry["title"] for entry in ancestry]
                metadata["parent_title"] = ancestry[-1]["title"]
                parent_anchor = ancestry[-1]["anchor"]
                if parent_anchor:
                    metadata["parent_anchor"] = parent_anchor
            current = {
                "title": block.text,
                "content_parts": [],
                "depth": depth,
                "section_type": "heading",
                "metadata": metadata,
            }
            ancestry.append({"title": block.text, "depth": depth, "anchor": block.attrs.get("anchor")})
            continue

        if current is None:
            preamble_parts.append(block.text)
        else:
            current["content_parts"].append(block.text)

    if current is not None:
        sections.append(_finalize_section(current))

    if not sections:
        body_text = document_ir.body_text
        if not body_text:
            return []
        return [
            SectionCandidate(
                title=document_ir.title or "Body",
                content=body_text,
                depth=0,
                section_type="body",
                metadata={},
            )
        ]

    preamble = "\n\n".join(part for part in preamble_parts if part).strip()
    if preamble:
        first_section = sections[0]
        sections[0] = SectionCandidate(
            title=first_section.title,
            content=f"{preamble}\n\n{first_section.content}".strip(),
            depth=first_section.depth,
            section_type=first_section.section_type,
            metadata=first_section.metadata,
        )

    return [s for s in sections if s.content.strip()]


def _finalize_section(raw_section: dict[str, Any]) -> SectionCandidate:
    return SectionCandidate(
        title=raw_section["title"],
        content="\n\n".join(part for part in raw_section["content_parts"] if part).strip(),
        depth=raw_section["depth"],
        section_type=raw_section["section_type"],
        metadata=dict(raw_section["metadata"]),
    )
