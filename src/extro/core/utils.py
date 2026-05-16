import datetime


def ms_epoch_to_iso8601(epoch_ms_str: str) -> str:
    """
    Converts a milliseconds epoch timestamp to an ISO 8601 string in UTC.
    """
    # Ensure the input is treated as an integer
    epoch_ms_int = int(epoch_ms_str)

    # Convert milliseconds to seconds for fromtimestamp()
    epoch_sec = epoch_ms_int / 1000.0

    # Create a timezone-aware datetime object in UTC
    dt = datetime.datetime.fromtimestamp(epoch_sec, tz=datetime.UTC)

    # Format to ISO 8601.
    # timespec='milliseconds' ensures exactly 3 digits for fractions of a second.
    # We replace Python's default '+00:00' UTC offset with 'Z'.
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
