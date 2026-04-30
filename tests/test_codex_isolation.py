import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_team.codex_isolation import prepare_isolated_codex_home, sanitize_codex_config


class CodexIsolationTests(unittest.TestCase):
    def test_sanitize_codex_config_removes_prompt_injection_surfaces(self) -> None:
        config = """
model_provider = "local"

[model_providers.local]
base_url = "https://example.test/v1"

[mcp_servers.apifox]
command = "npx"
args = ["apifox"]

[mcp_servers.apifox.env]
TOKEN = "secret"

[plugins."documents@openai-primary-runtime"]
enabled = true

[marketplaces.openai-primary-runtime]
enabled = true

[[skills.config]]
name = "superpowers:using-superpowers"
path = "/Users/example/.codex/superpowers/skills/using-superpowers/SKILL.md"

[projects."/repo"]
trust_level = "trusted"
"""

        sanitized = sanitize_codex_config(config)

        self.assertIn('model_provider = "local"', sanitized)
        self.assertIn("[model_providers.local]", sanitized)
        self.assertIn("[projects.\"/repo\"]", sanitized)
        self.assertNotIn("mcp_servers", sanitized)
        self.assertNotIn("plugins", sanitized)
        self.assertNotIn("marketplaces", sanitized)
        self.assertNotIn("skills.config", sanitized)
        self.assertNotIn("secret", sanitized)
        self.assertNotIn("superpowers", sanitized)

    def test_prepare_isolated_codex_home_copies_auth_and_sanitizes_config(self) -> None:
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as target_dir:
            source_home = Path(source_dir)
            target_home = Path(target_dir)
            (source_home / "auth.json").write_text('{"token":"redacted"}')
            (source_home / "config.toml").write_text(
                'model_provider = "local"\n\n[mcp_servers.apifox]\ncommand = "npx"\n'
            )

            prepare_isolated_codex_home(source_home=source_home, target_home=target_home)

            self.assertEqual((target_home / "auth.json").read_text(), '{"token":"redacted"}')
            self.assertIn('model_provider = "local"', (target_home / "config.toml").read_text())
            self.assertNotIn("mcp_servers", (target_home / "config.toml").read_text())


if __name__ == "__main__":
    unittest.main()
