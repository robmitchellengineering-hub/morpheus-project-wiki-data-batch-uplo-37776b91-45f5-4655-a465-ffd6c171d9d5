import os
from pathlib import Path
from typing import Dict, Any

import exifread
from PIL import Image, IptcImagePlugin, ExifTags

SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.tif', '.tiff', '.png'}


def extract_image_metadata(file_path: str) -> Dict[str, Any]:
    """Extract metadata from an image file.

    Uses exifread for JPEG/TIFF (full EXIF including GPS),
    and Pillow for basic info, EXIF (if present), IPTC, and PNG textual chunks.
    Returns a dictionary of metadata tags. Empty dict if none found.

    Args:
        file_path: Path to the image file.

    Returns:
        dict: Metadata key-value pairs.

    Raises:
        FileNotFoundError: If file does not exist.
        ValueError: If file extension is not supported.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image format: {ext}")

    metadata = {}

    # --- Pillow-based extraction (basic info, EXIF, IPTC, PNG text) ---
    try:
        with Image.open(file_path) as img:
            metadata['Format'] = img.format or 'Unknown'
            metadata['Mode'] = img.mode
            metadata['Size'] = f'{img.width}x{img.height}'

            # EXIF (Pillow reads EXIF from JPEG/TIFF and eXIf from PNG)
            exif_data = img.getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    metadata[f'EXIF:{tag_name}'] = str(value)

            # IPTC
            iptc = IptcImagePlugin.getiptcinfo(img)
            if iptc:
                for tag, value in iptc.items():
                    if isinstance(value, bytes):
                        try:
                            value = value.decode('utf-8', errors='replace')
                        except Exception:
                            value = str(value)
                    metadata[f'IPTC:{tag}'] = str(value)
    except Exception:
        # Do not fail entire extraction if Pillow fails; exifread may still work for JPEG/TIFF
        pass

    # --- exifread-based extraction (detailed for JPEG/TIFF) ---
    if ext in ('.jpg', '.jpeg', '.tif', '.tiff'):
        try:
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
                if tags:
                    # Copy raw tags, and compute decimal GPS if available
                    for key, value in tags.items():
                        metadata[f'EXIFREAD:{key}'] = str(value)

                    # Compute combined GPS decimal coordinates
                    if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
                        try:
                            lat = _convert_to_decimal(tags['GPS GPSLatitude'])
                            lon = _convert_to_decimal(tags['GPS GPSLongitude'])
                            ref_lat = str(tags.get('GPS GPSLatitudeRef', 'N')).upper()
                            ref_lon = str(tags.get('GPS GPSLongitudeRef', 'E')).upper()
                            if ref_lat == 'S':
                                lat = -lat
                            if ref_lon == 'W':
                                lon = -lon
                            metadata['GPS_Latitude_Decimal'] = lat
                            metadata['GPS_Longitude_Decimal'] = lon
                        except Exception:
                            # If conversion fails, keep raw values only
                            pass
        except Exception:
            # Ignore exifread errors; Pillow may have already extracted something
            pass

    return metadata


def _convert_to_decimal(value) -> float:
    """Convert an exifread GPS DMS value to decimal degrees.

    Handles exifread Ratio objects or a string like "31 13 48.00".
    """
    if hasattr(value, 'values'):
        vals = value.values
        if len(vals) != 3:
            raise ValueError(f"Unexpected GPS value: {value}")
        degrees = float(vals[0].num) / float(vals[0].den)
        minutes = float(vals[1].num) / float(vals[1].den)
        seconds = float(vals[2].num) / float(vals[2].den)
        return degrees + minutes / 60.0 + seconds / 3600.0
    elif hasattr(value, 'num') and hasattr(value, 'den'):
        return float(value.num) / float(value.den)
    else:
        parts = str(value).split()
        try:
            if len(parts) == 2:
                d = float(parts[0])
                m = float(parts[1])
                return d + m / 60.0
            elif len(parts) == 3:
                d = float(parts[0])
                m = float(parts[1])
                s = float(parts[2])
                return d + m / 60.0 + s / 3600.0
            else:
                raise ValueError
        except (ValueError, IndexError):
            raise ValueError(f"Cannot convert to decimal: {value}")
