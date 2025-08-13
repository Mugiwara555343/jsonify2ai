"""
Encoding utilities for note-to-json.

Provides safe text reading functions that automatically detect and handle
various text encodings including UTF-8, UTF-8 BOM, UTF-16 LE/BE.
"""

from typing import Iterable

PREFERRED_ENCODINGS: tuple[str, ...] = (
    "utf-8",
    "utf-8-sig",
    "utf-16-le",
    "utf-16-be",
    "utf-16",
    "cp1252",
    "latin-1",
)


def decode_bytes(data: bytes, encodings: Iterable[str] = PREFERRED_ENCODINGS) -> str:
    last_err = None
    for enc in encodings:
        try:
            decoded = data.decode(enc)  # no errors="replace"
            # Strip BOM if present (utf-8-sig should handle this, but let's be explicit)
            if decoded.startswith("\ufeff"):
                decoded = decoded[1:]

            # Validate the decoded result - if it contains too many null bytes, it's probably wrong
            # But be more lenient for UTF-16 encodings which naturally have many null bytes
            if len(decoded) > 0:  # Avoid division by zero
                null_ratio = decoded.count("\x00") / len(decoded)
                if null_ratio > 0.1 and enc not in ("utf-16", "utf-16-le", "utf-16-be"):
                    continue  # Try next encoding

            # Additional validation: if this is a UTF-16 encoding, check if the result looks reasonable
            if enc in ("utf-16", "utf-16-le", "utf-16-be"):
                # Check if the result contains mostly printable ASCII characters
                printable_chars = sum(
                    1 for c in decoded if c.isprintable() and ord(c) < 128
                )
                if (
                    printable_chars < len(decoded) * 0.5
                ):  # Less than 50% printable ASCII
                    continue  # Try next encoding

            return decoded
        except UnicodeDecodeError as e:
            last_err = e
            continue
    raise ValueError(
        "Decoding error: input is not valid UTF text (try saving as UTF-8)."
    ) from last_err


def read_text_safely(path):
    with open(path, "rb") as f:
        return decode_bytes(f.read())


def read_stdin_safely(stdin_buffer) -> str:
    data = stdin_buffer.read()
    if isinstance(data, str):
        # Already text (some shells); normalize newline only
        return data
    return decode_bytes(data)
