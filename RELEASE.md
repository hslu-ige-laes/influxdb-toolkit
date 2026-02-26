# Release Process

## 1. Prepare

1. Ensure `main` is green.
2. Update version in `pyproject.toml`.
3. Update `CHANGELOG.md`.

## 2. Validate

```powershell
py -m pip install -e .[release]
py -m build
$files = Get-ChildItem dist\\* | Select-Object -ExpandProperty FullName
py -m twine check $files
py -m pytest -q
```

## 3. Publish to TestPyPI

```powershell
py -m twine upload --repository testpypi dist/*
```

## 4. Test on clean environment / PC

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -i https://test.pypi.org/simple/ influxdb-toolkit
```

Run at least one read-only query using environment-configured credentials.

## 5. Publish to PyPI

```powershell
py -m twine upload dist/*
```

## 6. Tag

Create and push a git tag matching the version (for example, `v0.1.1`).


