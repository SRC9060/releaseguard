import hashlib
import re


_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
_HEX_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]+")
_LINE_COL_RE = re.compile(r":\d+(?::\d+)?\b")


def normalize_stack_trace(stack_trace: str) -> str:
    value = _UUID_RE.sub("<uuid>", stack_trace)
    value = _HEX_ADDRESS_RE.sub("<hex>", value)
    value = _LINE_COL_RE.sub(":<line>", value)
    return value.strip()


def make_fingerprint(exception_type: str, stack_trace: str) -> str:
    normalized = normalize_stack_trace(stack_trace)
    raw = f"{exception_type}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
