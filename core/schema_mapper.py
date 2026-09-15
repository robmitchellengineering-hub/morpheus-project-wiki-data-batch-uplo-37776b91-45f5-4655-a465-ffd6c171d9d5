import difflib
import pandas as pd


def suggest_mappings(columns, properties_df):
    """Return a dictionary mapping each column name to a best-guess property_id or None."""
    mapping = {}
    if properties_df is None or properties_df.empty:
        return {col: None for col in columns}

    labels = properties_df['label'].astype(str).tolist()
    property_ids = properties_df['property_id'].astype(str).tolist()
    lowered_labels = [l.lower() for l in labels]

    for col in columns:
        col_str = str(col).lower()
        matches = difflib.get_close_matches(col_str, lowered_labels, n=1, cutoff=0.6)
        if matches:
            idx = lowered_labels.index(matches[0])
            mapping[col] = property_ids[idx]
        else:
            mapping[col] = None
    return mapping
