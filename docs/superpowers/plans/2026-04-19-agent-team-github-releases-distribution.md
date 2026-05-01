# Agent Team GitHub Releases Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Agent Team as a GitHub-Releases-only CLI product that installs via `curl ... | sh`, verifies checksums, keeps upgrades safe, and runs without a repository checkout.

**Architecture:** First move runtime-critical assets into the Python package so a wheel installation is self-contained. Then add release-tooling scripts that render a version-pinned installer, extract version-specific changelog content, and verify tag/version parity. Finally wire those scripts into GitHub Actions so tag pushes build artifacts, upload release assets, and publish docs/install instructions that match the shipped workflow.

**Tech Stack:** Python 3.13, setuptools, unittest, shell installer, GitHub Actions, Markdown docs

---

## File Structure

- Modify: `pyproject.toml`
  Package metadata, package-data rules, and any console entrypoints needed for wheel-safe operations.

- Create: `agent_team/assets/roles/Product/context.md`
- Create: `agent_team/assets/roles/Product/memory.md`
- Create: `agent_team/assets/roles/Product/SKILL.md`
- Create: `agent_team/assets/roles/Dev/context.md`
- Create: `agent_team/assets/roles/Dev/memory.md`
- Create: `agent_team/assets/roles/Dev/SKILL.md`
- Create: `agent_team/assets/roles/QA/context.md`
- Create: `agent_team/assets/roles/QA/memory.md`
- Create: `agent_team/assets/roles/QA/SKILL.md`
- Create: `agent_team/assets/roles/Acceptance/context.md`
- Create: `agent_team/assets/roles/Acceptance/memory.md`
- Create: `agent_team/assets/roles/Acceptance/SKILL.md`
- Create: `agent_team/assets/roles/Ops/context.md`
- Create: `agent_team/assets/roles/Ops/memory.md`
- Create: `agent_team/assets/roles/Ops/SKILL.md`
  Wheel-owned copies of the role assets that the runtime currently reads from the repository root.

- Create: `agent_team/assets/codex_skill/agent-team-workflow/SKILL.md`
- Create: `agent_team/assets/codex_skill/agent-team-workflow/scripts/agent-team-run.sh`
  Wheel-owned Codex skill assets so users can install the skill without cloning the repo.

- Create: `agent_team/packaged_assets.py`
  Helpers for reading packaged asset text and copying packaged asset trees to user-chosen destinations.

- Modify: `agent_team/roles.py`
  Fallback from repo-root role directories to packaged role assets when the repo checkout does not contain those directories.

- Modify: `agent_team/cli.py`
  Add a wheel-safe `install-codex-skill` command and keep existing CLI behavior intact.

- Create: `agent_team/codex_skill_installer.py`
  Copy the packaged Codex skill into `$CODEX_HOME` and print the installed paths.

- Create: `scripts/release/verify_release_version.py`
  Fail fast if the pushed git tag and `pyproject.toml` version differ.

- Create: `scripts/release/extract_release_changelog.py`
  Read repository `CHANGELOG.md` and emit the current version section as release-local `CHANGELOG.md`.

- Create: `scripts/release/render_install_script.py`
  Render a version-pinned `install.sh` from a checked-in template and the current release metadata.

- Create: `scripts/release/install.sh.template`
  The checked-in shell installer template that downloads wheel and checksum assets from the same release.

- Create: `.github/workflows/ci.yml`
  Run test and build checks on `main` and pull requests.

- Create: `.github/workflows/release.yml`
  Build release assets and publish a GitHub Release for `v*` tags.

- Create: `.github/release.yml`
  Release-note category config so GitHub’s generated metadata stays tidy if used later.

- Create: `CHANGELOG.md`
  Canonical product changelog with version sections that the release tooling can extract.

- Modify: `README.md`
  Replace editable-install guidance with GitHub Releases installation and upgrade instructions.

- Modify: `docs/workflow-specs/2026-04-11-agent-team-cli-runtime-usage.md`
  Align runtime usage docs with release install and wheel-owned assets.

- Create: `tests/test_packaged_assets.py`
  Tests for packaged role/skill asset loading and copying.

- Create: `tests/test_release_tooling.py`
  Tests for version parsing, changelog extraction, and installer rendering.

- Create: `tests/test_release_install_script.py`
  Integration-style tests for installer success, reinstall, and failed-upgrade behavior using local release fixtures.

- Modify: `tests/test_state.py`
  Assert role profile loading works without repo-root role directories.

- Modify: `tests/test_skill_package.py`
  Assert wheel-safe skill installation works via the CLI and packaged assets.

- Modify: `tests/test_console_scripts.py`
  Add a non-editable wheel installation smoke test.

- Modify: `tests/test_docs.py`
  Assert release-install instructions and changelog expectations stay documented.

## Task 1: Package Runtime Assets Into The Wheel

**Files:**
- Modify: `pyproject.toml`
- Create: `agent_team/assets/roles/Product/context.md`
- Create: `agent_team/assets/roles/Product/memory.md`
- Create: `agent_team/assets/roles/Product/SKILL.md`
- Create: `agent_team/assets/roles/Dev/context.md`
- Create: `agent_team/assets/roles/Dev/memory.md`
- Create: `agent_team/assets/roles/Dev/SKILL.md`
- Create: `agent_team/assets/roles/QA/context.md`
- Create: `agent_team/assets/roles/QA/memory.md`
- Create: `agent_team/assets/roles/QA/SKILL.md`
- Create: `agent_team/assets/roles/Acceptance/context.md`
- Create: `agent_team/assets/roles/Acceptance/memory.md`
- Create: `agent_team/assets/roles/Acceptance/SKILL.md`
- Create: `agent_team/assets/roles/Ops/context.md`
- Create: `agent_team/assets/roles/Ops/memory.md`
- Create: `agent_team/assets/roles/Ops/SKILL.md`
- Create: `agent_team/assets/codex_skill/agent-team-workflow/SKILL.md`
- Create: `agent_team/assets/codex_skill/agent-team-workflow/scripts/agent-team-run.sh`
- Create: `agent_team/packaged_assets.py`
- Modify: `agent_team/roles.py`
- Modify: `tests/test_state.py`
- Create: `tests/test_packaged_assets.py`

- [ ] **Step 1: Add a failing packaged-role fallback test**

```python
def test_load_role_profiles_uses_packaged_assets_when_repo_roles_are_missing(self) -> None:
    from agent_team.roles import load_role_profiles

    with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
        repo_root = Path(temp_dir) / "empty-repo"
        repo_root.mkdir()
        state_root = Path(temp_dir) / "state"
        state_root.mkdir()

        roles = load_role_profiles(repo_root=repo_root, state_root=state_root)

        self.assertIn("Product", roles)
        self.assertIn("QA", roles)
        self.assertIn("Product Manager Onboarding Manual", roles["Product"].effective_context_text)
```

- [ ] **Step 2: Run the failing role-loader test**

Run: `python -m unittest tests.test_state.StateTests.test_load_role_profiles_uses_packaged_assets_when_repo_roles_are_missing -v`

Expected: FAIL because `load_role_profiles()` currently skips roles when `<repo-root>/<Role>` does not exist.

- [ ] **Step 3: Add a failing packaged-asset copy test**

```python
class PackagedAssetTests(unittest.TestCase):
    def test_copy_packaged_codex_skill_tree(self) -> None:
        from agent_team.packaged_assets import copy_packaged_tree

        with TemporaryDirectory() as temp_dir:
            written = copy_packaged_tree(
                ("codex_skill", "agent-team-workflow"),
                Path(temp_dir) / "installed-skill",
            )

            self.assertTrue((Path(temp_dir) / "installed-skill" / "SKILL.md").exists())
            self.assertTrue(any(path.name == "agent-team-run.sh" for path in written))
```

- [ ] **Step 4: Run the failing packaged-asset copy test**

Run: `python -m unittest tests.test_packaged_assets.PackagedAssetTests.test_copy_packaged_codex_skill_tree -v`

Expected: FAIL with `ModuleNotFoundError` or missing helper function because `agent_team.packaged_assets` does not exist yet.

- [ ] **Step 5: Copy the current role and skill assets under `agent_team/assets/`**

```text
agent_team/assets/
  roles/
    Product/{context.md,memory.md,SKILL.md}
    Dev/{context.md,memory.md,SKILL.md}
    QA/{context.md,memory.md,SKILL.md}
    Acceptance/{context.md,memory.md,SKILL.md}
    Ops/{context.md,memory.md,SKILL.md}
  codex_skill/
    agent-team-workflow/
      SKILL.md
      scripts/agent-team-run.sh
```

Copy the repository versions verbatim so the packaged assets and repo-local assets start from identical content.

- [ ] **Step 6: Add packaged-asset helpers and package-data rules**

```python
# agent_team/packaged_assets.py
from __future__ import annotations

from importlib.resources import files
from pathlib import Path


ASSET_ROOT = files("agent_team").joinpath("assets")


def packaged_text(*parts: str) -> str:
    return ASSET_ROOT.joinpath(*parts).read_text()


def copy_packaged_tree(parts: tuple[str, ...], destination: Path) -> list[Path]:
    source = ASSET_ROOT.joinpath(*parts)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            written.extend(copy_packaged_tree(parts + (item.name,), target))
        else:
            target.write_text(item.read_text())
            written.append(target)
    return written
```

```toml
# pyproject.toml
[tool.setuptools]
packages = ["agent_team"]
include-package-data = true

[tool.setuptools.package-data]
agent_team = [
  "acceptance_policy.json",
  "assets/roles/*/*.md",
  "assets/codex_skill/agent-team-workflow/SKILL.md",
  "assets/codex_skill/agent-team-workflow/scripts/*.sh",
]
```

- [ ] **Step 7: Update `roles.py` to fall back to packaged role text**

```python
def load_role_profiles(
    repo_root: Path,
    state_root: Path | None = None,
    role_names: tuple[str, ...] = DEFAULT_ROLE_NAMES,
) -> dict[str, RoleProfile]:
    profiles: dict[str, RoleProfile] = {}

    for role_name in role_names:
        role_dir = repo_root / role_name
        if role_dir.exists():
            context_text = _read_text(role_dir / "context.md")
            memory_text = _read_text(role_dir / "memory.md")
            skill_text = _read_text(role_dir / "SKILL.md")
        else:
            context_text = packaged_text("roles", role_name, "context.md")
            memory_text = packaged_text("roles", role_name, "memory.md")
            skill_text = packaged_text("roles", role_name, "SKILL.md")

        profiles[role_name] = RoleProfile(
            name=role_name,
            role_dir=role_dir,
            context_path=role_dir / "context.md",
            memory_path=role_dir / "memory.md",
            skill_path=role_dir / "SKILL.md",
            base_context_text=context_text,
            base_memory_text=memory_text,
            base_skill_text=skill_text,
            learned_context_text=_read_text((state_root / "memory" / role_name / "context_patch.md")) if state_root else "",
            learned_memory_text=_read_text((state_root / "memory" / role_name / "lessons.md")) if state_root else "",
            learned_skill_text=_read_text((state_root / "memory" / role_name / "skill_patch.md")) if state_root else "",
        )
```

- [ ] **Step 8: Re-run the focused packaged-asset tests**

Run: `python -m unittest tests.test_state.StateTests.test_load_role_profiles_uses_packaged_assets_when_repo_roles_are_missing tests.test_packaged_assets -v`

Expected: PASS with both repo-local and packaged-asset loading covered.

## Task 2: Add A Wheel-Safe Codex Skill Installer

**Files:**
- Create: `agent_team/codex_skill_installer.py`
- Modify: `agent_team/cli.py`
- Modify: `tests/test_skill_package.py`

- [ ] **Step 1: Add a failing CLI test for packaged skill installation**

```python
def test_cli_install_codex_skill_uses_packaged_assets(self) -> None:
    repo_root = Path(__file__).resolve().parents[1]

    with TemporaryDirectory() as temp_dir:
        env = os.environ.copy()
        env["HOME"] = temp_dir
        env.pop("CODEX_HOME", None)

        result = subprocess.run(
            [sys.executable, "-m", "agent_team", "--repo-root", str(repo_root), "install-codex-skill"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        installed_skill = Path(temp_dir) / ".codex" / "skills" / "agent-team-workflow" / "SKILL.md"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(installed_skill.exists())
```

- [ ] **Step 2: Run the failing CLI skill-install test**

Run: `python -m unittest tests.test_skill_package.SkillPackageTests.test_cli_install_codex_skill_uses_packaged_assets -v`

Expected: FAIL because `install-codex-skill` is not a recognized CLI command.

- [ ] **Step 3: Implement the packaged skill installer helper**

```python
# agent_team/codex_skill_installer.py
from __future__ import annotations

import os
from pathlib import Path

from .packaged_assets import copy_packaged_tree


def install_codex_skill(codex_home: Path | None = None) -> Path:
    root = codex_home or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    target = root / "skills" / "agent-team-workflow"
    copy_packaged_tree(("codex_skill", "agent-team-workflow"), target)
    return target
```

- [ ] **Step 4: Wire the new command into `agent_team.cli`**

```python
install_skill_parser = subparsers.add_parser(
    "install-codex-skill",
    help="Install the packaged agent-team-workflow skill into CODEX_HOME.",
)
install_skill_parser.set_defaults(handler=_handle_install_codex_skill)


def _handle_install_codex_skill(args: argparse.Namespace) -> int:
    target = install_codex_skill()
    print(f"installed_skill: {target / 'SKILL.md'}")
    return 0
```

- [ ] **Step 5: Re-run the skill-install tests**

Run: `python -m unittest tests.test_skill_package.SkillPackageTests.test_cli_install_codex_skill_uses_packaged_assets tests.test_skill_package.SkillPackageTests.test_install_script_copies_skill_into_codex_home -v`

Expected: PASS, proving both the new CLI path and the existing repo-local shell script path still install the same skill tree.

## Task 3: Add Release Metadata Tooling And Changelog Extraction

**Files:**
- Create: `CHANGELOG.md`
- Create: `scripts/release/verify_release_version.py`
- Create: `scripts/release/extract_release_changelog.py`
- Create: `tests/test_release_tooling.py`
- Modify: `tests/test_docs.py`

- [ ] **Step 1: Add failing tests for version verification and changelog extraction**

```python
class ReleaseToolingTests(unittest.TestCase):
    def test_verify_release_version_accepts_matching_tag(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/release/verify_release_version.py", "--tag", "v0.1.0"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

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
        self.assertIn("0.1.0", result.stdout)
        self.assertNotIn("Unreleased", result.stdout)
```

- [ ] **Step 2: Run the failing release-tooling tests**

Run: `python -m unittest tests.test_release_tooling -v`

Expected: FAIL because the release-tooling scripts and root changelog do not exist yet.

- [ ] **Step 3: Create the canonical changelog file**

```markdown
# Changelog

## [Unreleased]

- No unreleased entries yet.

## [0.1.0] - 2026-04-19

- Added the first GitHub-Releases-only distribution contract for Agent Team.
- Added a version-pinned shell installer and checksum-verified release artifacts.
```

- [ ] **Step 4: Implement the tag/version verifier**

```python
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args()

    package_version = tomllib.loads(args.pyproject.read_text())["project"]["version"]
    tag_version = args.tag.removeprefix("refs/tags/").removeprefix("v")
    if tag_version != package_version:
        print(f"tag {tag_version} does not match package version {package_version}", file=sys.stderr)
        return 1
    print(package_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Implement the changelog extractor**

```python
def extract_version_section(markdown: str, version: str) -> str:
    header = f"## [{version}]"
    lines = markdown.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## [")), len(lines))
    return "\n".join(lines[start:end]).strip() + "\n"
```

```python
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--changelog", type=Path, required=True)
    args = parser.parse_args()

    print(extract_version_section(args.changelog.read_text(), args.version))
    return 0
```

- [ ] **Step 6: Add a docs assertion for release-install guidance**

```python
def test_readme_mentions_github_release_installer(self) -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    self.assertIn("releases/latest/download/install.sh", readme)
    self.assertIn("CHANGELOG.md", readme)
```

- [ ] **Step 7: Re-run the release-tooling and docs tests**

Run: `python -m unittest tests.test_release_tooling tests.test_docs -v`

Expected: PASS, proving the repo has a canonical changelog and deterministic version-check tooling.

## Task 4: Render A Version-Pinned Installer And Test Local Install Behavior

**Files:**
- Create: `scripts/release/install.sh.template`
- Create: `scripts/release/render_install_script.py`
- Create: `tests/test_release_install_script.py`
- Modify: `tests/test_console_scripts.py`

- [ ] **Step 1: Add a failing installer-rendering test**

```python
def test_render_install_script_embeds_release_coordinates(self) -> None:
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
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("AGENT_TEAM_RELEASE_TAG=\"v0.1.0\"", result.stdout)
    self.assertIn("agent_team-0.1.0-py3-none-any.whl", result.stdout)
```

- [ ] **Step 2: Add a failing installer integration test with local release fixtures**

```python
def test_install_script_keeps_previous_version_when_candidate_smoke_check_fails(self) -> None:
    release_dir = build_fake_release_fixture(version="0.1.0", broken=True)
    result = run_installer_with_base_url(release_dir)
    self.assertNotEqual(result.returncode, 0)
    self.assertEqual(read_current_symlink_version(), "0.0.9")
```

Use a helper HTTP server in the test so the installer still performs real `curl` downloads; do not replace the installer with a pure-Python fake.

- [ ] **Step 3: Run the failing installer tests**

Run: `python -m unittest tests.test_release_tooling.ReleaseToolingTests.test_render_install_script_embeds_release_coordinates tests.test_release_install_script -v`

Expected: FAIL because the template, renderer, and fixture helpers do not exist yet.

- [ ] **Step 4: Check in the installer template**

```bash
#!/usr/bin/env bash
set -euo pipefail

AGENT_TEAM_REPO="${AGENT_TEAM_REPO:-{{ repo }}}"
AGENT_TEAM_RELEASE_TAG="${AGENT_TEAM_RELEASE_TAG:-{{ tag }}}"
AGENT_TEAM_VERSION="${AGENT_TEAM_VERSION:-{{ version }}}"
AGENT_TEAM_WHEEL="${AGENT_TEAM_WHEEL:-{{ wheel }}}"
AGENT_TEAM_RELEASE_BASE_URL="${AGENT_TEAM_RELEASE_BASE_URL:-https://github.com/${AGENT_TEAM_REPO}/releases/download/${AGENT_TEAM_RELEASE_TAG}}"
AGENT_TEAM_INSTALL_DIR="${AGENT_TEAM_INSTALL_DIR:-${HOME}/.local/share/agent-team}"
AGENT_TEAM_BIN_DIR="${AGENT_TEAM_BIN_DIR:-${HOME}/.local/bin}"
AGENT_TEAM_FORCE="${AGENT_TEAM_FORCE:-0}"
```

The hidden `AGENT_TEAM_RELEASE_BASE_URL` override is only for local integration tests and must default to the real GitHub Releases URL.

- [ ] **Step 5: Implement the installer renderer**

```python
TEMPLATE_TOKENS = {
    "{{ repo }}": args.repo,
    "{{ tag }}": args.tag,
    "{{ version }}": args.version,
    "{{ wheel }}": args.wheel,
}

content = template_path.read_text()
for token, value in TEMPLATE_TOKENS.items():
    content = content.replace(token, value)
print(content)
```

- [ ] **Step 6: Finish the installer body with checksum and symlink safety**

```bash
tmp_dir="$(mktemp -d)"
version_dir="${AGENT_TEAM_INSTALL_DIR}/versions/${AGENT_TEAM_VERSION}"
candidate_dir="${version_dir}/venv"

curl -fsSL "${AGENT_TEAM_RELEASE_BASE_URL}/${AGENT_TEAM_WHEEL}" -o "${tmp_dir}/${AGENT_TEAM_WHEEL}"
curl -fsSL "${AGENT_TEAM_RELEASE_BASE_URL}/SHA256SUMS" -o "${tmp_dir}/SHA256SUMS"
verify_checksum "${tmp_dir}/${AGENT_TEAM_WHEEL}" "${tmp_dir}/SHA256SUMS"
python3 -m venv "${candidate_dir}"
"${candidate_dir}/bin/python" -m pip install "${tmp_dir}/${AGENT_TEAM_WHEEL}"
"${candidate_dir}/bin/agent-team" --help >/dev/null
ln -sfn "${version_dir}" "${AGENT_TEAM_INSTALL_DIR}/current"
ln -sfn "${AGENT_TEAM_INSTALL_DIR}/current/venv/bin/agent-team" "${AGENT_TEAM_BIN_DIR}/agent-team"
```

Do not move the `current` symlink before the smoke check passes.

- [ ] **Step 7: Add a wheel-install smoke test**

```python
def test_built_wheel_installs_and_runs_help(self) -> None:
    repo_root = Path(__file__).resolve().parents[1]

    with TemporaryDirectory(dir=local_temp_dir()) as temp_dir:
        dist_dir = Path(temp_dir) / "dist"
        subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)], cwd=repo_root, check=True)
        wheel_path = next(dist_dir.glob("*.whl"))

        venv_dir = Path(temp_dir) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], cwd=repo_root, check=True)
        subprocess.run([str(venv_dir / "bin" / "python"), "-m", "pip", "install", str(wheel_path)], cwd=repo_root, check=True)

        help_result = subprocess.run([str(venv_dir / "bin" / "agent-team"), "--help"], capture_output=True, text=True, check=False)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
```

- [ ] **Step 8: Re-run the installer and wheel smoke tests**

Run: `python -m unittest tests.test_release_tooling tests.test_release_install_script tests.test_console_scripts.ConsoleScriptTests.test_built_wheel_installs_and_runs_help -v`

Expected: PASS, proving the rendered installer and built wheel both behave like release artifacts.

## Task 5: Wire Release Automation And Update Product Docs

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Create: `.github/release.yml`
- Modify: `README.md`
- Modify: `docs/workflow-specs/2026-04-11-agent-team-cli-runtime-usage.md`
- Modify: `tests/test_docs.py`

- [ ] **Step 1: Add a failing docs test for release install, upgrade, and pinned version commands**

```python
def test_readme_documents_latest_and_pinned_release_install(self) -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    self.assertIn("releases/latest/download/install.sh", readme)
    self.assertIn("releases/download/v0.1.0/install.sh", readme)
    self.assertIn("Python 3.13+", readme)
```

- [ ] **Step 2: Run the failing docs test**

Run: `python -m unittest tests.test_docs.DocsTests.test_readme_documents_latest_and_pinned_release_install -v`

Expected: FAIL because the README still documents editable installation.

- [ ] **Step 3: Add CI workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: python -m pip install --upgrade pip build
      - run: python -m unittest
      - run: python -m build
```

- [ ] **Step 4: Add release workflow**

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: python -m pip install --upgrade pip build
      - run: python -m unittest
      - run: python scripts/release/verify_release_version.py --tag "${GITHUB_REF_NAME}"
      - run: python -m build
      - run: python scripts/release/extract_release_changelog.py --version "${GITHUB_REF_NAME#v}" --changelog CHANGELOG.md > dist/CHANGELOG.md
      - run: |
          WHEEL_PATH=$(find dist -maxdepth 1 -name '*.whl' | head -n 1)
          python scripts/release/render_install_script.py \
            --repo "${GITHUB_REPOSITORY}" \
            --tag "${GITHUB_REF_NAME}" \
            --version "${GITHUB_REF_NAME#v}" \
            --wheel "$(basename "${WHEEL_PATH}")" > dist/install.sh
      - run: (cd dist && shasum -a 256 *.whl *.tar.gz install.sh CHANGELOG.md > SHA256SUMS)
```

Use a dedicated release-upload step after artifact generation so the workflow only publishes when every required asset already exists.

- [ ] **Step 5: Add release configuration and docs updates**

```yaml
# .github/release.yml
changelog:
  categories:
    - title: Runtime
      labels: ["runtime"]
    - title: Packaging
      labels: ["packaging", "release"]
    - title: Documentation
      labels: ["docs"]
```

````markdown
## Install

Requirements:

- Python 3.13+
- `curl`
- `shasum` or `sha256sum`

Latest:

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/Agent Team/releases/latest/download/install.sh | sh
```

Pinned:

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/Agent Team/releases/download/v0.1.0/install.sh | sh
```
````

- [ ] **Step 6: Re-run docs assertions**

Run: `python -m unittest tests.test_docs -v`

Expected: PASS, showing the repo docs describe the actual release flow.

## Task 6: Final Verification And Release Dry Run

**Files:**
- Test: `tests/test_state.py`
- Test: `tests/test_packaged_assets.py`
- Test: `tests/test_skill_package.py`
- Test: `tests/test_release_tooling.py`
- Test: `tests/test_release_install_script.py`
- Test: `tests/test_console_scripts.py`
- Test: `tests/test_docs.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run the focused distribution regression suite**

Run:

```bash
python -m unittest \
  tests.test_state \
  tests.test_packaged_assets \
  tests.test_skill_package \
  tests.test_release_tooling \
  tests.test_release_install_script \
  tests.test_console_scripts \
  tests.test_docs -v
```

Expected: PASS with release tooling, packaged assets, and docs all covered.

- [ ] **Step 2: Build final release artifacts locally**

Run:

```bash
python -m build
python scripts/release/verify_release_version.py --tag "v0.1.0"
python scripts/release/extract_release_changelog.py --version "0.1.0" --changelog CHANGELOG.md > /tmp/agent-team-release-changelog.md
python scripts/release/render_install_script.py \
  --repo "ZHOUKAILIAN/Agent Team" \
  --tag "v0.1.0" \
  --version "0.1.0" \
  --wheel "$(basename "$(find dist -maxdepth 1 -name '*.whl' | head -n 1)")" > /tmp/agent-team-install.sh
```

Expected: `dist/*.whl`, `dist/*.tar.gz`, `/tmp/agent-team-release-changelog.md`, and `/tmp/agent-team-install.sh` all exist.

- [ ] **Step 3: Manually inspect the built wheel for packaged assets**

Run:

```bash
python - <<'PY'
from pathlib import Path
import zipfile

wheel = next(Path("dist").glob("*.whl"))
with zipfile.ZipFile(wheel) as zf:
    names = zf.namelist()
    required = [
        "agent_team/assets/roles/Product/context.md",
        "agent_team/assets/codex_skill/agent-team-workflow/SKILL.md",
        "agent_team/acceptance_policy.json",
    ]
    missing = [name for name in required if name not in names]
    if missing:
        raise SystemExit(f"missing wheel assets: {missing}")
    print("wheel assets verified")
PY
```

Expected: `wheel assets verified`

- [ ] **Step 4: Commit the release-distribution implementation in logical slices**

```bash
git add pyproject.toml agent_team/assets agent_team/packaged_assets.py agent_team/roles.py tests/test_state.py tests/test_packaged_assets.py
git commit -m "feat: package runtime assets for wheel installs"

git add agent_team/codex_skill_installer.py agent_team/cli.py tests/test_skill_package.py
git commit -m "feat: add wheel-safe codex skill installer"

git add CHANGELOG.md scripts/release tests/test_release_tooling.py tests/test_release_install_script.py tests/test_console_scripts.py
git commit -m "feat: add release tooling and installer"

git add .github/workflows .github/release.yml README.md docs/workflow-specs/2026-04-11-agent-team-cli-runtime-usage.md tests/test_docs.py
git commit -m "docs: document GitHub Releases distribution"
```

- [ ] **Step 5: Create and push the release tag after merge**

Run:

```bash
git tag v0.1.0
git push origin main
git push origin v0.1.0
```

Expected: GitHub Actions `Release` workflow starts, uploads `wheel`, `tar.gz`, `install.sh`, `SHA256SUMS`, and `CHANGELOG.md`, then publishes the release.

## Self-Review Coverage

- Spec coverage: asset packaging is handled in Task 1, wheel-safe skill install in Task 2, changelog/version tooling in Task 3, installer safety in Task 4, GitHub Actions and docs in Task 5, and acceptance/dry-run validation in Task 6.
- Placeholder scan: no `TODO`, `TBD`, or “implement later” markers remain; every test and command is spelled out.
- Type consistency: the plan uses one consistent helper naming set: `packaged_text`, `copy_packaged_tree`, `install_codex_skill`, `verify_release_version.py`, `extract_release_changelog.py`, and `render_install_script.py`.
