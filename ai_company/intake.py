from __future__ import annotations

import re
from dataclasses import dataclass

from .acceptance_policy import load_acceptance_policy, match_visual_evidence_profile
from .models import AcceptanceContract

FIGMA_REVIEW_METHOD = "figma-restoration-review"
FIGMA_NODE_ID_PATTERN = re.compile(r"\b\d{2,}:\d+\b")

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


@dataclass(frozen=True)
class IntakeMessage:
    request: str
    raw_message: str
    contract: AcceptanceContract


def extract_request_from_message(message: str) -> str:
    normalized = message.strip()
    if not normalized:
        return ""

    for pattern in TRIGGER_PATTERNS:
        match = pattern.match(normalized)
        if match:
            return match.group("request").strip()

    return normalized


def parse_intake_message(message: str) -> IntakeMessage:
    request = extract_request_from_message(message)
    return IntakeMessage(
        request=request,
        raw_message=message,
        contract=_build_acceptance_contract(message),
    )


def _build_acceptance_contract(message: str) -> AcceptanceContract:
    lowered = message.lower()
    review_method = _detect_review_method(message)
    profile = match_visual_evidence_profile(message) if review_method else None
    if review_method and profile is None:
        profile = load_acceptance_policy().get("evidence_profiles", {}).get("page_root_visual_parity")

    contract = AcceptanceContract(
        review_method=review_method,
        boundary=_detect_boundary(lowered),
        recursive=_detect_recursive(lowered),
        tolerance_px=_detect_tolerance(message),
        required_dimensions=(
            ["Structure", "Geometry", "Style", "Content", "State"] if review_method else []
        ),
        required_artifacts=(
            ["deviation_checklist.md", "review_completion.json"] if review_method else []
        ),
        required_evidence=list(profile.get("required_evidence", [])) if profile else [],
        native_node_policy="miniprogram" if review_method else "",
        allow_host_environment_changes=_detect_environment_change_permission(lowered),
        read_only_review=bool(review_method),
        acceptance_criteria=_extract_acceptance_criteria(message),
    )

    if not contract.boundary and review_method:
        contract.boundary = "page_root"
    if review_method and not contract.tolerance_px and profile:
        contract.tolerance_px = 0.5
    if review_method and not contract.recursive:
        contract.recursive = True
    return contract


def _detect_review_method(message: str) -> str:
    lowered = message.lower()
    if any(token in lowered for token in ("figma-restoration-review", "figma-review")):
        return FIGMA_REVIEW_METHOD

    if "figma" not in lowered:
        return ""

    visual_review_signals = (
        "1:1",
        "视觉验收",
        "视觉还原",
        "fresh reread",
        "重新完整读取",
        "重新读取",
        "读取 figma 节点",
        "figma 节点",
        "node-id",
        "deviation checklist",
        "偏差",
        "overlay diff",
        "runtime screenshot",
        "0.5px",
    )
    if any(signal in lowered for signal in visual_review_signals):
        return FIGMA_REVIEW_METHOD
    if _looks_like_figma_node_restoration(message):
        return FIGMA_REVIEW_METHOD
    return ""


def _looks_like_figma_node_restoration(message: str) -> bool:
    lowered = message.lower()
    if "figma" not in lowered or FIGMA_NODE_ID_PATTERN.search(message) is None:
        return False
    return any(
        token in lowered
        for token in (
            "节点",
            "node",
            "还原",
            "恢复",
            "修正",
            "对齐",
            "样式",
            "restore",
            "parity",
        )
    )


def _detect_boundary(lowered: str) -> str:
    if any(token in lowered for token in ("page-root", "page root", "页面级", "页面根", "page_root")):
        return "page_root"
    return ""


def _detect_recursive(lowered: str) -> bool:
    return any(
        token in lowered
        for token in ("递归", "recursive", "all visible descendants", "所有可见子节点")
    )


def _detect_tolerance(message: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*px", message, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1))


def _detect_environment_change_permission(lowered: str) -> bool:
    if any(
        phrase in lowered
        for phrase in (
            "不允许改本机环境",
            "不允许修改本机配置",
            "不允许重启微信开发者工具",
            "不要修改本机配置",
            "不要改本机环境",
            "do not modify local config",
            "do not restart wechat devtools",
            "without host environment changes",
        )
    ):
        return False
    return any(
        phrase in lowered
        for phrase in (
            "允许重启微信开发者工具",
            "允许修改本机配置",
            "允许改本机环境",
            "可以重启微信开发者工具",
            "可以修改本机配置",
            "allow host environment changes",
            "allow local config changes",
            "allow restarting wechat devtools",
            "may restart wechat devtools",
        )
    )


def _extract_acceptance_criteria(message: str) -> list[str]:
    match = re.search(r"(验收标准|acceptance criteria?)[:：]\s*(?P<body>.+)$", message, re.IGNORECASE | re.DOTALL)
    if not match:
        return []

    body = re.sub(r"\s+", " ", match.group("body")).strip()
    body = re.sub(r"(^|[;；])\s*(\d+)[\.\)、]\s*", r"\1\n\2. ", body)
    items = []
    for chunk in body.splitlines():
        normalized = re.sub(r"^\d+[\.\)、]\s*", "", chunk).strip(" ;；。.")
        if normalized:
            items.append(normalized)

    if len(items) <= 1:
        items = [
            segment.strip(" ;；。.")
            for segment in re.split(r"[;；]", body)
            if segment.strip(" ;；。.")
        ]
        items = [re.sub(r"^\d+[\.\)、]\s*", "", item) for item in items]

    return items
