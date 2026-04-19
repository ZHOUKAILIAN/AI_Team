from __future__ import annotations

from pathlib import Path

from .models import RoleProfile
from .packaged_assets import packaged_text

DEFAULT_ROLE_NAMES = ("Product", "Dev", "QA", "Acceptance", "Ops")


def load_role_profiles(
    repo_root: Path,
    state_root: Path | None = None,
    role_names: tuple[str, ...] = DEFAULT_ROLE_NAMES,
) -> dict[str, RoleProfile]:
    profiles: dict[str, RoleProfile] = {}

    for role_name in role_names:
        role_dir = repo_root / role_name
        context_path = role_dir / "context.md"
        memory_path = role_dir / "memory.md"
        skill_path = role_dir / "SKILL.md"
        learning_dir = (state_root / "memory" / role_name) if state_root else None
        if role_dir.exists():
            base_context_text = _read_text(context_path)
            base_memory_text = _read_text(memory_path)
            base_skill_text = _read_text(skill_path)
        else:
            base_context_text = packaged_text("roles", role_name, "context.md")
            base_memory_text = packaged_text("roles", role_name, "memory.md")
            base_skill_text = packaged_text("roles", role_name, "SKILL.md")

        profiles[role_name] = RoleProfile(
            name=role_name,
            role_dir=role_dir,
            context_path=context_path,
            memory_path=memory_path,
            skill_path=skill_path,
            base_context_text=base_context_text,
            base_memory_text=base_memory_text,
            base_skill_text=base_skill_text,
            learned_context_text=_read_text(learning_dir / "context_patch.md") if learning_dir else "",
            learned_memory_text=_read_text(learning_dir / "lessons.md") if learning_dir else "",
            learned_skill_text=_read_text(learning_dir / "skill_patch.md") if learning_dir else "",
        )

    return profiles


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""

    return path.read_text()
