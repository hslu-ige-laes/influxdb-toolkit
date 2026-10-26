# Release Process

Publishing a GitHub release triggers `.github/workflows/publish.yml`, which runs the
full test suite (Python 3.10–3.14), builds the dists, checks that the release tag
matches the version in `pyproject.toml`, and uploads to PyPI. Nothing is published
if any step fails.

## 1. Prepare

1. Ensure CI on `main` is green.
2. Bump `version` in `pyproject.toml` (for example, `0.2.0`).
3. In `CHANGELOG.md`, rename `## Unreleased` to the new version and add a fresh,
   empty `## Unreleased` section above it.
4. Commit and push to `main` (directly or via pull request).

## 2. Optional: dry run on TestPyPI

Recommended when packaging metadata changed (dependencies, README, classifiers).

1. GitHub → **Actions** → **Publish** → **Run workflow** (branch `main`).
2. Test the package in a clean environment:

```powershell
py -m venv .venv-test
.\.venv-test\Scripts\Activate.ps1
py -m pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ influxdb-toolkit
```

Run at least one read-only query using environment-configured credentials.

TestPyPI rejects a version that was already uploaded. To repeat a dry run, bump to a
pre-release version (for example, `0.2.0rc1`).

## 3. Publish

1. GitHub → **Releases** → **Draft a new release**.
2. Create a new tag `v<version>` (for example, `v0.2.0`) on `main`.
3. Use the version as title and paste the changelog entry as description.
4. Click **Publish release**.

Follow the run under **Actions** → **Publish**. If it fails before the upload (tests,
tag/version mismatch), fix the issue, delete the release and its tag, and create the
release again. A version that reached PyPI can never be uploaded again; publish a
new version instead.

## Local validation (optional)

To check the build locally before releasing:

```powershell
py -m pip install -e .[dev,polars,release]
py -m pytest -q
py -m build
py -m twine check --strict (Get-ChildItem dist\*).FullName
```

## One-time setup

The target is PyPI trusted publishing (OIDC), so no API tokens are stored in GitHub.

**Current state (transitional):** the workflow still uploads with the API tokens in
the repository secrets `PYPI_API_TOKEN` and `TEST_PYPI_API_TOKEN`. They belong to the
account of the previous project owner. Configuring a trusted publisher requires the
**Owner** role on PyPI; once that is available, complete the steps below and remove
the `password:` lines from `.github/workflows/publish.yml`.

1. On [pypi.org](https://pypi.org/manage/account/publishing/) (project
   `influxdb-toolkit` → **Settings** → **Publishing**, or as a pending publisher if the
   project does not exist yet) add a GitHub publisher:
   - Owner: `hslu-ige-laes`
   - Repository: `influxdb-toolkit`
   - Workflow: `publish.yml`
   - Environment: `pypi`
2. Repeat on [test.pypi.org](https://test.pypi.org/manage/account/publishing/) with
   environment `testpypi`.
3. In the GitHub repository → **Settings** → **Environments**, create `pypi` and
   `testpypi`. Optionally add required reviewers to `pypi` as a manual approval gate.
4. Remove the `password:` lines from `.github/workflows/publish.yml`, delete the
   `PYPI_API_TOKEN` / `TEST_PYPI_API_TOKEN` secrets and revoke the tokens on PyPI.
5. Make sure the project has at least two owners on PyPI.
