import re
from typing import Tuple, List, Dict


class PIIMasker:
    PATTERNS: Dict[str, re.Pattern] = {
        "API_KEY": re.compile(
            r"\b(?:AIza[0-9A-Za-z\-_]{35}|sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{30,}|AKIA[0-9A-Z]{16})\b"
        ),
        "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "CREDIT_CARD": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
        "GOV_ID": re.compile(r"\b(?:\d{3}-\d{2}-\d{4}|\d{4}\s?\d{4}\s?\d{4}|[A-Z]{5}[0-9]{4}[A-Z])\b"),
        "PHONE": re.compile(r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"),
        "IP_ADDRESS": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    }

    @classmethod
    def inspect(cls, text: str) -> List[str]:
        detected_types: List[str] = []
        for entity_type, pattern in cls.PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                detected_types.append(f"{entity_type} ({len(matches)})")
        return detected_types

    @classmethod
    def sanitize(cls, text: str) -> Tuple[str, List[str]]:
        sanitized = text
        detected_types: List[str] = []

        for entity_type, pattern in cls.PATTERNS.items():
            matches = pattern.findall(sanitized)
            if matches:
                detected_types.append(f"{entity_type} ({len(matches)})")
                sanitized = pattern.sub(f"[{entity_type}_REDACTED]", sanitized)

        return sanitized, detected_types