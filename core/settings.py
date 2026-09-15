from PyQt6.QtCore import QSettings

ORGANIZATION_NAME = "MorpheusNZ"
APPLICATION_NAME = "WikidataBatchUploader"

# Settings keys
EDIT_SUMMARY_KEY = "upload/edit_summary"
UPLOAD_DELAY_KEY = "upload/delay_seconds"
MAXLAG_KEY = "upload/maxlag_seconds"
AI_ENDPOINT_URL_KEY = "ai/endpoint_url"
AI_API_KEY_KEY = "ai/api_key"

DEFAULT_EDIT_SUMMARY = "Batch upload from Wikidata Batch Uploader"
DEFAULT_UPLOAD_DELAY_SECONDS = 1.0
DEFAULT_MAXLAG_SECONDS = 5.0
DEFAULT_AI_ENDPOINT_URL = ""
DEFAULT_AI_API_KEY = ""

_settings = None


def _get_settings() -> QSettings:
    global _settings
    if _settings is None:
        _settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
    return _settings


def get_default_edit_summary() -> str:
    """Return the saved default edit summary, falling back to the built-in default."""
    return str(_get_settings().value(EDIT_SUMMARY_KEY, DEFAULT_EDIT_SUMMARY))


def set_default_edit_summary(summary: str) -> None:
    """Save a new default edit summary."""
    _get_settings().setValue(EDIT_SUMMARY_KEY, summary)


def get_upload_delay_seconds() -> float:
    """Return the saved upload delay in seconds, coerced to a non-negative float."""
    try:
        value = float(_get_settings().value(UPLOAD_DELAY_KEY, DEFAULT_UPLOAD_DELAY_SECONDS))
    except (TypeError, ValueError):
        value = DEFAULT_UPLOAD_DELAY_SECONDS
    return max(0.0, value)


def set_upload_delay_seconds(delay_seconds: float) -> None:
    """Save a new upload delay in seconds. Negative values are clamped to zero."""
    delay_seconds = max(0.0, float(delay_seconds))
    _get_settings().setValue(UPLOAD_DELAY_KEY, delay_seconds)


def get_maxlag_seconds() -> float:
    """Return the saved maxlag value in seconds, coerced to a non-negative float."""
    try:
        value = float(_get_settings().value(MAXLAG_KEY, DEFAULT_MAXLAG_SECONDS))
    except (TypeError, ValueError):
        value = DEFAULT_MAXLAG_SECONDS
    return max(0.0, value)


def set_maxlag_seconds(maxlag_seconds: float) -> None:
    """Save a new maxlag value in seconds. Negative values are clamped to zero."""
    maxlag_seconds = max(0.0, float(maxlag_seconds))
    _get_settings().setValue(MAXLAG_KEY, maxlag_seconds)


def get_ai_endpoint_url() -> str:
    """Return the saved AI endpoint URL, or empty string if not configured."""
    return str(_get_settings().value(AI_ENDPOINT_URL_KEY, DEFAULT_AI_ENDPOINT_URL))


def set_ai_endpoint_url(url: str) -> None:
    """Save a new AI endpoint URL."""
    _get_settings().setValue(AI_ENDPOINT_URL_KEY, url.strip())


def get_ai_api_key() -> str:
    """Return the saved AI API key, or empty string if not configured."""
    return str(_get_settings().value(AI_API_KEY_KEY, DEFAULT_AI_API_KEY))


def set_ai_api_key(api_key: str) -> None:
    """Save a new AI API key."""
    _get_settings().setValue(AI_API_KEY_KEY, api_key)
