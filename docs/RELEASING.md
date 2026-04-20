# Releasing Theogony

This file is the single source of truth for how Theogony is released to PyPI. It documents both the **local verification path** (you do this every time before any release) and the **publication path** (gated, so accidents are hard).

## Versioning

The version is **single-sourced** in [`src/theogony/__init__.py`](../src/theogony/__init__.py) as `__version__`. `pyproject.toml` declares `dynamic = ["version"]`, and hatchling parses the value at build time. Never bump the version in two places.

The git tag pushed for a release must match the value of `__version__` exactly, prefixed with `v`. Examples:

- `__version__ = "0.1.0"` → tag `v0.1.0`
- `__version__ = "0.2.0"` → tag `v0.2.0`

## Local Verification (Always)

Before any release, build and inspect the distribution locally. This catches metadata regressions, missing data files, and broken installs before CI ever runs.

```bash
# 1. Clean previous artefacts.
rm -rf dist build

# 2. Build wheel + sdist (uses an isolated build environment).
./venv/bin/python -m build

# 3. Validate the metadata the same way PyPI will.
./venv/bin/python -m twine check dist/*

# 4. Eyeball the wheel — confirms cli.py, mcp/, py.typed, and the
#    answer_synthesizer.md prompt are all bundled.
./venv/bin/python -m zipfile -l dist/*.whl | head -40

# 5. Eyeball the sdist — confirms docs, prompts, phoenix-backlog,
#    and the project metadata files are bundled.
tar tzf dist/*.tar.gz | head -40

# 6. Smoke-install in a throwaway venv and run the CLI.
rm -rf /tmp/theogony_install_test
python3 -m venv /tmp/theogony_install_test
/tmp/theogony_install_test/bin/pip install dist/theogony-*.whl
/tmp/theogony_install_test/bin/theogony --help
/tmp/theogony_install_test/bin/python -c "import theogony; print(theogony.__version__)"
```

If any step fails, fix the build before pushing a tag.

## CI Release Workflow

The workflow at [`.github/workflows/release.yml`](../.github/workflows/release.yml) has **two trigger modes**:

| Trigger | What it does | When to use |
|---|---|---|
| `workflow_dispatch` (default `publish=false`) | Builds + validates + uploads artefacts. Does not publish. | Pre-release verification on a clean Linux runner. |
| `workflow_dispatch` with `publish=true` | Builds + attempts publish (still gated by environment approval). | Manual rescue of a release whose tag was forgotten. |
| Tag push `v*` | Builds + attempts publish (gated by environment approval). | The standard release path. |

The build job always runs and uploads the wheel + sdist as workflow artefacts; you can download those from the GitHub Actions run page and inspect them locally without any PyPI side effects.

## One-Time Setup Before First Publish

The publish step is **double-gated** — both gates must be configured before the first release can succeed. Both are deliberate: they make publishing impossible without explicit, recorded human action.

### 1. PyPI Trusted Publisher (no API tokens)

PyPI's modern OIDC publishing flow means GitHub Actions can publish without any long-lived secret stored in this repository.

1. Reserve the `theogony` name on PyPI. The simplest path is to register `https://pypi.org/account/register/` (if needed), then on the project's settings page, add a **Trusted Publisher** with:
   - **Owner:** `theogony-project`
   - **Repository name:** `theogony`
   - **Workflow filename:** `release.yml`
   - **Environment name:** `pypi`
2. Save. PyPI will then accept uploads from this exact workflow + environment combination, and only this one.

If you want to dry-run the upload first against TestPyPI, repeat the same steps at `https://test.pypi.org/` and temporarily switch the action's `repository-url` input to the TestPyPI endpoint before reverting.

### 2. GitHub Environment `pypi`

GitHub Environments add a manual-approval gate before any token-bearing step runs.

1. In the repository: `Settings` → `Environments` → `New environment`.
2. Name: **`pypi`** (must match the workflow's `environment.name`).
3. Add **Required reviewers**: at minimum the repository owner. Anyone listed must explicitly approve before the publish job will run.
4. Optionally restrict deployment branches/tags to `v*` so the environment cannot be reached from arbitrary branches.

Once both gates are configured, the workflow will pause at the publish job after build completes; you receive a GitHub notification asking for approval; clicking approve runs the upload.

## Release Procedure

1. **Bump the version** in `src/theogony/__init__.py`. Follow [SemVer](https://semver.org/): patch (`0.1.0 → 0.1.1`), minor (`0.1.0 → 0.2.0`), major (`0.1.0 → 1.0.0`). Theogony stays on `0.x` until the substrate contracts (Pantheon Vision §"Non-Negotiable Principles") stabilise.
2. **Run the local verification** above. If it does not pass, do not proceed.
3. **Open a PR** with the version bump alone. Title: `chore(release): vX.Y.Z`. Body: list of user-visible changes since the last release (or "first release" if this is `v0.1.0`). Get it merged.
4. **Tag from `main`** after the PR merges:
   ```bash
   git checkout main && git pull origin main
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```
5. **Watch the workflow** at `https://github.com/theogony-project/theogony/actions`. The build job runs automatically; the publish job pauses for environment approval.
6. **Approve the environment** when ready. The upload completes; the new release appears at `https://pypi.org/project/theogony/`.
7. **Verify** in a throwaway venv:
   ```bash
   python3 -m venv /tmp/theogony_release_check
   /tmp/theogony_release_check/bin/pip install --upgrade theogony
   /tmp/theogony_release_check/bin/theogony --help
   ```

## Yanking a Bad Release

If a release is broken in a way local verification missed, **yank it on PyPI** (do not delete — yanked releases stay resolvable for pinned installers, just disappear from `pip install theogony` defaults). Then bump the patch version and release a fix.

## Changelog

Until a `CHANGELOG.md` is established, the GitHub Releases page (`https://github.com/theogony-project/theogony/releases`) is the canonical changelog. Use the body of each release tag to summarise user-visible changes.

## Related Files

- [`pyproject.toml`](../pyproject.toml) — package metadata, hatchling build targets, optional extras.
- [`src/theogony/__init__.py`](../src/theogony/__init__.py) — `__version__` (single source of truth).
- [`.github/workflows/release.yml`](../.github/workflows/release.yml) — the build + publish workflow.
- [`AGENTS.md`](../AGENTS.md) — discipline for AI agents picking up release work.
