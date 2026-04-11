from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_POLICY_PATH = Path(__file__).with_name("acceptance_policy.json")


@lru_cache(maxsize=1)
def load_acceptance_policy(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_POLICY_PATH
    return json.loads(target.read_text())


def match_visual_evidence_profile(report: str) -> dict[str, Any] | None:
    lowered = report.lower()
    policy = load_acceptance_policy()
    for profile in policy.get("evidence_profiles", {}).values():
        matchers = profile.get("matchers", [])
        if any(matcher.lower() in lowered for matcher in matchers):
            return profile
    return None
