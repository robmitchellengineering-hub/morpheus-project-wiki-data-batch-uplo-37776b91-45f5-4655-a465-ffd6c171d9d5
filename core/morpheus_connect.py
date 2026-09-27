"""Morpheus Connect — device-flow login so each operator uses their own
Morpheus account and credits for AI mapping suggestions, instead of a
shared secret baked into the build.

Three small calls against the real, live Morpheus API:
  - start_device_flow(): kick off a connection request.
  - poll_device_flow(device_code): check whether the operator has approved
    it yet (one HTTP call; the caller is responsible for the wait/repeat
    loop — see ui/connect_dialog.py's MorpheusConnectWorker).
  - suggest_mappings_with_morpheus(columns, samples, token): the actual
    billed AI call, once connected, backed by the operator's own Morpheus
    account instead of a hardcoded Gemini key.

It still never raises — the caller always falls back to local suggestion — but
it no longer hides why: it returns a MappingSuggestion carrying the failure
reason, because "no suggestions" and "the server returned 500" used to reach the
operator as the same sentence.
"""
from typing import List, NamedTuple, Optional

import requests

# The API lives on its own subdomain, separate from the main site
# (morpheus.nz is the Netlify-hosted frontend; api.morpheus.nz is the real
# Northflank backend) -- confirmed live, not assumed from reading the
# server source alone, which only shows route paths, not the production
# origin they're actually served from. The verification_uri(_complete)
# /device/start returns is correctly the main site (morpheus.nz/connect,
# where a human approves in a browser) and is used as-is, never
# reconstructed from this constant.
MORPHEUS_API_BASE_URL = "https://api.morpheus.nz"
CLIENT_LABEL = "Wikidata Batch Uploader"
DEVICE_SCOPES = ["ai_action"]


def start_device_flow():
    """Start a Morpheus Connect device-login request.

    Returns the /device/start response dict — {device_code, user_code,
    verification_uri, verification_uri_complete, interval, expires_in} —
    or None if the request itself failed (no internet, Morpheus
    unreachable, etc.).
    """
    try:
        resp = requests.post(
            f"{MORPHEUS_API_BASE_URL}/api/auth/device/start",
            json={"client_label": CLIENT_LABEL, "scopes": DEVICE_SCOPES},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    if not data.get("device_code") or not data.get("user_code"):
        return None
    return data


def poll_device_flow(device_code):
    """One poll of the pending device request.

    Returns the /device/poll response dict, e.g. {"status": "pending"} or
    {"status": "approved", "token": "dvc_..."}. Returns
    {"status": "error"} on a request failure (network blip, etc.) rather
    than raising — the caller's poll loop treats that as "try again next
    interval", not a hard failure.
    """
    try:
        resp = requests.post(
            f"{MORPHEUS_API_BASE_URL}/api/auth/device/poll",
            json={"device_code": device_code},
            timeout=10,
        )
        data = resp.json()
    except Exception:
        return {"status": "error"}
    if not isinstance(data, dict) or not data.get("status"):
        return {"status": "error"}
    return data


class MappingSuggestion(NamedTuple):
    """What the AI mapping call produced: suggestions, and why it produced none.

    `error` is None on success (including a legitimate empty answer) and a
    human-readable reason otherwise — the HTTP status and body, or the exception
    text for a timeout or a connection failure.
    """

    mappings: List[dict]
    error: Optional[str] = None


def suggest_mappings_with_morpheus(columns, samples, token) -> MappingSuggestion:
    """Ask Morpheus (runAiAction, task=schema_mapping) to suggest a
    Wikidata property label for each column, using the operator's own
    connected Morpheus account.

    Args:
        columns: list of column name strings.
        samples: list of sample rows, each a list of stringified values in
            column order (matches ui/mapping_panel.py's existing shape —
            this is the exact request runAiAction.js was verified against).
        token: the dvc_... device token from a completed Morpheus Connect
            login (core.credential_storage.load_morpheus_token()).

    Returns:
        MappingSuggestion(mappings=[...]) on success and
        MappingSuggestion(mappings=[], error="...") on any failure — never raises,
        so a caller can always fall back to local suggestion while still being able
        to tell the operator what went wrong.
    """
    if not token:
        return MappingSuggestion([], "Not connected to Morpheus — connect first, then ask it to map the columns.")
    try:
        resp = requests.post(
            f"{MORPHEUS_API_BASE_URL}/api/functions/runAiAction",
            json={"task": "schema_mapping", "columns": columns, "samples": samples},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as exc:
        # The status and the body are the whole point: this used to be one of
        # three indistinguishable `return []` paths, so an operator saw
        # "did not return suggestions" for a 500, a 401 and a timeout alike.
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        body = ''
        try:
            body = (exc.response.text or '').strip()[:300]
        except Exception:
            body = ''
        detail = f"HTTP {status}" if status else str(exc)
        return MappingSuggestion([], f"Morpheus rejected the mapping request ({detail})." + (f" {body}" if body else ""))
    except Exception as exc:
        return MappingSuggestion([], f"Could not reach Morpheus: {type(exc).__name__}: {exc}")

    mappings = data.get("mappings", [])
    if not isinstance(mappings, list):
        return MappingSuggestion([], "Morpheus returned an unexpected response shape for the mapping request.")
    return MappingSuggestion([
        {"column": str(m["column"]), "label": str(m["label"])}
        for m in mappings
        if isinstance(m, dict) and m.get("column") and m.get("label")
    ])
