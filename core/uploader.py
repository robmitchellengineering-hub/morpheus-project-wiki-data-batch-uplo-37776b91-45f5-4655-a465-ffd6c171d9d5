import time
import pandas as pd
from wikidataintegrator import wdi_core, wdi_login
from typing import Dict, List, Any, Optional, Union, Callable

from core.validator import validate_dataset
from core.duplicate_checker import find_duplicate_rows_within_batch


def validate_login(username: str, password: str) -> Optional[wdi_login.WDLogin]:
    """Validate bot credentials and return a login object if successful, else None."""
    try:
        login = wdi_login.WDLogin(user=username, pwd=password)
        return login
    except Exception:
        return None


def validate_oauth_login(consumer_key: str, consumer_secret: str, access_token: str, access_secret: str) -> Optional[wdi_login.WDLogin]:
    """Validate OAuth 1.0a credentials and return a login object if successful, else None.

    Args:
        consumer_key: OAuth consumer key from Wikidata OAuth consumer registration.
        consumer_secret: OAuth consumer secret.
        access_token: OAuth access token.
        access_secret: OAuth access secret.

    Returns:
        WDLogin object if authentication succeeds; None otherwise.
    """
    try:
        login = wdi_login.WDLogin(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_secret=access_secret
        )
        return login
    except Exception:
        return None


# Precision reported for globe-coordinate claims built from row data (e.g.
# EXIF GPS via core/photo_metadata_merge.py). Typical phone/camera GPS
# accuracy is a few to ~15m; 0.0001 degrees (~11m at the equator) is a
# reasonable match rather than overclaiming survey-grade precision.
COORDINATE_PRECISION_DEGREES = 0.0001


def _parse_coordinate(value_str: str) -> Optional[tuple]:
    """Parse a 'lat,lon' string into (latitude, longitude) floats, or None
    if it isn't coordinate-shaped or the values are out of range."""
    parts = value_str.split(',')
    if len(parts) != 2:
        return None
    try:
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _value_to_statement(property_id: str, value: Any) -> Union[wdi_core.WDItemID, wdi_core.WDUrl, wdi_core.WDString, wdi_core.WDGlobeCoordinate, None]:
    """Convert a single value into a Wikidata statement object."""
    if pd.isna(value) or value == '':
        return None

    value_str = str(value).strip()
    if not value_str:
        return None

    # Globe coordinate ("coordinate location") -- must be built as
    # WDGlobeCoordinate, not a plain string, or Wikidata rejects/mishandles
    # the claim. A value that doesn't parse as 'lat,lon' falls through to
    # the string fallback below rather than being dropped.
    if property_id == 'P625':
        coord = _parse_coordinate(value_str)
        if coord is not None:
            lat, lon = coord
            return wdi_core.WDGlobeCoordinate(lat, lon, COORDINATE_PRECISION_DEGREES, prop_nr=property_id)

    # Item ID
    if value_str.startswith('Q') and value_str[1:].isdigit():
        return wdi_core.WDItemID(value=value_str, prop_nr=property_id)
    # URL
    elif value_str.lower().startswith('http://') or value_str.lower().startswith('https://'):
        return wdi_core.WDUrl(value=value_str, prop_nr=property_id)
    # String fallback
    else:
        return wdi_core.WDString(value=value_str, prop_nr=property_id)


def build_constants_statements(constants_df: pd.DataFrame) -> List[wdi_core.WDItemID]:
    """Prebuild project constants as WDItemID statements.

    Args:
        constants_df: DataFrame with 'property_id' and 'value' columns.

    Returns:
        List of wdi_core.WDItemID statements (only valid QID values).
    """
    statements = []
    for _, const_row in constants_df.iterrows():
        prop_id = str(const_row['property_id'])
        val = str(const_row['value'])
        if val.startswith('Q') and val[1:].isdigit():
            statements.append(wdi_core.WDItemID(value=val, prop_nr=prop_id))
    return statements


def build_statements(row: pd.Series, mapping: Dict[str, Optional[str]], constants_df: pd.DataFrame,
                     constant_statements: Optional[List[wdi_core.WDItemID]] = None) -> List[Any]:
    """Build a list of Wikidata statements for a given data row and mapping.

    Args:
        row: pandas Series representing one row of the dataset.
        mapping: dict mapping column names (strings) to property IDs (strings) or None.
        constants_df: DataFrame with 'property_id' and 'value' columns for project constants.
        constant_statements: Optional prebuilt list of constant statements. If not provided,
                             it is built from constants_df.

    Returns:
        List of wdi_core statement objects ready for upload.
    """
    statements = []

    # Add statements from mapped columns
    for col, property_id in mapping.items():
        if property_id is None:
            continue
        if col not in row.index:
            continue
        value = row[col]
        stmt = _value_to_statement(property_id, value)
        if stmt is not None:
            statements.append(stmt)

    # Add project constants (precomputed if possible)
    if constant_statements is None:
        constant_statements = build_constants_statements(constants_df)
    statements.extend(constant_statements)

    return statements


def upload_row(login: wdi_login.WDLogin, row: pd.Series, mapping: Dict[str, Optional[str]], constants_df: pd.DataFrame,
               edit_summary: str, maxlag: float = 5.0,
               constant_statements: Optional[List[wdi_core.WDItemID]] = None) -> str:
    """Create a new Wikidata item from a row and return the item ID.

    Handles Wikidata maxlag by setting wdi_core.config['MAXLAG'] before each write
    and retrying up to three times if the server reports maxlag exceeded.
    Each retry waits 10 seconds before trying again.

    Args:
        login: Authenticated WDLogin object.
        row: pandas Series representing one row.
        mapping: Column name -> property ID mapping.
        constants_df: Project constants DataFrame (used only if constant_statements is None).
        edit_summary: Edit summary for the write.
        maxlag: Maximum server lag allowed in seconds.
        constant_statements: Optional prebuilt project constant statements.
    """
    statements = build_statements(row, mapping, constants_df, constant_statements)
    if not statements:
        raise ValueError("No statements to upload for this row.")

    # Set global maxlag configuration using dictionary-style assignment
    wdi_core.config['MAXLAG'] = maxlag

    last_maxlag_error = None
    for attempt in range(3):
        try:
            item = wdi_core.WDItemEngine(data=statements, new_item=True)
            # Do NOT pass maxlag keyword to write; it is not a supported parameter.
            item.write(login, edit_summary=edit_summary)
            return item.wd_item_id
        except Exception as e:
            if 'maxlag' in str(e).lower():
                last_maxlag_error = e
                time.sleep(10)
                continue
            raise
    raise last_maxlag_error or Exception("Maxlag exceeded after multiple attempts")


def upload_rows(
    login: wdi_login.WDLogin,
    df: pd.DataFrame,
    mapping: Dict[str, Optional[str]],
    constants_df: pd.DataFrame,
    edit_summary: str,
    callback: Optional[Callable[[int, int, str], None]] = None,
    delay_seconds: float = 1.0,
    maxlag: float = 5.0,
    skip_rows: Optional[set] = None
) -> int:
    """Upload all rows in df to Wikidata, respecting a configurable delay.

    Calls upload_row for each row, optionally invoking a callback after each
    successful upload with (current_index, total_rows, item_id). Skips rows
    listed in skip_rows (by original index) without uploading, but still counts
    them in the progress callback. Sleeps delay_seconds between uploaded rows
    (except after the last row) to avoid rate limits.

    Args:
        login: Authenticated WDLogin object.
        df: DataFrame containing the data.
        mapping: Column name -> property ID mapping.
        constants_df: Project constants DataFrame.
        edit_summary: Edit summary for all writes.
        callback: Optional function receiving (done_count, total_count, item_id).
        delay_seconds: Delay between individual row uploads (default 1.0).
        maxlag: Maximum server lag allowed in seconds (default 5.0).
        skip_rows: Set of original DataFrame row indices to skip.

    Returns:
        Number of rows successfully uploaded.
    """
    total_rows = len(df)
    if skip_rows is None:
        skip_rows = set()

    # Precompute project constant statements once to avoid per-row overhead.
    constant_statements = build_constants_statements(constants_df)

    uploaded_count = 0
    for idx, (row_index, row) in enumerate(df.iterrows()):
        if row_index in skip_rows:
            if callback is not None:
                callback(idx + 1, total_rows, "Skipped")
            continue
        item_id = upload_row(
            login, row, mapping, constants_df, edit_summary,
            maxlag=maxlag,
            constant_statements=constant_statements
        )
        uploaded_count += 1
        if callback is not None:
            callback(idx + 1, total_rows, item_id)
        if idx < total_rows - 1 and delay_seconds > 0:
            time.sleep(delay_seconds)
    return uploaded_count


def dry_run(df: pd.DataFrame, mapping: Dict[str, Optional[str]], constants_df: pd.DataFrame, properties_df: Optional[pd.DataFrame] = None) -> str:
    """Perform a dry run: count rows, statements, missing values, and run validation.

    Args:
        df: Dataset to evaluate.
        mapping: Column name -> property ID mapping.
        constants_df: Project constants DataFrame.
        properties_df: Optional property reference DataFrame for validator.

    Returns:
        A human-readable summary string.
    """
    total_rows = len(df)
    total_statements = 0
    missing_count = 0
    rows_with_missing = 0
    samples = []

    # Precompute project constant statements for efficiency.
    constant_statements = build_constants_statements(constants_df)

    for idx, row in df.iterrows():
        statements = build_statements(row, mapping, constants_df, constant_statements)
        total_statements += len(statements)

        row_has_missing = False
        for col, prop in mapping.items():
            if prop is not None and col in row.index:
                value = row[col]
                if pd.isna(value) or str(value).strip() == '':
                    missing_count += 1
                    if not row_has_missing:
                        rows_with_missing += 1
                        row_has_missing = True
                    if len(samples) < 5:
                        samples.append(f"Row {idx}: missing '{col}'")

    avg_statements = total_statements / total_rows if total_rows > 0 else 0
    summary = f"Dry run: {total_rows} row(s) processed.\n"
    summary += f"Total statements: {total_statements} (average {avg_statements:.2f} per row).\n"
    summary += f"Missing values: {missing_count} across {rows_with_missing} row(s)."
    if samples:
        summary += "\nExamples of missing values:\n" + "\n".join(samples)

    # Duplicate detection (within batch)
    dup_groups = find_duplicate_rows_within_batch(df, mapping)
    if dup_groups:
        summary += f"\n\nWithin-batch duplicates: {len(dup_groups)} group(s) of identical rows found."

    # Run validator and append its findings
    validation = validate_dataset(df, mapping, constants_df, properties_df)
    if validation['errors'] or validation['warnings']:
        summary += "\n\nValidation:"
        for error in validation['errors']:
            summary += f"\n  [ERROR] {error}"
        for warning in validation['warnings']:
            summary += f"\n  [WARNING] {warning}"

    return summary
