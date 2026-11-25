"""
Custom exceptions for Copernicus Marine operations.
"""


class CopernicusError(Exception):
    """Base exception for all Copernicus module errors."""
    pass


class DatasetNotFoundError(CopernicusError):
    """Raised when a requested dataset ID is not registered or not found."""
    pass


class InvalidVariableError(CopernicusError):
    """Raised when a requested variable is unsupported or not in the dataset."""
    pass


class InvalidBoundsError(CopernicusError):
    """Raised when spatial, temporal, or depth bounds are invalid or exceed limits."""
    pass


class RetrievalError(CopernicusError):
    """Raised when subsetting or data retrieval fails."""
    pass


class ValidationError(CopernicusError):
    """Raised when data fails verification or validation requirements."""
    pass


class AuthenticationRequiredError(CopernicusError):
    """Raised when operation requires authentication credentials that are missing."""
    pass
