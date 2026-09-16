"""Upload local files to Wikimedia Commons using OAuth 1.0a.

This module provides a single entry point, :func:`upload_file_to_commons`,
which handles CSRF token retrieval, direct upload for files up to 5 MB,
and chunked (stashed) upload for larger files. Credentials are loaded
from core.credential_storage (or passed explicitly) and are used to
create an OAuth1Session that signs every API request.

Maxlag is respected by including the ``maxlag`` parameter in every
upload request and by retrying on server-reported lag or HTTP 503
responses, with an exponential backoff.
"""

import os
import time

import requests
from requests_oauthlib import OAuth1Session

from core import credential_storage


class CommonsUploadError(Exception):
    """Raised when a Commons upload fails."""


COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
CHUNK_SIZE = 5 * 1024 * 1024  # 5 MiB, MediaWiki's recommended chunk size
DIRECT_UPLOAD_LIMIT = 5 * 1024 * 1024


def _load_credentials(credentials=None):
    """Return a dict with OAuth 1.0a credentials.

    Args:
        credentials: Optional dict or object with attributes
            consumer_key, consumer_secret, access_token, access_secret.
            If None, credentials are loaded from
            core.credential_storage.load_commons_oauth().

    Returns:
        dict with keys 'consumer_key', 'consumer_secret', 'access_token',
        'access_secret'.

    Raises:
        CommonsUploadError: if credentials are missing or malformed.
    """
    if credentials is None:
        stored = credential_storage.load_commons_oauth()
        if stored is None:
            raise CommonsUploadError("Commons OAuth credentials are not configured.")
        credentials = stored

    required = ["consumer_key", "consumer_secret", "access_token", "access_secret"]

    if isinstance(credentials, dict):
        for key in required:
            if key not in credentials or not credentials[key]:
                raise CommonsUploadError(f"Missing credential field: {key}")
        return {key: credentials[key] for key in required}

    # Assume object with attributes
    try:
        return {
            "consumer_key": credentials.consumer_key,
            "consumer_secret": credentials.consumer_secret,
            "access_token": credentials.access_token,
            "access_secret": credentials.access_secret,
        }
    except AttributeError as exc:
        raise CommonsUploadError(f"Invalid credentials object: {exc}") from exc


def _get_csrf_token(session):
    """Fetch a fresh CSRF token from the MediaWiki API."""
    try:
        response = session.post(
            COMMONS_API_URL,
            data={
                "action": "query",
                "meta": "tokens",
                "format": "json",
            },
            timeout=30,
        )
    except requests.exceptions.RequestException as exc:
        raise CommonsUploadError(f"Connection error fetching CSRF token: {exc}") from exc

    data = _handle_api_response(response)
    token = data.get("query", {}).get("tokens", {}).get("csrftoken")
    if not token:
        raise CommonsUploadError("Failed to obtain CSRF token from Commons API.")
    return token


def _handle_api_response(response):
    """Process a Commons API response and raise on errors.

    Args:
        response: requests.Response object.

    Returns:
        Parsed JSON dict.

    Raises:
        CommonsUploadError: if the API returned an error status, a
            MediaWiki error in the JSON body, or a non-JSON response.
    """
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise CommonsUploadError(
            f"HTTP error {response.status_code}: {response.text[:200]}"
        ) from exc

    try:
        data = response.json()
    except ValueError:
        raise CommonsUploadError(
            f"Unexpected non-JSON response: {response.status_code} {response.text[:200]}"
        )

    if "error" in data:
        code = data["error"].get("code", "unknown")
        info = data["error"].get("info", "")
        raise CommonsUploadError(f"Commons API error {code}: {info}")

    return data


def _build_wikitext(text=None, category=None, license_template=None):
    """Build wikitext for the file description page."""
    parts = []
    if text:
        parts.append(text)
    if category:
        # Ensure category is in [[Category:...]] form
        if not category.startswith("Category:"):
            category = f"Category:{category}"
        parts.append(f"[[{category}]]")
    if license_template:
        parts.append(license_template)
    return "\n".join(parts) if parts else None


def _upload_direct(
    session,
    filename,
    local_path,
    comment,
    text,
    csrf_token,
    maxlag,
    ignorewarnings=True,
):
    """Upload a file in a single multipart POST."""
    data = {
        "action": "upload",
        "filename": filename,
        "comment": comment or "",
        "text": text or "",
        "token": csrf_token,
        "ignorewarnings": "1" if ignorewarnings else "0",
        "maxlag": str(maxlag),
        "format": "json",
    }
    try:
        with open(local_path, "rb") as file_obj:
            files = {"file": (filename, file_obj)}
            response = session.post(
                COMMONS_API_URL,
                data=data,
                files=files,
                timeout=60,
            )
    except requests.exceptions.RequestException as exc:
        raise CommonsUploadError(f"Connection error during upload: {exc}") from exc
    return _handle_api_response(response)


def _upload_chunked(
    session,
    filename,
    local_path,
    comment,
    text,
    csrf_token,
    maxlag,
    chunk_size=CHUNK_SIZE,
    ignorewarnings=True,
):
    """Upload a file using the stash upload API.

    The file is split into chunk_size pieces and uploaded sequentially
    with ``stash=1``. Each chunk after the first must include the
    ``filekey`` returned from the previous chunk. After all chunks are
    stashed, the upload is finalized using the final ``filekey``.
    """
    total_size = os.path.getsize(local_path)
    filekey = None
    offset = 0

    with open(local_path, "rb") as file_obj:
        while offset < total_size:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            data = {
                "action": "upload",
                "filename": filename,
                "comment": comment or "",
                "text": text or "",
                "token": csrf_token,
                "ignorewarnings": "1" if ignorewarnings else "0",
                "maxlag": str(maxlag),
                "stash": "1",
                "format": "json",
                "offset": str(offset),
                "filesize": str(total_size),
            }
            if filekey is not None:
                data["filekey"] = filekey

            try:
                files = {"file": (filename, chunk)}
                response = session.post(
                    COMMONS_API_URL,
                    data=data,
                    files=files,
                    timeout=60,
                )
            except requests.exceptions.RequestException as exc:
                raise CommonsUploadError(f"Connection error during chunked upload: {exc}") from exc

            result = _handle_api_response(response)
            upload_info = result.get("upload", {})
            new_filekey = upload_info.get("filekey")
            if not new_filekey:
                raise CommonsUploadError("Chunked upload did not return a filekey.")
            filekey = new_filekey
            offset += len(chunk)

    # Finalize the stashed upload
    data = {
        "action": "upload",
        "filename": filename,
        "comment": comment or "",
        "text": text or "",
        "token": csrf_token,
        "ignorewarnings": "1" if ignorewarnings else "0",
        "maxlag": str(maxlag),
        "filekey": filekey,
        "format": "json",
    }
    try:
        response = session.post(
            COMMONS_API_URL,
            data=data,
            timeout=60,
        )
    except requests.exceptions.RequestException as exc:
        raise CommonsUploadError(f"Connection error during finalization: {exc}") from exc
    return _handle_api_response(response)


def upload_file_to_commons(
    local_path,
    filename=None,
    text=None,
    comment=None,
    category=None,
    license_template=None,
    credentials=None,
    maxlag=5,
    max_retries=3,
):
    """Upload a local file to Wikimedia Commons.

    Args:
        local_path: Path to the local file.
        filename: Destination filename on Commons. If None, uses the
            local basename.
        text: Additional wikitext to include on the file description page.
        comment: Edit summary/comment for the upload.
        category: Category name (without "Category:" prefix is fine).
        license_template: License template (e.g. "{{CC-BY-SA-4.0}}").
        credentials: Optional OAuth 1.0a credentials as a dict or object
            with attributes consumer_key, consumer_secret, access_token,
            access_secret. If None, credentials are loaded from
            core.credential_storage.load_commons_oauth().
        maxlag: Maxlag value in seconds (default 5).
        max_retries: Number of retries on maxlag/503 errors.

    Returns:
        dict with keys 'filename', 'url', 'success'.

    Raises:
        CommonsUploadError on failure.
    """
    if not os.path.isfile(local_path):
        raise CommonsUploadError(f"File not found: {local_path}")

    file_size = os.path.getsize(local_path)
    if file_size == 0:
        raise CommonsUploadError("Cannot upload an empty file.")

    if filename is None:
        filename = os.path.basename(local_path)

    creds = _load_credentials(credentials)
    session = OAuth1Session(
        client_key=creds["consumer_key"],
        client_secret=creds["consumer_secret"],
        resource_owner_key=creds["access_token"],
        resource_owner_secret=creds["access_secret"],
    )

    csrf_token = _get_csrf_token(session)
    wikitext = _build_wikitext(text, category, license_template)

    attempt = 0
    while True:
        try:
            if file_size <= DIRECT_UPLOAD_LIMIT:
                result = _upload_direct(
                    session,
                    filename,
                    local_path,
                    comment,
                    wikitext,
                    csrf_token,
                    maxlag,
                )
            else:
                result = _upload_chunked(
                    session,
                    filename,
                    local_path,
                    comment,
                    wikitext,
                    csrf_token,
                    maxlag,
                )

            upload_info = result.get("upload", {})
            file_url = upload_info.get("imageinfo", {}).get("url") or upload_info.get("url")
            return {
                "filename": upload_info.get("filename", filename),
                "url": file_url or "",
                "success": True,
            }

        except CommonsUploadError as exc:
            error_msg = str(exc).lower()
            if "maxlag" in error_msg or "503" in error_msg:
                attempt += 1
                if attempt <= max_retries:
                    # Exponential backoff, then refresh token and retry
                    time.sleep(10 * attempt)
                    csrf_token = _get_csrf_token(session)
                    continue
            raise
