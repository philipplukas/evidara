"""Shared structured errors for document-intelligence."""


class ProcessingError(ValueError):
    """Raised when processing cannot continue safely."""

    def __init__(self, code: str, summary: str) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary
