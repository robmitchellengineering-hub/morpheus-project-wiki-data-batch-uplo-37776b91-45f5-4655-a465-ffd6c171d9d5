import pandas as pd
from typing import Dict, List, Optional, Any


def validate_dataset(
    df: pd.DataFrame,
    mapping: Dict[str, Optional[str]],
    constants_df: pd.DataFrame,
    properties_df: Optional[pd.DataFrame] = None
) -> Dict[str, List[str]]:
    """
    Validate a dataset before upload.

    Checks:
      1. Mapped property IDs exist in the reference table (if properties_df provided).
      2. Project constants have valid QID values and property IDs exist in reference.
      3. Data completeness: mapped columns contain no missing values.

    Args:
        df: The dataset to be uploaded.
        mapping: Column name (str) -> Wikidata property ID (str) or None.
        constants_df: DataFrame with columns 'property_id' and 'value'.
        properties_df: Optional DataFrame with at least 'property_id' column.

    Returns:
        dict with keys 'errors' and 'warnings', each a list of strings.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if df.empty:
        errors.append("Dataset is empty.")
        return {"errors": errors, "warnings": warnings}

    # Build set of valid property IDs if reference table is provided
    valid_ids = None
    if properties_df is not None and not properties_df.empty:
        try:
            valid_ids = set(properties_df['property_id'].astype(str))
        except KeyError:
            warnings.append("Property reference table is missing 'property_id' column.")

    # 1. Validate mapping property IDs
    for column, property_id in mapping.items():
        if property_id is None:
            continue
        pid = str(property_id)
        if valid_ids is not None and pid not in valid_ids:
            warnings.append(
                f"Mapped property '{pid}' for column '{column}' is not in the property reference table."
            )

    # 2. Validate project constants
    for idx, const_row in constants_df.iterrows():
        prop_id = str(const_row['property_id'])
        value = str(const_row['value'])

        if valid_ids is not None and prop_id not in valid_ids:
            warnings.append(
                f"Project constant property '{prop_id}' is not in the property reference table."
            )

        if not (value.startswith('Q') and value[1:].isdigit()):
            errors.append(
                f"Project constant value '{value}' is not a valid QID (must be Q followed by digits)."
            )

    # 3. Data completeness (vectorized)
    mapped_cols = [col for col, pid in mapping.items() if pid is not None]
    if not mapped_cols:
        return {"errors": errors, "warnings": warnings}

    missing_cols = [col for col in mapped_cols if col not in df.columns]
    for col in missing_cols:
        warnings.append(f"Column '{col}' not found in dataset.")

    present_mapped_cols = [col for col in mapped_cols if col in df.columns]
    if present_mapped_cols:
        df_cols = df[present_mapped_cols]
        is_na = df_cols.isna()
        is_empty_str = df_cols.astype(str).apply(lambda col: col.str.strip().eq(''))
        missing_mask = is_na | is_empty_str

        total_missing = int(missing_mask.sum().sum())
        rows_with_missing = missing_mask.any(axis=1)
        missing_rows = int(rows_with_missing.sum())

        if missing_rows > 0:
            warnings.append(
                f"Found missing values in {missing_rows} row(s) across mapped columns "
                f"(total missing cells: {total_missing})."
            )

            # Sample up to 5 specific missing entries for useful output.
            missing_pairs = missing_mask.stack().reset_index()
            missing_pairs.columns = ['row', 'col', 'missing']
            sample_pairs = missing_pairs[missing_pairs['missing']].head(5)
            for _, r in sample_pairs.iterrows():
                warnings.append(
                    f"Row {r['row']}: missing value for column '{r['col']}'"
                )

    return {"errors": errors, "warnings": warnings}
