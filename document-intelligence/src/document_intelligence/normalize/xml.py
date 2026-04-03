"""XML normalization into the shared intermediate representation."""

from xml.etree import ElementTree

from document_intelligence.errors import ProcessingError
from document_intelligence.normalize.ir import Block, NormalizedDocumentIR

_TITLE_TAGS = {
    "langtitel",
    "kurztitel",
    "titel",
    "title",
    "ueberschrift",
    "heading",
}
_STRUCTURAL_LEVELS = {
    "teil": 1,
    "part": 1,
    "hauptstueck": 1,
    "hauptstuck": 1,
    "kapitel": 2,
    "chapter": 2,
    "abschnitt": 2,
    "unterabschnitt": 3,
    "subsection": 3,
    "paragraf": 4,
    "paragraph": 4,
    "section": 4,
    "artikel": 4,
    "article": 4,
    "anlage": 4,
    "annex": 4,
}
_TEXT_TAGS = {
    "absatz",
    "paragraphtext",
    "text",
    "normtext",
    "inhalt",
    "content",
    "p",
    "satz",
    "einleitung",
    "praeambel",
    "preamble",
}
_LIST_ITEM_TAGS = {"ziffer", "litera", "listitem", "item", "punkt"}
_METADATA_TAGS = {
    "dokumentnummer": "dokumentnummer",
    "risdokumentnummer": "dokumentnummer",
    "gesetzesnummer": "gesetzesnummer",
    "kundmachungsorgan": "kundmachungsorgan",
    "abkuerzung": "abkuerzung",
    "abkuerzunglang": "abkuerzung_lang",
    "eli": "eli",
    "typ": "document_type",
    "dokumenttyp": "document_type",
}
_SKIPPED_CONTAINER_TAGS = {
    "metadata",
    "metadaten",
    "header",
    "kopf",
    "stammdaten",
}


def normalize_xml_document(xml_text: str, artifact_id: str) -> NormalizedDocumentIR:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as error:
        raise ProcessingError(
            "invalid_xml",
            "primary XML artifact could not be parsed",
        ) from error

    builder = _XmlIrBuilder(artifact_id=artifact_id)
    builder.visit(root)
    blocks = builder.blocks
    if not blocks:
        fallback_text = _normalize_whitespace(" ".join(root.itertext()))
        if fallback_text:
            blocks = [
                Block(
                    id="blk_0000",
                    type="paragraph",
                    text=fallback_text,
                    level=None,
                    order=0,
                    parent_id=None,
                    artifact_id=artifact_id,
                    attrs={"fallback": True, "tag": _local_name(root.tag)},
                )
            ]

    extracted_metadata = _extract_metadata(root)
    title = _choose_title(root, blocks)
    metadata = {
        "title": title,
        "normalizer": "xml_v1",
        "source_profile_ref": "default_xml_v1",
        "normalization_profile_ref": "xml_v1",
        "source_flavor": "ris_like" if _looks_like_ris(root, extracted_metadata) else "generic_xml",
        "root_tag": _local_name(root.tag),
        "extracted_metadata": extracted_metadata,
    }
    if extracted_metadata.get("document_type"):
        metadata["document_type"] = extracted_metadata["document_type"]

    return NormalizedDocumentIR(blocks=blocks, metadata=metadata)


class _XmlIrBuilder:
    def __init__(self, artifact_id: str) -> None:
        self._artifact_id = artifact_id
        self._blocks = []
        self._order = 0

    @property
    def blocks(self):
        return list(self._blocks)

    def visit(self, element, parent_heading_id=None) -> None:
        tag = _local_name(element.tag)

        if tag in _SKIPPED_CONTAINER_TAGS:
            return

        if tag in _STRUCTURAL_LEVELS:
            heading_block_id = self._emit_structural_heading(element, tag, parent_heading_id)
            next_parent_id = heading_block_id or parent_heading_id
            for child in list(element):
                child_tag = _local_name(child.tag)
                if child_tag in _TITLE_TAGS or child_tag in {
                    "nummer",
                    "nr",
                    "label",
                    "bezeichnung",
                }:
                    continue
                self.visit(child, next_parent_id)
            return

        if tag in _TEXT_TAGS or tag in _LIST_ITEM_TAGS:
            if _should_recurse_text_container(element, tag):
                for child in list(element):
                    self.visit(child, parent_heading_id)
                return
            self._emit_text_block(element, tag, parent_heading_id)
            return

        for child in list(element):
            self.visit(child, parent_heading_id)

    def _emit_structural_heading(self, element, tag: str, parent_heading_id):
        official_label = _derive_official_label(element, tag)
        heading_text = _extract_heading_text(element)
        heading_display = _compose_heading_display(official_label, heading_text)
        if not heading_display:
            return None

        block_id = self._next_block_id()
        self._blocks.append(
            Block(
                id=block_id,
                type="heading",
                text=heading_display,
                level=_STRUCTURAL_LEVELS[tag],
                order=self._order,
                parent_id=parent_heading_id,
                artifact_id=self._artifact_id,
                attrs={
                    "tag": tag,
                    "official_label": official_label,
                    "heading_text": heading_text,
                },
            )
        )
        self._order += 1
        return block_id

    def _emit_text_block(self, element, tag: str, parent_heading_id) -> None:
        text = _normalize_whitespace(" ".join(element.itertext()))
        if not text:
            return

        official_label = _derive_official_label(element, tag)
        rendered_text = _compose_inline_text(official_label, text)
        block_type = "list_item" if tag in _LIST_ITEM_TAGS else "paragraph"
        block_id = self._next_block_id()
        self._blocks.append(
            Block(
                id=block_id,
                type=block_type,
                text=rendered_text,
                level=None,
                order=self._order,
                parent_id=parent_heading_id,
                artifact_id=self._artifact_id,
                attrs={
                    "tag": tag,
                    "official_label": official_label,
                },
            )
        )
        self._order += 1

    def _next_block_id(self) -> str:
        return f"blk_{self._order:04d}"


def _choose_title(root, blocks) -> str | None:
    for candidate_tag in ("langtitel", "kurztitel", "titel", "title"):
        for element in root.iter():
            if _local_name(element.tag) != candidate_tag:
                continue
            text = _normalize_whitespace(" ".join(element.itertext()))
            if text:
                return text
    for block in blocks:
        if block.type == "heading":
            return block.text
    return None


def _extract_metadata(root) -> dict[str, str]:
    output: dict[str, str] = {}
    language = root.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") or root.attrib.get("lang")
    if language:
        output["language"] = language
    output["root_tag"] = _local_name(root.tag)

    for element in root.iter():
        tag = _local_name(element.tag)
        key = _METADATA_TAGS.get(tag)
        if key is None or key in output:
            continue
        text = _normalize_whitespace(" ".join(element.itertext()))
        if text:
            output[key] = text
    return output


def _looks_like_ris(root, extracted_metadata: dict[str, str]) -> bool:
    if "dokumentnummer" in extracted_metadata or "gesetzesnummer" in extracted_metadata:
        return True
    observed_tags = {_local_name(element.tag) for element in root.iter()}
    return bool(observed_tags & {"paragraf", "absatz", "artikel", "anlage", "kundmachungsorgan"})


def _extract_heading_text(element) -> str | None:
    for child in list(element):
        if _local_name(child.tag) not in _TITLE_TAGS:
            continue
        text = _normalize_whitespace(" ".join(child.itertext()))
        if text:
            return text
    return None


def _derive_official_label(element, tag: str) -> str | None:
    raw = _raw_label_value(element)
    if not raw:
        return None
    if tag == "paragraf":
        return f"§ {raw}"
    if tag in {"artikel", "article"}:
        return f"Art. {raw}"
    if tag in {"anlage", "annex"}:
        return f"Anlage {raw}"
    if tag in {"teil", "part"}:
        return f"Teil {raw}"
    if tag == "abschnitt":
        return f"Abschnitt {raw}"
    if tag in {"kapitel", "chapter"}:
        return f"Kapitel {raw}"
    return raw


def _raw_label_value(element) -> str | None:
    for key in ("nummer", "nr", "number", "label", "bezeichnung"):
        if key in element.attrib:
            value = _normalize_whitespace(str(element.attrib[key]))
            if value:
                return value
    for child in list(element):
        if _local_name(child.tag) not in {"nummer", "nr", "label", "bezeichnung"}:
            continue
        value = _normalize_whitespace(" ".join(child.itertext()))
        if value:
            return value
    return None


def _compose_heading_display(official_label: str | None, heading_text: str | None) -> str | None:
    if official_label and heading_text:
        if heading_text.startswith(official_label):
            return heading_text
        return f"{official_label} {heading_text}"
    return heading_text or official_label


def _compose_inline_text(official_label: str | None, text: str) -> str:
    if official_label and not text.startswith(official_label):
        return f"{official_label} {text}"
    return text


def _should_recurse_text_container(element, tag: str) -> bool:
    if tag not in {"text", "content", "inhalt", "normtext"}:
        return False
    child_tags = {_local_name(child.tag) for child in list(element)}
    return bool(child_tags)


def _local_name(tag) -> str:
    if not isinstance(tag, str):
        return ""
    local = tag.rsplit("}", 1)[-1]
    return local.replace("-", "_").lower()


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())
