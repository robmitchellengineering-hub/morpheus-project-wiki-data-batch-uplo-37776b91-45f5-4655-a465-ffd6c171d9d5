import os
import sys
import json
import base64
import ctypes
from ctypes import wintypes
from typing import Optional, Dict

from config import BASE_DIR

CREDENTIAL_FILE = BASE_DIR / 'credentials.dat'

# Constants for CryptProtectData/CryptUnprotectData
CRYPTPROTECT_UI_FORBIDDEN = 0x01

class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ('cbData', wintypes.DWORD),
        ('pbData', ctypes.POINTER(ctypes.c_char))
    ]

def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    if not blob.pbData:
        return b''
    return ctypes.string_at(blob.pbData, blob.cbData)

def _encrypt_bytes(data: bytes) -> Optional[bytes]:
    """Encrypt bytes using Windows DPAPI (CryptProtectData)."""
    if sys.platform != 'win32':
        return None

    data_in = DATA_BLOB()
    data_in.cbData = len(data)
    # Keep buffer alive by storing in local variable
    input_buffer = ctypes.create_string_buffer(data, len(data))
    data_in.pbData = ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_char))

    data_out = DATA_BLOB()

    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(data_in),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(data_out)
    ):
        return None

    try:
        return _blob_to_bytes(data_out)
    finally:
        ctypes.windll.kernel32.LocalFree(data_out.pbData)

def _decrypt_bytes(blob: bytes) -> Optional[bytes]:
    """Decrypt bytes using Windows DPAPI (CryptUnprotectData)."""
    if sys.platform != 'win32':
        return None

    data_in = DATA_BLOB()
    data_in.cbData = len(blob)
    # Keep buffer alive by storing in local variable
    input_buffer = ctypes.create_string_buffer(blob, len(blob))
    data_in.pbData = ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_char))

    data_out = DATA_BLOB()

    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(data_in),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(data_out)
    ):
        return None

    try:
        return _blob_to_bytes(data_out)
    finally:
        ctypes.windll.kernel32.LocalFree(data_out.pbData)

def save_credentials(credentials: Dict[str, str]) -> bool:
    """Encrypt and save credentials to disk using DPAPI.

    Args:
        credentials: dictionary containing credential fields, including
            'type' ('bot' or 'oauth') and the corresponding values.

    Returns:
        True if saved successfully, False otherwise.
    """
    if sys.platform != 'win32':
        return False

    try:
        json_data = json.dumps(credentials).encode('utf-8')
        encrypted = _encrypt_bytes(json_data)
        if encrypted is None:
            return False
        encoded = base64.b64encode(encrypted).decode('ascii')
        with open(CREDENTIAL_FILE, 'w') as f:
            f.write(encoded)
        return True
    except Exception:
        return False

def load_credentials() -> Optional[Dict[str, str]]:
    """Load and decrypt saved credentials.

    Returns:
        Dictionary of credentials if available and decryption succeeds,
        otherwise None.
    """
    if sys.platform != 'win32':
        return None

    if not CREDENTIAL_FILE.exists():
        return None

    try:
        encoded = CREDENTIAL_FILE.read_text()
        encrypted = base64.b64decode(encoded)
        decrypted = _decrypt_bytes(encrypted)
        if decrypted is None:
            return None
        return json.loads(decrypted.decode('utf-8'))
    except Exception:
        return None
