# Agent Team GitHub Releases Distribution Design

Date: 2026-04-19

## Goal

Ship `Agent Team` as a mature CLI product distributed only through GitHub Releases, without requiring users to clone the repository or install from PyPI.

The target installation experience is:

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/Agent Team/releases/latest/download/install.sh | sh
```

Users may also install a pinned version:

```bash
curl -fsSL https://github.com/ZHOUKAILIAN/Agent Team/releases/download/v0.1.0/install.sh | sh
```

This design assumes the user machine already has `Python >= 3.13`.

## Summary

Each versioned GitHub Release becomes the single source of truth for distribution.

Every release must include:

- built Python wheel
- source archive
- version-pinned `install.sh`
- `SHA256SUMS`
- release-specific `CHANGELOG.md`

The release workflow must:

1. validate that the git tag and `pyproject.toml` version match
2. run tests before publishing
3. build wheel and source distribution
4. generate checksums and release changelog
5. generate a version-pinned installer script
6. create the GitHub Release and upload all assets

The installer script must:

1. check runtime prerequisites
2. download artifacts from the same release
3. verify checksums
4. create an isolated virtual environment under the user home directory
5. install the wheel locally
6. expose a stable `agent-team` command under `~/.local/bin`
7. leave the previous version intact until the new version passes a smoke check

## Problems In The Current State

### 1. Installation is still development-oriented

The current documented install path is:

```bash
pip install -e .
```

That is suitable for contributors, not end users. It depends on a repository checkout and exposes the project as a source tree instead of a versioned product.

### 2. Distribution assets are not yet formal release artifacts

The repository can already build a Python package, but it does not yet define a release contract that guarantees:

- exact artifact set
- checksums
- changelog shape
- release automation
- stable installer entrypoint

### 3. Runtime assets may still be implicitly repo-local

The product includes role assets and Codex skill packaging material outside the Python package root. If the runtime depends on those files at execution time, a wheel-only installation may succeed while runtime behavior fails.

### 4. Versioned upgrades are not yet productized

Without a dedicated installer and install layout, upgrades risk mutating the live install in place. A mature release process should support safe upgrade and rollback boundaries even if rollback is manual in the first version.

## Design Goals

- Make GitHub Releases the only distribution channel.
- Preserve a one-command install experience.
- Require no repository checkout and no PyPI access.
- Keep the product install user-local and `sudo`-free.
- Ensure release artifacts are checksum-verifiable.
- Ensure failed installs do not break the previously working version.
- Keep the first release operationally simple enough to maintain.

## Non-Goals

- Do not build standalone native binaries in this iteration.
- Do not support installation without Python.
- Do not make GitHub Packages or PyPI fallback channels part of this design.
- Do not redesign the core runtime behavior in this change.

## Recommended Distribution Model

Use a Python wheel as the primary install artifact and a release-scoped shell installer as the product entrypoint.

### Why This Model

- The project is already a Python CLI with a declared console entrypoint.
- A wheel is the most direct way to distribute the exact packaged runtime.
- A thin installer script keeps the user experience simple while preserving checksum verification and safe directory management.
- Requiring `Python >= 3.13` is acceptable for this product.

### Alternatives Considered

#### Source archive install

Install from `tar.gz` by building locally on the user machine.

Rejected because:

- local build behavior is less deterministic
- installation becomes slower and more fragile
- it feels less like a finished product than installing a prebuilt wheel

#### Standalone binary release

Ship bundled executables per platform.

Rejected for this phase because:

- multi-platform build and test cost is much higher
- release maintenance becomes heavier immediately
- the current project shape already fits wheel-based distribution well

## Release Artifact Contract

Each GitHub Release must include exactly these user-facing assets:

- `agent_team-<version>-py3-none-any.whl`
- `agent_team-<version>.tar.gz`
- `install.sh`
- `SHA256SUMS`
- `CHANGELOG.md`

Notes:

- The exact wheel and source file names must come from the build output instead of being hardcoded by hand.
- The installer must resolve artifact names dynamically from release-generated metadata or embedded values produced during the release workflow.
- `CHANGELOG.md` in the release assets is a version-scoped extract, not necessarily the repository root changelog file verbatim.

## Versioning Rules

Use semantic version tags with a leading `v`:

- `v0.1.0`
- `v0.1.1`
- `v0.2.0`

The version stored in `pyproject.toml` remains the package source of truth:

```toml
[project]
version = "0.1.0"
```

Release rule:

- release tag without the leading `v` must exactly match the package version

If the tag and package version differ, release publication must fail before creating the final release.

Pre-release support is optional. The first implementation may ignore pre-releases entirely to reduce complexity.

## GitHub Actions Design

### CI Workflow

Trigger on:

- `push` to `main`
- `pull_request`

Responsibilities:

- set up Python 3.13
- run test suite
- verify package build succeeds

This workflow prevents broken changes from reaching release tags unnoticed.

### Release Workflow

Trigger on:

- `push` tags matching `v*`

Responsibilities:

1. check out the tagged commit
2. set up Python 3.13
3. run tests
4. validate tag version against `pyproject.toml`
5. build wheel and source distribution
6. compute `SHA256SUMS`
7. render release-specific `CHANGELOG.md`
8. render a version-pinned `install.sh`
9. create a draft GitHub Release
10. upload all release assets
11. publish the release

### Release Permissions

The release workflow only needs repository contents write permission to create the GitHub Release and upload assets.

### Draft-Then-Publish Rule

Create the release as a draft first, upload all assets, then publish it.

This avoids partial public releases and keeps the release asset set atomic from the user point of view.

## Installer Script Design

### Entry Model

The installer script attached to each release is not generic across versions. It is generated during release publication and embeds:

- repository slug
- release tag
- package version
- expected primary artifact names

That means:

- `latest/download/install.sh` always yields the installer for the latest published release
- `download/v0.1.0/install.sh` always yields the installer for `v0.1.0`

The script does not need to infer which version it belongs to at runtime.

### Runtime Checks

Before installation, `install.sh` must verify:

- `python3` exists
- Python version is `>= 3.13`
- `curl` exists
- either `shasum -a 256` or `sha256sum` exists

If any prerequisite is missing, the script must stop with a concrete error message and zero ambiguity about the missing command or version.

### Download Behavior

The installer downloads from the same GitHub Release that produced it:

- wheel
- `SHA256SUMS`

The source archive does not need to be downloaded during a normal install.

The installer must fail closed:

- if the wheel cannot be downloaded
- if checksums cannot be downloaded
- if checksum verification fails

No install step may continue after a checksum failure.

### Installation Layout

Install under the user home directory:

```text
~/.local/share/agent-team/
  versions/
    0.1.0/
      venv/
      install-manifest.json
  current -> versions/0.1.0

~/.local/bin/
  agent-team -> ~/.local/share/agent-team/current/venv/bin/agent-team
```

Rules:

- no `sudo`
- no global site-packages mutation
- each installed version gets its own isolated directory
- the stable command path is always `~/.local/bin/agent-team`

### Upgrade Behavior

Re-running the installer for a newer release creates a new version directory, installs there, runs a smoke check, then atomically updates the `current` symlink.

If installation or smoke check fails:

- `current` must remain pointed at the previously working version
- the user must receive a failure message that identifies the failed phase

If the same version is already active, the installer may exit early unless the user explicitly forces reinstall.

### Smoke Check

After local wheel installation and before switching `current`, the installer must run:

```bash
<new-venv>/bin/agent-team --help
```

The install is only considered successful if that command exits successfully.

### Optional Installer Configuration

The installer may support these environment variables:

- `AGENT_TEAM_INSTALL_DIR`
- `AGENT_TEAM_BIN_DIR`
- `AGENT_TEAM_FORCE`

The first version does not need broader configuration than that.

Avoid over-designing the installer into a full package manager.

## Changelog Design

Maintain a repository-root `CHANGELOG.md` as the canonical product changelog.

At release time:

1. locate the section for the current version
2. extract that section into a release-local `CHANGELOG.md`
3. use the same content as the GitHub Release body, optionally prefixed with the install command

This keeps release notes product-oriented instead of relying entirely on generated PR titles.

## Packaging Requirements

Before release distribution is considered complete, all runtime-critical assets must be installable from the wheel alone.

That includes any files the runtime needs at execution time from locations such as:

- role assets
- skill assets
- policy JSON
- scaffolding templates

The packaging design must make one of these true:

1. move runtime-critical assets under the package directory and include them as package data
2. explicitly copy them into build output through setuptools packaging configuration

The release must not depend on the repository working tree existing on the user machine.

## Data Flow

### Release Publication Flow

```text
maintainer updates code + CHANGELOG
-> maintainer updates pyproject version
-> maintainer pushes tag vX.Y.Z
-> release workflow validates version
-> tests run
-> wheel and sdist build
-> checksums generated
-> install.sh rendered with embedded version metadata
-> GitHub Release draft created
-> assets uploaded
-> release published
```

### User Installation Flow

```text
user runs curl .../install.sh | sh
-> installer checks prerequisites
-> installer downloads wheel + SHA256SUMS from the same release
-> installer verifies checksum
-> installer creates versioned venv
-> installer installs wheel locally
-> installer runs agent-team --help smoke check
-> installer updates current symlink
-> user runs agent-team
```

## Error Handling

The design must produce clear failure behavior for these cases:

### 1. Missing Python or unsupported version

Installer exits before any download or filesystem mutation beyond temporary work files.

### 2. Network or GitHub download failure

Installer exits with the failing asset name and release tag.

### 3. Checksum mismatch

Installer exits immediately and never installs the artifact.

### 4. Virtual environment creation failure

Installer leaves the current version untouched and surfaces the failing command.

### 5. Local wheel installation failure

Installer leaves the current version untouched and reports the pip failure.

### 6. Post-install smoke check failure

Installer leaves the current version untouched and reports that the candidate version did not pass validation.

### 7. Release workflow version mismatch

Release publication fails before any public release is published.

### 8. Missing changelog section for tagged version

Release publication fails. A tagged version without release notes is a release-process error.

## Testing Strategy

The implementation should be validated at three levels.

### 1. Unit-Level Validation

- parse package version from `pyproject.toml`
- render version-pinned installer metadata correctly
- extract the correct changelog section
- detect checksum command availability

### 2. Workflow-Level Validation

- CI verifies package build still works
- release workflow fails when tag and package version differ
- release workflow fails when tests fail
- release workflow emits all required assets

### 3. Install-Level Validation

In a clean test environment:

- install latest via release `install.sh`
- verify `agent-team --help` works
- reinstall same version and confirm idempotent behavior
- install a newer version and confirm symlink switch
- simulate failure before symlink switch and confirm old version remains active

## Open Decisions

These decisions should be made during implementation but do not block this design:

- whether checksum generation covers only shipped install assets or every built file
- whether the installer stores a richer install manifest for future uninstall and doctor commands
- whether the first release includes a CLI self-management namespace such as `agent-team self doctor`

## Acceptance Criteria

This design is complete when all of the following are true:

1. pushing tag `vX.Y.Z` creates a GitHub Release with wheel, source archive, `install.sh`, `SHA256SUMS`, and `CHANGELOG.md`
2. release publication fails if tests fail
3. release publication fails if tag and package version do not match
4. users can install from `latest/download/install.sh` without cloning the repository
5. users can install a pinned release from `download/vX.Y.Z/install.sh`
6. installation uses only GitHub Release assets and does not depend on PyPI
7. installation verifies artifact checksums before local install
8. installation exposes a working `agent-team` command under a stable user-local path
9. a failed upgrade does not replace the previously working version
10. the installed product can access all runtime-critical assets without a repository checkout

## Conclusion

The right first mature distribution model for `Agent Team` is:

- GitHub Releases only
- wheel-based installation
- version-pinned installer per release
- checksum verification by default
- user-local versioned install layout

This keeps the product simple, auditable, and operationally maintainable while eliminating the current requirement to clone the repository for normal usage.
