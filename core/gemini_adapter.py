import json
import requests
from typing import List, Dict, Any, Optional


def suggest_mappings_with_gemini(columns: List[str], samples: List[List[str]], api_key: str, model: str = 'gemini-1.5-flash') -> List[Dict[str, str]]:
    """
    Use Google Gemini to suggest column-to-Wikidata property label mappings.

    Args:
        columns: List of column names (strings).
        samples: List of sample rows (each a list of strings, matching columns order).
        api_key: Google Gemini API key.
        model: Gemini model name (default 'gemini-1.5-flash').

    Returns:
        List of dicts with 'column' and 'label' keys, e.g.
        [{"column": "name", "label": "inception"}, ...]
        Returns empty list on any failure.
    """
    if not api_key:
        return []

    prompt = (
        "You are a Wikidata schema mapping assistant. "
        "Given the following dataset column headers and sample rows, suggest for each column "
        "the most appropriate Wikidata property label (e.g., 'inception', 'country', 'population'). "
        "Return ONLY a JSON object with a 'mappings' array. Each mapping must have 'column' and 'label'. "
        "Use the exact column names as given. If a column does not map to a known Wikidata property, skip it.\n\n"
        "Column headers:\n"
        f"{json.dumps(columns, ensure_ascii=False)}\n\n"
        "Sample rows (each row is a list where values correspond to columns order):\n"
    )
    for i, row in enumerate(samples, 1):
        prompt += f"Row {i}: {json.dumps(row, ensure_ascii=False)}\n"
    prompt += "\nRespond with JSON only."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
    except Exception:
        return []

    try:
        candidates = result.get("candidates", [])
        if not candidates:
            return []
        first_candidate = candidates[0]
        content = first_candidate.get("content", {})
        parts = content.get("parts", [])
        if not parts:
            return []
        text = parts[0].get("text", "")
        if not text:
            return []
        # Remove markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        # Parse JSON
        data = json.loads(text)
        mappings = data.get("mappings", [])
        if not isinstance(mappings, list):
            return []
        validated = []
        for item in mappings:
            if isinstance(item, dict) and "column" in item and "label" in item:
                validated.append({
                    "column": str(item["column"]),
                    "label": str(item["label"])
                })
        return validated
    except Exception:
        return []
