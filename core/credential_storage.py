import os
import json
import logging
from typing import Optional, Dict

from config import BASE_DIR

# Try to use keyring; if it's not available (e.g., dependency missing),
# fall back to a local file with restricted permissions.
try:
    import keyring
except ImportError:  # pragma: no cover - keyring is a required dependency
    keyring = None

logger = logging.getLogger(__name__)

SERVICE_NAME = "WikiDataBatchUploader"
CREDENTIAL_KEY = "credentials"
MORPHEUS_TOKEN_KEY = "morpheus_token"

# OAuth credential keys stored individually in the keyring
OAUTH_KEYS = ['consumer_key', 'consumer_secret', 'access_token', 'access_secret']

# Fallback file paths (used only if keyring is unavailable or fails)
CREDENTIAL_FILE = BASE_DIR / 'credentials.dat'
OAUTH_FILE = BASE_DIR / 'oauth_credentials.dat'
MORPHEUS_TOKEN_FILE = BASE_DIR / 'morpheus_token.dat'


def _file_save(path, data: str) -> bool:
    """Fallback: store data in a local file with 0600 permissions."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(data)
        os.chmod(path, 0o600)
        return True
    except Exception:
        return False


def _file_load(path) -> Optional[str]:
    """Fallback: read data from a local file (if it exists)."""
    if not path.exists():
        return None
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return None


def _file_delete(path) -> None:
    """Fallback: delete a local file, ignoring errors."""
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def _keyring_set(service: str, key: str, value: str) -> bool:
    """Set a password in keyring. Returns True on success, False on any error."""
    if keyring is None:
        return False
    try:
        keyring.set_password(service, key, value)
        return True
    except Exception:
        logger.warning("Keyring backend unavailable; using local file fallback.")
        return False


def _keyring_get(service: str, key: str) -> Optional[str]:
    """Get a password from keyring. Returns None if not found or on error."""
    if keyring is None:
        return None
    try:
        return keyring.get_password(service, key)
    except Exception:
        logger.warning("Keyring backend unavailable; using local file fallback.")
        return None


def _keyring_delete(service: str, key: str) -> None:
    """Delete a password from keyring, ignoring errors."""
    if keyring is None:
        return
    try:
        keyring.delete_password(service, key)
    except Exception:
        pass


def save_credentials(credentials: Dict[str, str]) -> bool:
    """Save Wikidata login credentials.

    Uses the OS keyring (Windows Credential Locker, macOS Keychain, Linux
    Secret Service) when available, falling back to a local file with
    restricted permissions if no keyring backend is found.

    Args:
        credentials: Dictionary containing credential fields, including
            'type' ('bot' or 'oauth') and the corresponding values.

    Returns:
        True if saved successfully, False otherwise.
    """
    try:
        json_data = json.dumps(credentials)
    except (TypeError, ValueError):
        return False

    # Try keyring first
    if _keyring_set(SERVICE_NAME, CREDENTIAL_KEY, json_data):
        return True

    # Fallback to file
    if _file_save(CREDENTIAL_FILE, json_data):
        logger.warning("Using local file fallback for credential storage.")
        return True
    return False


def load_credentials() -> Optional[Dict[str, str]]:
    """Load saved Wikidata login credentials.

    Returns:
        Dictionary of credentials if available and readable, otherwise None.
    """
    # Try keyring first
    data = _keyring_get(SERVICE_NAME, CREDENTIAL_KEY)
    if data is not None:
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None

    # Fallback to file
    data = _file_load(CREDENTIAL_FILE)
    if data is not None:
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None
    return None


def delete_credentials() -> None:
    """Delete saved Wikidata login credentials from keyring and fallback file.

    Best-effort; never raises. If no credentials are stored, this is a no-op.
    """
    _keyring_delete(SERVICE_NAME, CREDENTIAL_KEY)
    _file_delete(CREDENTIAL_FILE)


def save_oauth_credentials(consumer_key: str, consumer_secret: str, access_token: str, access_secret: str) -> bool:
    """Save Wikidata OAuth 1.0a credentials as separate keyring entries.

    Uses the OS keyring when possible; otherwise falls back to a local
    restricted-permission file containing all four tokens.

    Returns:
        True if saved successfully, False otherwise.
    """
    creds = {
        'consumer_key': consumer_key,
        'consumer_secret': consumer_secret,
        'access_token': access_token,
        'access_secret': access_secret,
    }

    # Try keyring first, storing each token under its own key
    success = True
    for field in OAUTH_KEYS:
        key_name = f'oauth_{field}'
        if not _keyring_set(SERVICE_NAME, key_name, creds[field]):
            success = False
            break
    if success:
        return True

    # Fallback to file
    try:
        json_data = json.dumps(creds)
    except (TypeError, ValueError):
        return False

    if _file_save(OAUTH_FILE, json_data):
        # Clean up any partial keyring entries to avoid inconsistency
        for field in OAUTH_KEYS:
            _keyring_delete(SERVICE_NAME, f'oauth_{field}')
        logger.warning("Using local file fallback for OAuth credential storage.")
        return True
    return False


def load_oauth_credentials() -> Optional[Dict[str, str]]:
    """Load saved Wikidata OAuth 1.0a credentials.

    Returns:
        Dictionary with keys 'consumer_key', 'consumer_secret', 'access_token',
        'access_secret' if all four values are available, otherwise None.
    """
    creds = {}

    # Try keyring first
    missing = False
    for field in OAUTH_KEYS:
        val = _keyring_get(SERVICE_NAME, f'oauth_{field}')
        if val is None:
            missing = True
            break
        creds[field] = val

    if not missing and len(creds) == 4:
        return creds

    # Fallback to file
    data = _file_load(OAUTH_FILE)
    if data is not None:
        try:
            data_dict = json.loads(data)
            if all(field in data_dict for field in OAUTH_KEYS):
                return data_dict
        except json.JSONDecodeError:
            pass
    return None


def delete_oauth_credentials() -> None:
    """Delete saved OAuth credentials from keyring and fallback file.

    Best-effort; never raises.
    """
    for field in OAUTH_KEYS:
        _keyring_delete(SERVICE_NAME, f'oauth_{field}')
    _file_delete(OAUTH_FILE)


def save_morpheus_token(token: str) -> bool:
    """Save a Morpheus Connect device token (dvc_...) securely."""
    # Try keyring first
    if _keyring_set(SERVICE_NAME, MORPHEUS_TOKEN_KEY, token):
        return True

    # Fallback to file
    if _file_save(MORPHEUS_TOKEN_FILE, token):
        logger.warning("Using local file fallback for Morpheus token storage.")
        return True
    return False


def load_morpheus_token() -> Optional[str]:
    """Load the saved Morpheus Connect device token.

    Returns the token string if available, otherwise None.
    """
    # Try keyring first
    data = _keyring_get(SERVICE_NAME, MORPHEUS_TOKEN_KEY)
    if data is not None:
        return data

    # Fallback to file
    return _file_load(MORPHEUS_TOKEN_FILE)


def clear_morpheus_token() -> None:
    """Remove the saved Morpheus Connect device token (Settings ->
    Disconnect). Best-effort; never raises."""
    _keyring_delete(SERVICE_NAME, MORPHEUS_TOKEN_KEY)
    _file_delete(MORPHEUS_TOKEN_FILE)


# --- Commons OAuth credentials ---
COMMONS_SERVICE_NAME = "WikidataBatchUploader-Commons"
COMMONS_OAUTH_KEYS = ['consumer_key', 'consumer_secret', 'access_token', 'access_secret']
COMMONS_OAUTH_FILE = BASE_DIR / 'commons_oauth_credentials.dat'


def save_commons_oauth(consumer_key: str, consumer_secret: str, access_token: str, access_secret: str) -> bool:
    """Save Commons OAuth 1.0a credentials for Commons uploads.

    Stored under a separate service name to avoid collisions with Wikidata
    credentials. Uses keyring when available; falls back to a local file.

    Returns:
        True if saved successfully, False otherwise.
    """
    creds = {
        'consumer_key': consumer_key,
        'consumer_secret': consumer_secret,
        'access_token': access_token,
        'access_secret': access_secret,
    }

    # Try keyring first, storing each token under its own key
    success = True
    for field in COMMONS_OAUTH_KEYS:
        key_name = f'oauth_{field}'
        if not _keyring_set(COMMONS_SERVICE_NAME, key_name, creds[field]):
            success = False
            break
    if success:
        return True

    # Fallback to file
    try:
        json_data = json.dumps(creds)
    except (TypeError, ValueError):
        return False

    if _file_save(COMMONS_OAUTH_FILE, json_data):
        # Clean up any partial keyring entries to avoid inconsistency
        for field in COMMONS_OAUTH_KEYS:
            _keyring_delete(COMMONS_SERVICE_NAME, f'oauth_{field}')
        logger.warning("Using local file fallback for Commons OAuth credential storage.")
        return True
    return False


def load_commons_oauth() -> Optional[Dict[str, str]]:
    """Load saved Commons OAuth credentials.

    Returns:
        Dictionary with keys 'consumer_key', 'consumer_secret', 'access_token',
        'access_secret' if all four values are available, otherwise None.
    """
    creds = {}

    # Try keyring first
    missing = False
    for field in COMMONS_OAUTH_KEYS:
        val = _keyring_get(COMMONS_SERVICE_NAME, f'oauth_{field}')
        if val is None:
            missing = True
            break
        creds[field] = val

    if not missing and len(creds) == 4:
        return creds

    # Fallback to file
    data = _file_load(COMMONS_OAUTH_FILE)
    if data is not None:
        try:
            data_dict = json.loads(data)
            if all(field in data_dict for field in COMMONS_OAUTH_KEYS):
                return data_dict
        except json.JSONDecodeError:
            pass
    return None


def clear_commons_oauth() -> None:
    """Delete saved Commons OAuth credentials from keyring and fallback file."""
    for field in COMMONS_OAUTH_KEYS:
        _keyring_delete(COMMONS_SERVICE_NAME, f'oauth_{field}')
    _file_delete(COMMONS_OAUTH_FILE)
