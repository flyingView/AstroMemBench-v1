"""Task-level memory evaluation with native agent lifecycle interventions."""

__version__ = "1.0.0"
PROTOCOL_VERSION = "astromembench/2"


def accepts_identifier(value, current):
    """Read records made before the project rename without rewriting evidence."""
    legacy = current.replace("astromembench", "astromem", 1)
    return isinstance(value, str) and value in (current, legacy)
