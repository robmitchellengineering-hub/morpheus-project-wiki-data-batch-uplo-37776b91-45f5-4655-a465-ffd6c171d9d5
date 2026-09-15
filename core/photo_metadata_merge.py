"""Fill dataset columns from each row's matching photo's EXIF/IPTC metadata.

Matches rows to photo files by filename (see _build_image_index), extracts
each match's metadata via core.metadata_extractor, and writes it into new or
existing columns -- GPS coordinates as a 'lat,lon' string ready for
core.uploader's P625 handling, plus date-taken and camera model for
whichever property a project chooses to map them to.
"""
import os
from pathlib import Path

import pandas as pd

from core.metadata_extractor import extract_image_metadata

GPS_COLUMN = 'GPS Coordinates'
DATE_COLUMN = 'Date Taken'
CAMERA_COLUMN = 'Camera Model'

FIELD_COLUMNS = {
    'gps': GPS_COLUMN,
    'date': DATE_COLUMN,
    'camera': CAMERA_COLUMN,
}


def _build_image_index(image_paths):
    """Map lowercase filename -> full path, keyed by both the full basename
    and its extension-less stem (so a spreadsheet that stores names without
    their extension still matches)."""
    index = {}
    for path in image_paths:
        name = os.path.basename(path)
        index.setdefault(name.lower(), path)
        stem = os.path.splitext(name)[0].lower()
        index.setdefault(stem, path)
    return index


def _format_date(exif_datetime_str):
    """Convert EXIF 'YYYY:MM:DD HH:MM:SS' to an ISO 'YYYY-MM-DD' date string.
    Returns None if the input isn't in the expected EXIF date form."""
    if not exif_datetime_str:
        return None
    try:
        date_part = str(exif_datetime_str).split(' ')[0]
        parts = date_part.split(':')
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return f"{parts[0]}-{parts[1]}-{parts[2]}"
    except Exception:
        pass
    return None


def _cell_is_empty(value):
    return pd.isna(value) or str(value).strip() == ''


def merge_photo_metadata(df, filename_column, image_paths, fields, overwrite=False):
    """Fill columns in df from each row's matching photo's metadata.

    Args:
        df: Source DataFrame (not mutated -- a filled copy is returned).
        filename_column: Name of the column holding each row's photo filename.
        image_paths: Full paths to available photo files (e.g. every image
            found alongside the spreadsheet in the working folder).
        fields: Iterable of field keys to fill -- any of 'gps', 'date', 'camera'.
        overwrite: If True, replace already-populated cells; otherwise only
            empty cells are filled.

    Returns:
        (new_df, summary) -- new_df is a copy of df with the requested
        columns added/filled; summary is a dict of match/fill counts for the
        caller to report to the user.

    Raises:
        ValueError: If filename_column isn't a column in df.
    """
    if filename_column not in df.columns:
        raise ValueError(f"Column '{filename_column}' not found in the dataset.")

    fields = list(fields)
    result_df = df.copy()
    image_index = _build_image_index(image_paths)

    for field in fields:
        col_name = FIELD_COLUMNS.get(field)
        if col_name and col_name not in result_df.columns:
            result_df[col_name] = ''

    matched_photos = 0
    unmatched_rows = 0
    no_gps_count = 0
    filled = {f: 0 for f in fields}

    # Cache metadata extraction per image path in case more than one row
    # references the same photo.
    metadata_cache = {}

    for idx, row in result_df.iterrows():
        raw_name = row.get(filename_column)
        if _cell_is_empty(raw_name):
            unmatched_rows += 1
            continue
        name = str(raw_name).strip()
        image_path = image_index.get(name.lower()) or image_index.get(Path(name).stem.lower())
        if not image_path:
            unmatched_rows += 1
            continue
        matched_photos += 1

        if image_path not in metadata_cache:
            try:
                metadata_cache[image_path] = extract_image_metadata(image_path)
            except Exception:
                metadata_cache[image_path] = {}
        metadata = metadata_cache[image_path]

        if 'gps' in fields:
            lat = metadata.get('GPS_Latitude_Decimal')
            lon = metadata.get('GPS_Longitude_Decimal')
            if lat is not None and lon is not None:
                current = result_df.at[idx, GPS_COLUMN]
                if overwrite or _cell_is_empty(current):
                    result_df.at[idx, GPS_COLUMN] = f"{lat:.6f},{lon:.6f}"
                    filled['gps'] += 1
            else:
                no_gps_count += 1

        if 'date' in fields:
            date_str = _format_date(
                metadata.get('EXIF:DateTimeOriginal') or metadata.get('EXIFREAD:EXIF DateTimeOriginal')
            )
            if date_str:
                current = result_df.at[idx, DATE_COLUMN]
                if overwrite or _cell_is_empty(current):
                    result_df.at[idx, DATE_COLUMN] = date_str
                    filled['date'] += 1

        if 'camera' in fields:
            model = metadata.get('EXIF:Model') or metadata.get('EXIFREAD:Image Model')
            if model:
                current = result_df.at[idx, CAMERA_COLUMN]
                if overwrite or _cell_is_empty(current):
                    result_df.at[idx, CAMERA_COLUMN] = str(model).strip()
                    filled['camera'] += 1

    summary = {
        'total_rows': len(result_df),
        'matched_photos': matched_photos,
        'unmatched_rows': unmatched_rows,
        'no_gps_count': no_gps_count,
        'filled': filled,
        'columns_added': [FIELD_COLUMNS[f] for f in fields if FIELD_COLUMNS.get(f)],
    }
    return result_df, summary


def summary_to_text(summary):
    """Render a merge_photo_metadata summary dict as a short user-facing message."""
    lines = [f"Matched {summary['matched_photos']}/{summary['total_rows']} row(s) to a photo."]
    if summary['unmatched_rows']:
        lines.append(f"{summary['unmatched_rows']} row(s) had no matching photo file.")
    for field, count in summary['filled'].items():
        label = FIELD_COLUMNS.get(field, field)
        lines.append(f"Filled '{label}' for {count} row(s).")
    if 'gps' in summary['filled'] and summary['no_gps_count']:
        lines.append(f"{summary['no_gps_count']} matched photo(s) had no GPS data in their EXIF.")
    return ' '.join(lines)
