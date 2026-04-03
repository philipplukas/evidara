"""Optional spaCy-based enrichment helpers."""

from typing import Any, Dict, List


def enrich_with_spacy(
    text: str,
    *,
    enabled: bool,
    model_name: str,
    max_chars_per_section: int,
    batch_size: int,
) -> Dict[str, Any]:
    """Return a small, deterministic enrichment payload for metadata."""
    if not enabled:
        return {
            "enabled": False,
            "backend": "disabled",
            "model_name": model_name,
            "max_chars_per_section": max_chars_per_section,
            "batch_size": batch_size,
            "sentences": [],
            "entities": [],
        }

    try:
        import spacy  # type: ignore
    except ImportError:
        return {
            "enabled": True,
            "backend": "unavailable",
            "model_name": model_name,
            "max_chars_per_section": max_chars_per_section,
            "batch_size": batch_size,
            "sentences": [],
            "entities": [],
        }

    text_window = (text or "")[:max_chars_per_section]
    try:
        nlp = spacy.load(model_name)
        backend = "spacy_model"
    except Exception:
        nlp = spacy.blank("xx")
        backend = "spacy_blank_xx"

    if "sentencizer" not in nlp.pipe_names:
        nlp.add_pipe("sentencizer")
    docs = list(nlp.pipe([text_window], batch_size=batch_size))
    doc = docs[0] if docs else nlp("")
    sentences: List[str] = [span.text.strip() for span in doc.sents if span.text.strip()]
    entities = [
        {"text": ent.text, "label": ent.label_}
        for ent in doc.ents
        if ent.text and ent.label_
    ]
    return {
        "enabled": True,
        "backend": backend,
        "model_name": model_name,
        "max_chars_per_section": max_chars_per_section,
        "batch_size": batch_size,
        "sentences": sentences,
        "entities": entities,
    }
