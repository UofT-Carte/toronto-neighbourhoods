import re

_POSSESSIVE = re.compile(r"'s\b|'s\b|s'\b")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_LEADING_THE = re.compile(r"^the\s+")


def normalize_name(raw: str) -> str:
    s = (raw or "").lower().strip()
    s = s.replace("&", " and ")
    s = _POSSESSIVE.sub("", s)
    s = _NON_ALNUM.sub(" ", s)          # punctuation -> space
    s = re.sub(r"\s+", " ", s).strip()
    s = _LEADING_THE.sub("", s)
    return s
