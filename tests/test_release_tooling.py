import subprocess
import sys
import unittest
from pathlib import Path


class ReleaseToolingTests(unittest.TestCase):
    def test_verify_release_version_accepts_matching_tag(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "scripts/release/verify_release_version.py", "--tag", "v0.1.0"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0.1.0")

    def test_extract_release_changelog_emits_only_requested_version(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "scripts/release/extract_release_changelog.py",
                "--version",
                "0.1.0",
                "--changelog",
                str(repo_root / "CHANGELOG.md"),
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## [0.1.0] - 2026-04-19", result.stdout)
        self.assertNotIn("## [Unreleased]", result.stdout)

    def test_render_install_script_embeds_release_coordinates(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "scripts/release/render_install_script.py",
                "--repo",
                "ZHOUKAILIAN/AI_Team",
                "--tag",
                "v0.1.0",
                "--version",
                "0.1.0",
                "--wheel",
                "ai_company-0.1.0-py3-none-any.whl",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('AI_TEAM_RELEASE_TAG="${AI_TEAM_RELEASE_TAG:-v0.1.0}"', result.stdout)
        self.assertIn("ai_company-0.1.0-py3-none-any.whl", result.stdout)


if __name__ == "__main__":
    unittest.main()
