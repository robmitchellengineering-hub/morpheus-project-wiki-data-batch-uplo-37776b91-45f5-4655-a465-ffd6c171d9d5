import pandas as pd
from pathlib import Path

DEFAULT_PROPERTIES = [
    {"property_id": "P571", "label": "inception"},
    {"property_id": "P17", "label": "country"},
    {"property_id": "P131", "label": "located in the administrative territorial entity"},
    {"property_id": "P625", "label": "coordinate location"},
    {"property_id": "P18", "label": "image"},
    {"property_id": "P31", "label": "instance of"},
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
    return df


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
