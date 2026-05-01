from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import model_dataclass
from .packaged_assets import packaged_text


DEFAULT_DOC_MAP = {
    "requirements": "docs/requirements",
    "designs": "docs/designs",
    "workflow_specs": "docs/workflow-specs",
    "standards": "docs/standards",
}

DOC_CANDIDATES = {
    "requirements": (
        "docs/requirements",
        "docs/requirement",
        "docs/prd",
        "docs/prds",
        "requirements",
    ),
    "designs": (
        "docs/designs",
        "docs/design",
        "docs/technical-design",
        "docs/tech-design",
        "docs/architecture",
        "designs",
    ),
    "workflow_specs": (
        "docs/workflow-specs",
        "docs/workflow",
        "docs/workflows",
    ),
    "standards": (
        "docs/standards",
        "docs/guidelines",
        "docs/conventions",
    ),
}

ROLE_SLUGS = {
    "Product": "product",
    "Dev": "dev",
    "QA": "qa",
    "Acceptance": "acceptance",
    "Ops": "ops",
}


@model_dataclass
class RoleContextPaths:
    role_name: str
    role_dir: Path
    context_path: Path
    memory_path: Path
    guidance_path: Path
    source: str


@model_dataclass
class ProjectStructure:
    repo_root: Path
    agent_team_root: Path
    project_root: Path
    doc_map_path: Path
    doc_map: dict[str, str]
    used_default_docs: bool

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["repo_root"] = str(self.repo_root)
        payload["agent_team_root"] = str(self.agent_team_root)
        payload["project_root"] = str(self.project_root)
        payload["doc_map_path"] = str(self.doc_map_path)
        return payload


def detect_project_structure(repo_root: Path) -> ProjectStructure:
    repo_root = repo_root.resolve()
    agent_team_root = repo_root / "agent-team"
    project_root = agent_team_root / "project"
    doc_map_path = project_root / "doc-map.json"
    existing_doc_map = _read_doc_map(doc_map_path)
    if existing_doc_map:
        doc_map = existing_doc_map
        used_default_docs = False
    else:
        doc_map = detect_doc_map(repo_root)
        used_default_docs = not doc_map
        if used_default_docs:
            doc_map = dict(DEFAULT_DOC_MAP)

    return ProjectStructure(
        repo_root=repo_root,
        agent_team_root=agent_team_root,
        project_root=project_root,
        doc_map_path=doc_map_path,
        doc_map=doc_map,
        used_default_docs=used_default_docs,
    )


def detect_doc_map(repo_root: Path) -> dict[str, str]:
    repo_root = repo_root.resolve()
    detected: dict[str, str] = {}
    for key, candidates in DOC_CANDIDATES.items():
        for candidate in candidates:
            path = repo_root / candidate
            if path.exists() and path.is_dir():
                detected[key] = candidate
                break
    return detected


def ensure_project_structure(repo_root: Path) -> ProjectStructure:
    structure = detect_project_structure(repo_root)
    structure.project_root.mkdir(parents=True, exist_ok=True)

    if structure.used_default_docs:
        for relative_path in DEFAULT_DOC_MAP.values():
            (structure.repo_root / relative_path).mkdir(parents=True, exist_ok=True)
        structure.doc_map = dict(DEFAULT_DOC_MAP)

    _write_doc_map(structure.doc_map_path, structure.doc_map)
    _ensure_text(structure.project_root / "context.md", "# Project Context\n\nDescribe the project-level context here.\n")
    _ensure_text(structure.project_root / "rules.md", "# Project Rules\n\nAdd project-level Agent Team rules here.\n")
    if structure.used_default_docs:
        roles_dir = structure.project_root / "roles"
        roles_dir.mkdir(parents=True, exist_ok=True)
        for role_name, slug in ROLE_SLUGS.items():
            _ensure_text(
                roles_dir / f"{slug}.context.md",
                packaged_text("roles", role_name, "context.md"),
            )
            _ensure_text(
                roles_dir / f"{slug}.memory.md",
                packaged_text("roles", role_name, "memory.md"),
            )
            _ensure_text(
                roles_dir / f"{slug}.contract.md",
                packaged_text("roles", role_name, "SKILL.md"),
            )
    return structure


def resolve_role_context_paths(repo_root: Path, role_name: str) -> RoleContextPaths:
    repo_root = repo_root.resolve()
    slug = ROLE_SLUGS.get(role_name, role_name.lower())
    agent_team_roles_dir = repo_root / "agent-team" / "project" / "roles"
    agent_team_context_path = agent_team_roles_dir / f"{slug}.context.md"
    if agent_team_context_path.exists():
        return RoleContextPaths(
            role_name=role_name,
            role_dir=agent_team_roles_dir,
            context_path=agent_team_context_path,
            memory_path=agent_team_roles_dir / f"{slug}.memory.md",
            guidance_path=agent_team_roles_dir / f"{slug}.contract.md",
            source="agent-team-project",
        )

    legacy_role_dir = repo_root / role_name
    if legacy_role_dir.exists():
        return RoleContextPaths(
            role_name=role_name,
            role_dir=legacy_role_dir,
            context_path=legacy_role_dir / "context.md",
            memory_path=legacy_role_dir / "memory.md",
            guidance_path=legacy_role_dir / "SKILL.md",
            source="legacy-role-directory",
        )

    packaged_role_dir = repo_root / role_name
    return RoleContextPaths(
        role_name=role_name,
        role_dir=packaged_role_dir,
        context_path=packaged_role_dir / "context.md",
        memory_path=packaged_role_dir / "memory.md",
        guidance_path=packaged_role_dir / "SKILL.md",
        source="packaged",
    )


def _read_doc_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if isinstance(value, str)}


def _write_doc_map(path: Path, doc_map: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc_map, indent=2, sort_keys=True) + "\n")


def _ensure_text(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
