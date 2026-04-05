"""HTML and text normalization into the shared intermediate representation."""

import re
from html.parser import HTMLParser
from typing import Any

from document_intelligence.normalize.ir import Block, NormalizedDocumentIR


class _SimpleHtmlParser(HTMLParser):
    _TEXT_TAGS = {"p", "li", "td", "th", "blockquote", "pre", "article", "section", "main"}
    _HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
    _SKIPPED_TAGS = {"script", "style", "noscript", "template", "svg", "canvas", "nav", "footer", "aside"}

    def __init__(self, artifact_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self._artifact_id = artifact_id
        self._skip_depth = 0
        self._current_target: str | None = None
        self._buffer: list[str] = []
        self._blocks: list[Block] = []
        self._title_buffer: list[str] = []
        self._in_title = False
        self._block_order = 0
        self._html_lang: str | None = None

    @property
    def title(self) -> str | None:
        title = _normalize_whitespace("".join(self._title_buffer))
        return title or None

    @property
    def blocks(self) -> list[Block]:
        return list(self._blocks)

    @property
    def html_lang(self) -> str | None:
        return self._html_lang

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        lowered_tag = tag.lower()
        attrs_map = {str(key).lower(): str(value) for key, value in attrs if key and value}
        if lowered_tag == "html":
            self._html_lang = attrs_map.get("lang", self._html_lang)
        if lowered_tag in self._SKIPPED_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if lowered_tag == "title":
            self._in_title = True
            return
        if lowered_tag == "br" and self._current_target is not None:
            self._buffer.append("\n")
            return
        if lowered_tag in self._HEADING_TAGS or lowered_tag in self._TEXT_TAGS:
            if self._current_target is None:
                self._current_target = lowered_tag
                self._buffer = []

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        lowered_tag = tag.lower()
        if lowered_tag in self._SKIPPED_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if lowered_tag == "title":
            self._in_title = False
            return
        if lowered_tag == self._current_target:
            text = _normalize_whitespace("".join(self._buffer))
            if text:
                self._blocks.append(self._build_block(lowered_tag, text))
                self._block_order += 1
            self._current_target = None
            self._buffer = []

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._skip_depth:
            return
        if self._in_title:
            self._title_buffer.append(data)
            return
        if self._current_target is not None:
            self._buffer.append(data)

    def _build_block(self, tag: str, text: str) -> Block:
        if tag in self._HEADING_TAGS:
            block_type = "heading"
            level = self._HEADING_TAGS[tag]
            attrs: dict[str, Any] = {"tag": tag}
        elif tag == "li":
            block_type = "list_item"
            level = None
            attrs = {"tag": tag}
        else:
            block_type = "paragraph"
            level = None
            attrs = {"tag": tag}
        return Block(
            id=f"blk_{self._block_order:04d}",
            type=block_type,
            text=text,
            level=level,
            order=self._block_order,
            parent_id=None,
            artifact_id=self._artifact_id,
            attrs=attrs,
        )


def normalize_html_document(html_text: str, artifact_id: str) -> NormalizedDocumentIR:
    parser = _SimpleHtmlParser(artifact_id=artifact_id)
    parser.feed(html_text)
    blocks = parser.blocks
    if not blocks:
        text = _normalize_whitespace(_strip_tags_fallback(html_text))
        blocks = (
            [
                Block(
                    id="blk_0000",
                    type="paragraph",
                    text=text,
                    level=None,
                    order=0,
                    parent_id=None,
                    artifact_id=artifact_id,
                    attrs={"fallback": True},
                )
            ]
            if text
            else []
        )
    return NormalizedDocumentIR(
        blocks=blocks,
        metadata={
            "title": parser.title,
            "language": _normalize_language(parser.html_lang),
            "normalizer": "html_v1",
            "source_profile_ref": "default_html_v1",
            "normalization_profile_ref": "html_v1",
            "source_flavor": _detect_html_source_flavor(blocks),
        },
    )


def normalize_markdown_document(markdown_text: str, artifact_id: str) -> NormalizedDocumentIR:
    blocks: list[Block] = []
    title: str | None = None
    order = 0
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            text = _normalize_whitespace(heading_match.group(2))
            if text:
                if title is None and level == 1:
                    title = text
                    continue
                blocks.append(
                    Block(
                        id=f"blk_{order:04d}",
                        type="heading",
                        text=text,
                        level=level,
                        order=order,
                        parent_id=None,
                        artifact_id=artifact_id,
                        attrs={"format": "markdown"},
                    )
                )
                order += 1
            continue
        list_match = re.match(r"^[-*+]\s+(.+)$", line)
        if list_match:
            text = _normalize_whitespace(list_match.group(1))
            if not text:
                continue
            blocks.append(
                Block(
                    id=f"blk_{order:04d}",
                    type="list_item",
                    text=text,
                    level=None,
                    order=order,
                    parent_id=None,
                    artifact_id=artifact_id,
                    attrs={"format": "markdown"},
                )
            )
            order += 1
            continue
        blocks.append(
            Block(
                id=f"blk_{order:04d}",
                type="paragraph",
                text=_normalize_whitespace(line),
                level=None,
                order=order,
                parent_id=None,
                artifact_id=artifact_id,
                attrs={"format": "markdown"},
            )
        )
        order += 1

    return NormalizedDocumentIR(
        blocks=blocks,
        metadata={
            "title": title,
            "normalizer": "markdown_v1",
            "source_profile_ref": "default_markdown_v1",
            "normalization_profile_ref": "markdown_v1",
            "source_flavor": "markdown_like",
        },
    )


def normalize_plain_text_document(text: str, artifact_id: str) -> NormalizedDocumentIR:
    normalized = "\n".join(line.rstrip() for line in text.splitlines())
    body = _normalize_whitespace(normalized)
    blocks = []
    if body:
        blocks.append(
            Block(
                id="blk_0000",
                type="paragraph",
                text=body,
                level=None,
                order=0,
                parent_id=None,
                artifact_id=artifact_id,
                attrs={"normalizer": "plain_text_v1"},
            )
        )
    return NormalizedDocumentIR(
        blocks=blocks,
        metadata={
            "title": None,
            "normalizer": "plain_text_v1",
            "source_profile_ref": "default_plain_text_v1",
            "normalization_profile_ref": "plain_text_v1",
            "source_flavor": "plain_text",
        },
    )


def _detect_html_source_flavor(blocks: list[Block]) -> str:
    heading_count = sum(1 for block in blocks if block.type == "heading")
    legal_markers = ("art.", "§", "gesetz", "arrêt", "urteil", "rechtssatz", "verordnung")
    has_legal_marker = any(marker in block.text.lower() for block in blocks for marker in legal_markers)
    if heading_count >= 2 and has_legal_marker:
        return "legal_html"
    if heading_count >= 2:
        return "structured_html"
    return "generic_html"


def _normalize_language(value: str | None) -> str | None:
    if not value:
        return None
    primary = value.split("-", 1)[0].strip().lower()
    return primary or None


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _strip_tags_fallback(value: str) -> str:
    output = []
    inside_tag = False
    for char in value:
        if char == "<":
            inside_tag = True
        elif char == ">":
            inside_tag = False
        elif not inside_tag:
            output.append(char)
    return "".join(output)
