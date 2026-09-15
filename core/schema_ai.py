import requests
import pandas as pd


def suggest_ai_mappings(columns, sample_df, endpoint_url, api_key):
    """Send column headers and up to 5 sample rows to a configurable AI endpoint.

    The endpoint is expected to return a JSON object with a 'mappings' key:
    {
        "mappings": [
            {"column": "col1", "label": "inception"},
            {"column": "col2", "label": "country"}
        ]
    }

    Args:
        columns: List of column name strings.
        sample_df: pandas DataFrame containing sample rows (up to 5 will be sent).
        endpoint_url: Full URL of the AI mapping endpoint.
        api_key: Optional API key; if provided, sent as Bearer token in Authorization header.

    Returns:
        List of dicts with 'column' and 'label' keys on success.
        None if the endpoint is not configured, request fails, or response is invalid.
    """
    if not endpoint_url:
        return None

    # Limit sample rows to 5
    sample_rows = []
    for _, row in sample_df.head(5).iterrows():
        row_dict = {}
        for col in columns:
            val = row[col]
            if pd.isna(val):
                val = None
            else:
                # Convert to string for JSON serialization; preserve basic types if possible
                val = str(val)
            row_dict[col] = val
        sample_rows.append(row_dict)

    payload = {
        "columns": columns,
        "sample_rows": sample_rows
    }

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = requests.post(endpoint_url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        mappings = data.get("mappings", [])
        if not isinstance(mappings, list):
            return None

        result = []
        for item in mappings:
            if isinstance(item, dict) and "column" in item and "label" in item:
                result.append({"column": str(item["column"]), "label": str(item["label"])})
            else:
                # Invalid item structure, reject entire response
                return None
        return result
    except Exception:
        return None
