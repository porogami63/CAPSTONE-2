"""Helpers for safe CSV exports (spreadsheet formula-injection protection)."""

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_csv_cell(value):
    """Prefix text cells that a spreadsheet could interpret as a formula with a single quote.

    Numbers (int/float/Decimal) are left untouched so exports stay numerically usable.
    """
    if isinstance(value, str) and value and value.startswith(_DANGEROUS_PREFIXES):
        # A bare "—" placeholder or a negative number written as text should remain readable.
        try:
            float(value.replace(",", ""))
            return value
        except ValueError:
            return "'" + value
    return value


def safe_csv_row(row):
    return [safe_csv_cell(cell) for cell in row]
