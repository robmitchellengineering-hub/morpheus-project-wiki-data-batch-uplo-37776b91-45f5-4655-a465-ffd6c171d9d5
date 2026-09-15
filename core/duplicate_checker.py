import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from wikidataintegrator import wdi_core


def _is_valid_qid(value: str) -> bool:
    """Check if a string looks like a Wikidata item ID (Q followed by digits)."""
    return value.startswith('Q') and value[1:].isdigit()


def _build_sparql_value(value: Any) -> Optional[str]:
    """Convert a row value into a SPARQL value representation.

    Returns None if the value is missing, empty, or cannot be used.
    """
    if pd.isna(value):
        return None
    value_str = str(value).strip()
    if not value_str:
        return None
    if _is_valid_qid(value_str):
        return f"wd:{value_str}"
    else:
        # Escape backslashes and double quotes for a string literal
        escaped = value_str.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'


def find_duplicate_rows_within_batch(df: pd.DataFrame, mapping: Dict[str, Optional[str]]) -> List[List[Any]]:
    """
    Find groups of rows with identical values across all mapped non-null columns.

    Rows with any missing value in a mapped column are excluded from comparison.

    Args:
        df: The dataframe to check.
        mapping: Column name -> property ID (str) or None. Only columns with a
            non-None property ID are considered.

    Returns:
        A list of lists; each inner list contains the original row indices
        that form a duplicate group.
    """
    mapped_cols = [col for col, pid in mapping.items() if pid is not None and col in df.columns]
    if not mapped_cols:
        return []

    # Filter rows that have no missing or empty values in any mapped column
    complete_mask = ~df[mapped_cols].isna().any(axis=1)
    empty_mask = df[mapped_cols].astype(str).apply(lambda x: x.str.strip() == '', axis=0).any(axis=1)
    complete_mask = complete_mask & ~empty_mask
    complete_df = df.loc[complete_mask]

    if complete_df.empty:
        return []

    # Vectorized hashing: clean each column (strip whitespace) and hash the entire row.
    # This avoids Python-level tuple creation per row.
    clean_df = complete_df[mapped_cols].astype(str).apply(lambda col: col.str.strip())
    hash_series = pd.util.hash_pandas_object(clean_df, index=False)

    groups = complete_df.index.groupby(hash_series).apply(list).to_dict()
    duplicate_groups = [indices for key, indices in groups.items() if len(indices) > 1]
    return duplicate_groups


def find_existing_items(row: pd.Series, mapping: Dict[str, Optional[str]], duplicate_key_columns: List[str]) -> List[str]:
    """
    Query Wikidata for existing items matching the given row using the duplicate key columns.

    Builds a SPARQL query that matches items having the same property values as the
    given row for each column marked as duplicate key and having a non-null mapping.

    Args:
        row: pandas Series representing one row of data.
        mapping: Column name -> property ID (str) or None.
        duplicate_key_columns: List of column names to use for matching.

    Returns:
        List of Wikidata item IDs (QIDs) that match. Empty list if none found
        or if an error occurs.
    """
    if not duplicate_key_columns:
        return []

    conditions = []
    for col in duplicate_key_columns:
        if col not in row.index:
            continue
        prop_id = mapping.get(col)
        if prop_id is None:
            continue
        # Property ID must look like P123
        if not (prop_id.startswith('P') and prop_id[1:].isdigit()):
            continue
        value = row[col]
        sparql_value = _build_sparql_value(value)
        if sparql_value is None:
            continue
        conditions.append(f"?item wdt:{prop_id} {sparql_value} .")

    if not conditions:
        return []

    query = "SELECT ?item WHERE {\n" + "\n  ".join(conditions) + "\n} LIMIT 10"
    try:
        results = wdi_core.WDItemEngine.execute_sparql_query(query)
    except Exception:
        return []

    item_ids = []
    for result in results:
        item_uri = result.get('item', {}).get('value', '')
        if not item_uri:
            continue
        qid = item_uri.rsplit('/', 1)[-1]
        if _is_valid_qid(qid):
            item_ids.append(qid)
    return item_ids
