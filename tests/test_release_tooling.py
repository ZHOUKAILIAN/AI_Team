import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path


class ReleaseToolingTests(unittest.TestCase):
    def test_verify_release_version_accepts_matching_tag(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as temp_dir:
            pyproject = Path(temp_dir) / "pyproject.toml"
            pyproject.write_text('[project]\nname = "agent-team"\nversion = "0.1.0"\n')

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/release/verify_release_version.py",
                    "--tag",
                    "v0.1.0",
                    "--pyproject",
                    str(pyproject),
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0.1.0")

    def test_verify_release_version_accepts_matching_beta_tag(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as temp_dir:
            pyproject = Path(temp_dir) / "pyproject.toml"
            pyproject.write_text('[project]\nname = "agent-team"\nversion = "0.2.0b1"\n')

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/release/verify_release_version.py",
                    "--tag",
                    "v0.2.0b1",
                    "--pyproject",
                    str(pyproject),
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0.2.0b1")

    def test_release_type_outputs_github_args_for_beta_versions(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "scripts/release/release_type.py",
                "--version",
                "0.2.0b1",
                "--github-args",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "--prerelease --latest=false")

    def test_release_type_outputs_no_github_args_for_stable_versions(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "scripts/release/release_type.py",
                "--version",
                "0.2.0",
                "--github-args",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_extract_release_changelog_emits_only_requested_version(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "scripts/release/extract_release_changelog.py",
                "--version",
                "0.2.0b3",
                "--changelog",
                str(repo_root / "CHANGELOG.md"),
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## [0.2.0b3] - 2026-04-26", result.stdout)
        self.assertNotIn("## [Unreleased]", result.stdout)

    def test_render_install_script_embeds_release_coordinates(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "scripts/release/render_install_script.py",
                "--repo",
                "ZHOUKAILIAN/Agent Team",
                "--tag",
                "v0.1.0",
                "--version",
                "0.1.0",
                "--wheel",
                "agent_team-0.1.0-py3-none-any.whl",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('AGENT_TEAM_RELEASE_TAG="${AGENT_TEAM_RELEASE_TAG:-v0.1.0}"', result.stdout)
        self.assertIn("agent_team-0.1.0-py3-none-any.whl", result.stdout)


if __name__ == "__main__":
    unittest.main()
