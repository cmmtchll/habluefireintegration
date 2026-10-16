"""Configuration validation shared by manual and discovered-device setup."""

import re


def normalize_address(value: str) -> str:
    """Return a canonical Bluetooth MAC, rejecting malformed addresses."""
    value = value.strip()
    if not re.fullmatch(
        r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}"
        r"|(?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2}"
        r"|[0-9a-fA-F]{12}",
        value,
    ):
        raise ValueError("Invalid Bluetooth MAC address")
    compact = value.replace(":", "").replace("-", "").upper()
    if compact in {"000000000000", "FFFFFFFFFFFF"}:
        raise ValueError("Expected an individual Bluetooth device address")
    return ":".join(compact[index:index + 2] for index in range(0, 12, 2))
