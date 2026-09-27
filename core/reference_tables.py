import pandas as pd
from pathlib import Path

# `datatype` is the property's Wikidata datatype, and it decides which statement
# class a value must become: a time or a quantity written as a string is rejected
# by Wikidata (that is how P571 inception and P1082 population failed). It is a
# column in the reference table rather than a hardcoded map, so an operator can
# add a property and its type without a code change. A table without the column
# still loads — the datatype is then inferred from the value, as before.
DEFAULT_PROPERTIES = [
    {"property_id": "P571", "label": "inception", "datatype": "time"},
    {"property_id": "P17", "label": "country", "datatype": "wikibase-item"},
    {"property_id": "P131", "label": "located in the administrative territorial entity", "datatype": "wikibase-item"},
    {"property_id": "P625", "label": "coordinate location", "datatype": "globe-coordinate"},
    {"property_id": "P18", "label": "image", "datatype": "commonsMedia"},
    {"property_id": "P31", "label": "instance of", "datatype": "wikibase-item"},
]

DEFAULT_CONSTANTS = [
    {"property_id": "P31", "value": "Q532"},
]


def ensure_sample_reference_tables(ref_dir):
    """Create sample reference tables if they do not exist."""
    ref_dir = Path(ref_dir)
    ref_dir.mkdir(parents=True, exist_ok=True)
    props_path = ref_dir / "wikidata_properties.xlsx"
    const_path = ref_dir / "project_constants.xlsx"

    if not props_path.exists():
        df_props = pd.DataFrame(DEFAULT_PROPERTIES)
        df_props.to_excel(props_path, index=False)

    if not const_path.exists():
        df_const = pd.DataFrame(DEFAULT_CONSTANTS)
        df_const.to_excel(const_path, index=False)


def datatype_map(properties_df) -> dict:
    """Return {property_id: datatype} from the reference table.

    Empty when the table predates the `datatype` column, or the column is blank —
    callers then fall back to inferring the type from the value, which is the
    behaviour before the column existed.
    """
    if properties_df is None or 'datatype' not in getattr(properties_df, 'columns', []):
        return {}
    out = {}
    for _, row in properties_df.iterrows():
        prop = str(row.get('property_id', '') or '').strip()
        dtype = str(row.get('datatype', '') or '').strip()
        if prop and dtype and dtype.lower() != 'nan':
            out[prop] = dtype
    return out


def _with_default_datatypes(df, props_path):
    """Add a `datatype` column to a table written by a build that had none.

    Loading is the right place for this: an existing install already has
    wikidata_properties.xlsx, and ensure_sample_reference_tables only writes when
    the file is absent — so without this, upgrading would keep reading the old
    table and every value would still go out as a string, which is the fault this
    column exists to fix. Known properties take the default datatype; anything else
    is left blank, which keeps the old value-based inference for it. The file is
    rewritten on a best-effort basis: a read-only directory must not stop the app
    from loading.
    """
    if 'datatype' not in df.columns:
        defaults = {row['property_id']: row.get('datatype', '') for row in DEFAULT_PROPERTIES}
        if 'property_id' in df.columns:
            df = df.copy()
            df['datatype'] = [defaults.get(str(pid), '') for pid in df['property_id']]
        else:
            return df
    try:
        df.to_excel(props_path, index=False)
    except Exception:
        pass
    return df


def load_wikidata_properties(ref_dir):
    """Load wikidata_properties.xlsx as a DataFrame with required columns."""
    ref_dir = Path(ref_dir)
    props_path = ref_dir / "wikidata_properties.xlsx"
    if not props_path.exists():
        ensure_sample_reference_tables(ref_dir)
    df = pd.read_excel(props_path, engine='openpyxl')
    required = ['property_id', 'label']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"wikidata_properties.xlsx must contain column '{col}'")
    # An older table gains the datatype column here, and only here — that is the
    # upgrade path for an install that already exists.
    return _with_default_datatypes(df, props_path)


def load_project_constants(ref_dir):
    """Load project_constants.xlsx as a DataFrame with required columns."""
    ref_dir = Path(ref_dir)
    const_path = ref_dir / "project_constants.xlsx"
    if not const_path.exists():
        ensure_sample_reference_tables(ref_dir)
    df = pd.read_excel(const_path, engine='openpyxl')
    required = ['property_id', 'value']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"project_constants.xlsx must contain column '{col}'")
    return df


def save_wikidata_properties(ref_dir, df):
    """Save the wikidata_properties DataFrame to xlsx, validating required columns."""
    required = ['property_id', 'label']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"wikidata_properties.xlsx must contain column '{col}'")

    # Ensure strings and strip whitespace
    df = df.copy()
    df['property_id'] = df['property_id'].astype(str).str.strip()
    df['label'] = df['label'].astype(str).str.strip()

    # Check for duplicate property IDs
    if df['property_id'].duplicated().any():
        raise ValueError("Duplicate property IDs found in wikidata_properties.")

    ref_dir = Path(ref_dir)
    ref_dir.mkdir(parents=True, exist_ok=True)
    props_path = ref_dir / "wikidata_properties.xlsx"
    df.to_excel(props_path, index=False)


def save_project_constants(ref_dir, df):
    """Save the project_constants DataFrame to xlsx, validating required columns."""
    required = ['property_id', 'value']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"project_constants.xlsx must contain column '{col}'")

    df = df.copy()
    df['property_id'] = df['property_id'].astype(str).str.strip()
    df['value'] = df['value'].astype(str).str.strip()

    # Optional: could validate QID format here, but validator will handle later.
    ref_dir = Path(ref_dir)
    ref_dir.mkdir(parents=True, exist_ok=True)
    const_path = ref_dir / "project_constants.xlsx"
    df.to_excel(const_path, index=False)
