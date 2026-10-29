"""Conservative unit parsers for candidate text documented by the design brief.

No parser currently creates a decision or RTT: the firmware sources and exact
wire formats were not available to verify those fields.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ParseResult:
    kind: str
    format_verified: bool = False


def sanitize_diagnostic(text: str, limit: int = 400) -> str:
    """Bound and redact likely credential material before it enters app state."""
    value = text.replace("\x00", "")
    value = re.sub(r"(?i)\b(secret|psk|hmac|proof|credential|password|passphrase|card[_ -]?key|key)\b.*$",
                   r"\1=<redacted>", value)
    value = re.sub(r"\b(?:[0-9a-fA-F]{12,}|[A-Za-z0-9+/=_-]{40,})\b", "<redacted-token>", value)
    value = re.sub(r"\b(?:[0-9a-fA-F]{2}[:-]){5,}[0-9a-fA-F]{2}\b", "<redacted-token>", value)
    value = re.sub(r"(?i)\b(uid)\b\s*[:=]\s*[^\s,;]+", r"\1=<masked>", value)
    return value[:limit]


class UnitMessageParser:
    def classify(self, line: str) -> ParseResult:
        return ParseResult("unclassified")


class UnitAParser(UnitMessageParser):
    def classify(self, line: str) -> ParseResult:
        folded = line.strip().casefold()
        if folded.startswith("decision for"):
            return ParseResult("decision-format-candidate")
        if folded.startswith("[calib]"):
            return ParseResult("calibration-format-candidate")
        return ParseResult("unclassified")


class UnitBParser(UnitMessageParser):
    def classify(self, line: str) -> ParseResult:
        if line.strip().casefold() == "pn532 ready":
            return ParseResult("reader-ready-format-candidate")
        return ParseResult("unclassified")


class UnitCParser(UnitMessageParser):
    def classify(self, line: str) -> ParseResult:
        if line.strip().casefold().startswith("relay status: connected"):
            return ParseResult("relay-status-format-candidate")
        return ParseResult("unclassified")
