class DashboardError(Exception):
    """Base class for errors that map directly to an HTTP response."""

    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInputError(DashboardError):
    status_code = 422


class ConfigurationError(DashboardError):
    status_code = 409


class UpstreamError(DashboardError):
    """A subprocess, provider or remote service failed."""

    status_code = 502
