import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


class ProjectStructureTests(unittest.TestCase):
    def test_detect_doc_map_uses_existing_project_structure(self) -> None:
        from agent_team.project_structure import detect_doc_map

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "docs" / "prd").mkdir(parents=True)
            (repo_root / "docs" / "tech-design").mkdir(parents=True)

            doc_map = detect_doc_map(repo_root)

        self.assertEqual(doc_map["requirements"], "docs/prd")
        self.assertEqual(doc_map["designs"], "docs/tech-design")

    def test_ensure_project_structure_creates_default_docs_when_missing(self) -> None:
        from agent_team.project_structure import ensure_project_structure

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir)

            structure = ensure_project_structure(repo_root)

            self.assertTrue(structure.used_default_docs)
            self.assertTrue((repo_root / "docs" / "requirements").exists())
            self.assertTrue((repo_root / "docs" / "designs").exists())
            self.assertTrue((repo_root / "agent-team" / "project" / "roles" / "product.context.md").exists())
            self.assertTrue((repo_root / "agent-team" / "project" / "roles" / "techplan.context.md").exists())
            self.assertTrue((repo_root / "agent-team" / "project" / "roles" / "techplan.contract.md").exists())
            self.assertFalse((repo_root / "agent-team" / "project" / "roles" / "ops.context.md").exists())
            doc_map = json.loads((repo_root / "agent-team" / "project" / "doc-map.json").read_text())
            self.assertEqual(doc_map["requirements"], "docs/requirements")

    def test_ensure_project_structure_does_not_shadow_existing_role_context(self) -> None:
        from agent_team.project_structure import ensure_project_structure, resolve_role_context_paths

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "docs" / "prd").mkdir(parents=True)
            (repo_root / "Product").mkdir()
            (repo_root / "Product" / "context.md").write_text("# Product Context\n")

            structure = ensure_project_structure(repo_root)
            paths = resolve_role_context_paths(repo_root, "Product")

            self.assertFalse(structure.used_default_docs)
            self.assertFalse((repo_root / "agent-team" / "project" / "roles" / "product.context.md").exists())
            self.assertEqual(paths.source, "legacy-role-directory")
            self.assertEqual(paths.context_path, repo_root / "Product" / "context.md")

    def test_resolve_role_context_prefers_project_level_role_context(self) -> None:
        from agent_team.project_structure import resolve_role_context_paths

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir)
            roles_dir = repo_root / "agent-team" / "project" / "roles"
            roles_dir.mkdir(parents=True)
            (roles_dir / "dev.context.md").write_text("# Dev Context\n")
            (repo_root / "Dev").mkdir()
            (repo_root / "Dev" / "context.md").write_text("# Legacy Dev Context\n")

            paths = resolve_role_context_paths(repo_root, "Dev")

            self.assertEqual(paths.source, "agent-team-project")
            self.assertEqual(paths.context_path, roles_dir / "dev.context.md")

    def test_load_role_profiles_reads_project_level_role_context(self) -> None:
        from agent_team.roles import load_role_profiles

        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            repo_root = Path(temp_dir)
            state_root = repo_root / ".agent-team-state"
            roles_dir = repo_root / "agent-team" / "project" / "roles"
            roles_dir.mkdir(parents=True)
            (roles_dir / "qa.context.md").write_text("# Project QA Context\n\nVerify project-specific behavior.\n")
            (roles_dir / "qa.contract.md").write_text("# QA Contract\n\nRequire independent evidence.\n")

            roles = load_role_profiles(repo_root=repo_root, state_root=state_root, role_names=("QA",))

            self.assertIn("Project QA Context", roles["QA"].effective_context_text)
            self.assertIn("Require independent evidence.", roles["QA"].effective_skill_text)


if __name__ == "__main__":
    unittest.main()
