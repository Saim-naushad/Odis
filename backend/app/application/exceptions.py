"""Application-layer exceptions for platform services."""


class ObservationAlreadyExistsError(Exception):
    """Raised when persisting an observation with a duplicate identifier."""


class ObservationNotFoundError(Exception):
    """Raised when a requested observation does not exist."""
