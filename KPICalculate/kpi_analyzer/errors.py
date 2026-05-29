class KPIAnalyzerError(Exception):
    """Base exception for expected analyzer failures."""


class InputValidationError(KPIAnalyzerError):
    """Raised when input data is structurally invalid."""


class LLMError(KPIAnalyzerError):
    """Raised when an LLM request fails."""


class ParseError(KPIAnalyzerError):
    """Raised when model output cannot be parsed."""

