class ExtroError(Exception):
    """Base exception for all extro errors."""


class FirefoxNotFoundError(ExtroError):
    """Raised when Firefox profiles.ini cannot be located on the system."""


class NoProfilesError(ExtroError):
    """Raised when profiles.ini exists but contains no usable profiles."""


class ConfigError(ExtroError):
    """Raised when the application config file cannot be read or written."""
