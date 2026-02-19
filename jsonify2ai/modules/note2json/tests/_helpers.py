def normalize_text(s: str) -> str:
    # normalize newlines and trim trailing whitespace typical of shell-created files
    return s.replace("\r\n", "\n").rstrip()


def message_startswith(msg: str, prefix: str) -> bool:
    return normalize_text(msg).startswith(prefix)
