import hashlib
import functools
import http.server
import os
import socketserver
import subprocess
import sys
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


def local_temp_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_tmp"
    path.mkdir(exist_ok=True)
    return path


def write_sha256sums(directory: Path) -> None:
    lines: list[str] = []
    for path in sorted(directory.iterdir()):
        if path.name == "SHA256SUMS" or path.is_dir():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def build_fake_release_fixture(*, root: Path, repo_root: Path, version: str, broken: bool) -> Path:
    project_root = root / "fake-project"
    package_dir = project_root / "fake_pkg"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("")
    exit_code = "1" if broken else "0"
    (package_dir / "cli.py").write_text(
        "from __future__ import annotations\n\n"
        "import sys\n\n"
        "def main() -> int:\n"
        "    if '--help' in sys.argv:\n"
        f"        print('fake agent-team {version}')\n"
        f"        return {exit_code}\n"
        "    return 0\n"
    )
    (project_root / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'agent-team'\n"
        f"version = '{version}'\n"
        "requires-python = '>=3.13'\n\n"
        "[project.scripts]\n"
        "agent-team = 'fake_pkg.cli:main'\n\n"
        "[build-system]\n"
        "requires = ['setuptools>=68']\n"
        "build-backend = 'setuptools.build_meta'\n\n"
        "[tool.setuptools]\n"
        "packages = ['fake_pkg']\n"
    )

    release_dir = root / "release"
    release_dir.mkdir()
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(project_root), "--no-deps", "-w", str(release_dir)],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    write_sha256sums(release_dir)
    return release_dir


@contextmanager
def release_server(root: Path):
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

    handler = functools.partial(QuietHandler, directory=str(root))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            thread.join()


def render_install_script(repo_root: Path, wheel_name: str) -> str:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/release/render_install_script.py",
            "--repo",
            "ZHOUKAILIAN/agent-team-runtime",
            "--tag",
            "v0.1.0",
            "--version",
            "0.1.0",
            "--wheel",
            wheel_name,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout


class ReleaseInstallScriptTests(unittest.TestCase):
    def test_install_script_allows_runtime_dependency_resolution(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        install_script = render_install_script(repo_root, "agent_team_runtime-0.1.0-py3-none-any.whl")

        self.assertNotIn("--no-index", install_script)
        self.assertIn('-m pip install "${tmp_dir}/${AGENT_TEAM_WHEEL}"', install_script)

    def test_install_script_installs_candidate_and_updates_stable_command(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            temp_root = Path(temp_dir)
            release_dir = build_fake_release_fixture(root=temp_root, repo_root=repo_root, version="0.1.0", broken=False)
            wheel_name = next(release_dir.glob("*.whl")).name
            install_root = temp_root / "install"
            bin_dir = temp_root / "bin"
            install_script = temp_root / "install.sh"
            install_script.write_text(render_install_script(repo_root, wheel_name))
            install_script.chmod(0o755)

            env = os.environ.copy()
            env["AGENT_TEAM_INSTALL_DIR"] = str(install_root)
            env["AGENT_TEAM_BIN_DIR"] = str(bin_dir)

            with release_server(release_dir) as base_url:
                env["AGENT_TEAM_RELEASE_BASE_URL"] = base_url
                result = subprocess.run(
                    ["sh", str(install_script)],
                    cwd=repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                reinstall_result = subprocess.run(
                    ["sh", str(install_script)],
                    cwd=repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(os.readlink(install_root / "current"), str(install_root / "versions" / "0.1.0"))
            self.assertTrue((bin_dir / "agent-team").exists())

            help_result = subprocess.run(
                [str(bin_dir / "agent-team"), "--help"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("fake agent-team 0.1.0", help_result.stdout)
            self.assertEqual(reinstall_result.returncode, 0, reinstall_result.stderr)
            self.assertIn("already installed", reinstall_result.stdout)

    def test_install_script_keeps_previous_version_when_candidate_smoke_check_fails(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
            temp_root = Path(temp_dir)
            release_dir = build_fake_release_fixture(root=temp_root, repo_root=repo_root, version="0.1.0", broken=True)
            wheel_name = next(release_dir.glob("*.whl")).name
            install_root = temp_root / "install"
            bin_dir = temp_root / "bin"
            old_version_dir = install_root / "versions" / "0.0.9" / "venv" / "bin"
            old_version_dir.mkdir(parents=True)
            old_binary = old_version_dir / "agent-team"
            old_binary.write_text("#!/usr/bin/env bash\nexit 0\n")
            old_binary.chmod(0o755)
            (install_root / "current").parent.mkdir(parents=True, exist_ok=True)
            (install_root / "current").symlink_to(install_root / "versions" / "0.0.9")
            bin_dir.mkdir()
            (bin_dir / "agent-team").symlink_to(install_root / "current" / "venv" / "bin" / "agent-team")

            install_script = temp_root / "install.sh"
            install_script.write_text(render_install_script(repo_root, wheel_name))
            install_script.chmod(0o755)

            env = os.environ.copy()
            env["AGENT_TEAM_INSTALL_DIR"] = str(install_root)
            env["AGENT_TEAM_BIN_DIR"] = str(bin_dir)

            with release_server(release_dir) as base_url:
                env["AGENT_TEAM_RELEASE_BASE_URL"] = base_url
                result = subprocess.run(
                    ["sh", str(install_script)],
                    cwd=repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(os.readlink(install_root / "current"), str(install_root / "versions" / "0.0.9"))


if __name__ == "__main__":
    unittest.main()
