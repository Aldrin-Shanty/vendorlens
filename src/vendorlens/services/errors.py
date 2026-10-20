class SupplierSelectionError(ValueError):
    """The requested supplier selection is invalid."""


class EvidenceValidationError(ValueError):
    """Extracted facts have invalid evidence references."""


class AIOutputError(Exception):
    """The AI provider returned an unusable response."""


class AIServiceUnavailableError(Exception):
    """The AI provider could not be reached."""


class WorkflowNotFoundError(LookupError):
    """The workflow does not exist within the requested event."""
