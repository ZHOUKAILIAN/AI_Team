from __future__ import annotations

import re

TRIGGER_PATTERNS = (
    re.compile(r"^\s*执行这个需求[:：]\s*(?P<request>.+?)\s*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*按\s*AI\s*Company\s*流程跑这个需求[:：]\s*(?P<request>.+?)\s*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*按\s*AI\s*Company\s*流程执行[:：]\s*(?P<request>.+?)\s*$", re.IGNORECASE | re.DOTALL),
    re.compile(
        r"^\s*run\s+this\s+requirement\s+through\s+the\s+ai\s+company\s+workflow[:：]\s*(?P<request>.+?)\s*$",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"^\s*execute\s+this\s+requirement[:：]\s*(?P<request>.+?)\s*$",
        re.IGNORECASE | re.DOTALL,
    ),
)


def extract_request_from_message(message: str) -> str:
    normalized = message.strip()
    if not normalized:
        return ""

    for pattern in TRIGGER_PATTERNS:
        match = pattern.match(normalized)
        if match:
            return match.group("request").strip()

    return normalized
