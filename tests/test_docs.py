import unittest
from pathlib import Path


class DocsTests(unittest.TestCase):
    def test_readme_positions_project_as_cli_runtime_framework(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        readme = (repo_root / "README.md").read_text()

        self.assertIn("# Agent Team CLI Runtime", readme)
        self.assertIn("CLI-first", readme)
        self.assertIn("orchestration runtime", readme)
        self.assertIn("可自我进化", readme)
        self.assertIn("Product / Dev / QA / Acceptance", readme)

    def test_readme_documents_agent_team_cli_usage(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        readme = (repo_root / "README.md").read_text()

        self.assertIn("releases/latest/download/install.sh", readme)
        self.assertIn("releases/download/v0.1.0/install.sh", readme)
        self.assertIn("Python 3.13+", readme)
        self.assertIn("CHANGELOG.md", readme)
        self.assertIn("agent-team start-session", readme)
        self.assertIn("agent-team current-stage", readme)
        self.assertIn("agent-team build-stage-contract", readme)
        self.assertIn("agent-team submit-stage-result", readme)
        self.assertIn("agent-team record-human-decision", readme)
        self.assertIn("agent-team board-snapshot", readme)
        self.assertIn("agent-team serve-board", readme)

    def test_readme_keeps_authoritative_team_workflow_contract(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        readme = (repo_root / "README.md").read_text()

        self.assertIn("Product -> CEO approval -> Dev <-> QA -> Acceptance -> human Go/No-Go", readme)
        self.assertIn("QA", readme)
        self.assertIn("Acceptance", readme)
        self.assertIn("human Go/No-Go", readme)

    def test_runtime_docs_use_cli_runtime_naming(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        design_doc = (
            repo_root / "docs" / "workflow-specs" / "2026-04-11-agent-team-cli-runtime-design.md"
        ).read_text()
        flow_doc = (
            repo_root / "docs" / "workflow-specs" / "2026-04-11-agent-team-cli-runtime-flow.md"
        ).read_text()
        usage_doc = (
            repo_root / "docs" / "workflow-specs" / "2026-04-11-agent-team-cli-runtime-usage.md"
        ).read_text()

        self.assertIn("Agent Team CLI Runtime", design_doc)
        self.assertIn("Agent Team CLI Runtime", flow_doc)
        self.assertIn("Agent Team CLI Runtime", usage_doc)
        self.assertIn("agent-team start-session", flow_doc)
        self.assertIn("agent-team start-session", usage_doc)
        self.assertIn("releases/latest/download/install.sh", usage_doc)
        self.assertIn("releases/download/v0.1.0/install.sh", usage_doc)

    def test_release_workflows_define_ci_and_tag_release(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        ci_workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text()
        release_workflow = (repo_root / ".github" / "workflows" / "release.yml").read_text()
        release_config = (repo_root / ".github" / "release.yml").read_text()

        self.assertIn("python-version: \"3.13\"", ci_workflow)
        self.assertIn("python -m unittest discover -s tests", ci_workflow)
        self.assertIn("python -m build", ci_workflow)
        self.assertIn("tags:", release_workflow)
        self.assertIn("\"v*\"", release_workflow)
        self.assertIn("contents: write", release_workflow)
        self.assertIn("verify_release_version.py", release_workflow)
        self.assertIn("render_install_script.py", release_workflow)
        self.assertIn("SHA256SUMS", release_workflow)
        self.assertIn("Packaging", release_config)

    def test_codex_help_and_skill_integration_docs_exist(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        codex_help = (
            repo_root / "docs" / "workflow-specs" / "2026-04-11-agent-team-codex-cli-help.md"
        ).read_text()
        skill_integration = (
            repo_root / "docs" / "workflow-specs" / "2026-04-11-agent-team-skill-integration.md"
        ).read_text()
        codex_harness = (
            repo_root / "docs" / "workflow-specs" / "2026-04-11-agent-team-codex-harness-solution.md"
        ).read_text()
        readme = (repo_root / "README.md").read_text()

        self.assertIn("Codex App", codex_help)
        self.assertIn("agent-team start-session", codex_help)
        self.assertIn("agent-team build-stage-contract", codex_help)
        self.assertIn("agent-team submit-stage-result", codex_help)
        self.assertIn("agent-team record-feedback", codex_help)
        self.assertIn("最小 harness 循环", codex_help)
        self.assertIn("Skill Standard", skill_integration)
        self.assertIn("Goal", skill_integration)
        self.assertIn("Available assets", skill_integration)
        self.assertIn("Completion Signals", skill_integration)
        self.assertIn("skill 是入口，不是流程控制器", skill_integration)
        self.assertIn("Codex-only", codex_harness)
        self.assertIn("runtime-first", codex_harness)
        self.assertIn("agent-team step", codex_harness)
        self.assertIn("M0", codex_harness)
        self.assertIn("M1", codex_harness)
        self.assertIn("M2", codex_harness)
        self.assertIn("Codex 运行 Help", readme)
        self.assertIn("Skill 接入说明", readme)
        self.assertIn("Codex Harness 方案", readme)

    def test_removed_legacy_docs_are_gone(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        self.assertFalse((repo_root / "README_zh.md").exists())
        self.assertFalse((repo_root / "docs" / "SOP_简洁版.md").exists())
        self.assertFalse(
            (repo_root / "docs" / "workflow-specs" / "2026-04-11-agent-team-codex-harness-design.md").exists()
        )
        self.assertFalse(
            (repo_root / "docs" / "workflow-specs" / "2026-04-11-agent-team-harness-first-current-flow.md").exists()
        )
        self.assertFalse(
            (repo_root / "docs" / "workflow-specs" / "2026-04-11-agent-team-harness-first-usage-guide.md").exists()
        )


if __name__ == "__main__":
    unittest.main()
