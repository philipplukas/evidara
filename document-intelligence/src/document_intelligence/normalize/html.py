"""HTML normalization into the shared intermediate representation."""

from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

from document_intelligence.normalize.ir import Block, NormalizedDocumentIR


class _SimpleHtmlParser(HTMLParser):
    _TEXT_TAGS = {"p", "div", "li", "td", "th", "blockquote", "pre"}
    _HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

    def __init__(self, artifact_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self._artifact_id = artifact_id
        self._skip_depth = 0
        self._current_target: Optional[str] = None
        self._buffer: List[str] = []
        self._blocks: List[Block] = []
        self._title_buffer: List[str] = []
        self._in_title = False
        self._block_order = 0

    @property
    def title(self) -> Optional[str]:
        title = _normalize_whitespace("".join(self._title_buffer))
        return title or None

    @property
    def blocks(self) -> List[Block]:
        return list(self._blocks)

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        lowered_tag = tag.lower()
        if lowered_tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if lowered_tag == "title":
            self._in_title = True
            return
        if lowered_tag in self._HEADING_TAGS or lowered_tag in self._TEXT_TAGS:
            if self._current_target is None:
                self._current_target = lowered_tag
                self._buffer = []

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        lowered_tag = tag.lower()
        if lowered_tag in {"script", "style"} and self._skip_depth:
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
            attrs: Dict[str, Any] = {"tag": tag}
        elif tag == "li":
            block_type = "list_item"
            level = None
            attrs = {"tag": tag}
        else:
            block_type = "paragraph"
            level = None
            attrs = {"tag": tag}
        return Block(
            id="blk_{order:04d}".format(order=self._block_order),
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
        metadata={"title": parser.title, "normalizer": "html_v1"},
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
    return NormalizedDocumentIR(blocks=blocks, metadata={"title": None, "normalizer": "plain_text_v1"})


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
