"""Initial document-intelligence package scaffold."""

from .canonical.models import ProcessingResult
from .ingest.loaders import LocalFilesystemBundleLoader
from .pipeline import ProcessingPipeline

__all__ = ["LocalFilesystemBundleLoader", "ProcessingPipeline", "ProcessingResult"]
