import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent_team.skill_registry import SkillPreferences, SkillRegistry, skill_injection_text


class SkillRegistryTests(unittest.TestCase):
    def test_discovers_builtin_skills_by_stage(self) -> None:
        with TemporaryDirectory() as temp_dir:
            registry = SkillRegistry(Path(temp_dir))

            dev_skills = registry.list_skills(stage="Dev")
            qa_skills = registry.list_skills(stage="QA")

        self.assertIn("plan", {skill.name for skill in dev_skills})
        self.assertIn("security-audit", {skill.name for skill in qa_skills})

    def test_project_skill_overrides_builtin_by_name(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            skill_dir = repo_root / "Dev" / "skills" / "plan"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                """---
name: plan
description: Project plan
---

# Project Plan
"""
            )
            registry = SkillRegistry(repo_root)

            skill = registry.get_skill("plan", stage="Dev")

        self.assertIsNotNone(skill)
        assert skill is not None
        self.assertEqual(skill.source, "project")
        self.assertIn("Project Plan", skill.content)

    def test_personal_skill_path_is_supported(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory() as personal_dir:
            skill_dir = Path(personal_dir) / "cst"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: cst
description: Customer troubleshooting
stage: QA
---

# CST
"""
            )
            with patch.dict(os.environ, {"AGENT_TEAM_SKILL_PATH": personal_dir}):
                registry = SkillRegistry(Path(temp_dir))
                skills = registry.list_skills(stage="QA", source="personal")

        self.assertEqual([skill.name for skill in skills], ["cst"])

    def test_preferences_record_last_and_frequency(self) -> None:
        with TemporaryDirectory() as temp_dir:
            registry = SkillRegistry(Path(temp_dir))
            registry.record("Dev", ["plan"])
            registry.record("Dev", ["plan"])

            prefs = registry.load_preferences()

        self.assertEqual(prefs.last["dev"], ["plan"])
        self.assertEqual(prefs.frequent["dev"]["plan"], 2)
        self.assertFalse(prefs.is_first_time)

    def test_empty_selection_still_initializes_preferences(self) -> None:
        with TemporaryDirectory() as temp_dir:
            registry = SkillRegistry(Path(temp_dir))
            registry.record("Dev", [])

            prefs = registry.load_preferences()

        self.assertTrue(prefs.initialized)
        self.assertFalse(prefs.is_first_time)

    def test_skill_injection_text_omits_empty_layer(self) -> None:
        self.assertEqual(skill_injection_text([]), "")

    def test_skill_preferences_format_last_uses_defaults_first(self) -> None:
        prefs = SkillPreferences()
        prefs.last["dev"] = ["last"]
        prefs.defaults["dev"] = ["default"]

        self.assertEqual(prefs.format_last("Dev"), "default")

    def test_load_preferences_accepts_inline_yaml_lists(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            pref_path = repo_root / ".agent-team" / "skill-preferences.yaml"
            pref_path.parent.mkdir()
            pref_path.write_text(
                """initialized: true
dev:
  last: [plan]
  defaults: [refactor-checklist]
  frequent:
    plan: 3
"""
            )
            registry = SkillRegistry(repo_root)

            prefs = registry.load_preferences()

        self.assertTrue(prefs.initialized)
        self.assertEqual(prefs.last["dev"], ["plan"])
        self.assertEqual(prefs.defaults["dev"], ["refactor-checklist"])
        self.assertEqual(prefs.frequent["dev"]["plan"], 3)


if __name__ == "__main__":
    unittest.main()
