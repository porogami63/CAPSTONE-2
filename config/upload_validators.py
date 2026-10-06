"""Reusable upload validators (extension allow-list + size cap + magic-byte check).

These are called from forms/views rather than attached to model fields so that no
schema migration is required on the deployed database.
"""

from pathlib import Path

from django.core.exceptions import ValidationError

MB = 1024 * 1024

DOCUMENT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SPREADSHEET_EXTENSIONS = {".xlsx", ".xlsm"}
LEGACY_SPREADSHEET_EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".csv"}

DOCUMENT_MAX_BYTES = 10 * MB
IMAGE_MAX_BYTES = 5 * MB
SPREADSHEET_MAX_BYTES = 10 * MB


def _sniff_extension(header: bytes):
    """Return the canonical extension implied by the file's leading bytes, or None."""
    if header.startswith(b"%PDF-"):
        return ".pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return ".webp"
    if header.startswith(b"PK\x03\x04"):
        return ".xlsx"  # OOXML zip container (xlsx/xlsm)
    if header.startswith(b"\xd0\xcf\x11\xe0"):
        return ".xls"
    return None


def _equivalent(ext: str, sniffed: str) -> bool:
    groups = [{".jpg", ".jpeg"}, {".xlsx", ".xlsm"}]
    if ext == sniffed:
        return True
    return any(ext in g and sniffed in g for g in groups)


def validate_upload(file_obj, *, allowed_extensions, max_bytes, label="File"):
    """Validate a Django UploadedFile. Raises ValidationError on failure."""
    if not file_obj:
        return file_obj

    name = getattr(file_obj, "name", "") or ""
    ext = Path(name).suffix.lower()
    pretty = ", ".join(sorted(allowed_extensions))

    if ext not in allowed_extensions:
        raise ValidationError(f"{label}: unsupported file type '{ext or 'none'}'. Allowed: {pretty}.")

    size = getattr(file_obj, "size", 0) or 0
    if size > max_bytes:
        raise ValidationError(f"{label}: file is {size / MB:.1f} MB, which exceeds the {max_bytes // MB} MB limit.")
    if size == 0:
        raise ValidationError(f"{label}: the uploaded file is empty.")

    # CSV is plain text and has no magic bytes: only enforce that it is not a binary/HTML payload.
    if ext == ".csv":
        head = file_obj.read(2048)
        file_obj.seek(0)
        if b"\x00" in head or head.lstrip().lower().startswith((b"<!doctype", b"<html", b"<script", b"<svg")):
            raise ValidationError(f"{label}: file content does not look like a CSV.")
        return file_obj

    head = file_obj.read(16)
    file_obj.seek(0)
    sniffed = _sniff_extension(head)
    if sniffed is None or not _equivalent(ext, sniffed):
        raise ValidationError(f"{label}: file content does not match its '{ext}' extension.")
    return file_obj


def validate_document_upload(file_obj, label="Document"):
    return validate_upload(file_obj, allowed_extensions=DOCUMENT_EXTENSIONS, max_bytes=DOCUMENT_MAX_BYTES, label=label)


def validate_image_upload(file_obj, label="Image"):
    return validate_upload(file_obj, allowed_extensions=IMAGE_EXTENSIONS, max_bytes=IMAGE_MAX_BYTES, label=label)


def validate_spreadsheet_upload(file_obj, label="Workbook", legacy=False):
    exts = LEGACY_SPREADSHEET_EXTENSIONS if legacy else SPREADSHEET_EXTENSIONS
    return validate_upload(file_obj, allowed_extensions=exts, max_bytes=SPREADSHEET_MAX_BYTES, label=label)
