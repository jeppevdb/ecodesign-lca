class ValidationError(ValueError):
    """An input was rejected by an instant check.

    ``field`` names the offending field so the interface can mark it.
    """

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


class NotFoundError(LookupError):
    """A referenced record does not exist in the project."""
