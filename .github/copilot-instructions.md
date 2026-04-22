# Copilot / AI agent instructions for `trends_research`

These notes capture environment quirks discovered while working in this repo so
future automated coding sessions don't have to re-discover them.

## Running Python / pytest on Windows

**TL;DR — use the Anaconda interpreter directly with its full path:**

```powershell
& "C:\Users\MarianCraciun\anaconda3\python.exe" -m pytest tests/ -v
```

### Why the obvious things don't work

| Command | Result |
|---|---|
| `python` / `python3` | Resolves to the **Microsoft Store stub** in `C:\Users\…\AppData\Local\Microsoft\WindowsApps\python.exe` and fails with *"The system cannot find the path specified"*. |
| `py` | Not installed (no Python launcher). |
| `.\.venv\Scripts\python.exe` | The repo's `.venv` was created from **WSL** (`pyvenv.cfg` has `home = /usr/bin`). The Windows stub inside it tries to resolve the base interpreter at `/usr/bin\python.exe` and errors out. |
| `wsl -- .venv/bin/python …` | `.venv/bin` does not exist — the venv only has the Windows-style `Scripts/` layout, so it isn't usable from Linux either. |
| `wsl -- python3 -m pytest` | System WSL Python 3.13 has no project deps installed (`ModuleNotFoundError: pytest` / `fastapi` / `pandas` / …). |

### The working setup

There **is** a usable system Python: **Anaconda 3.13.9** at
`C:\Users\MarianCraciun\anaconda3\python.exe`. Most heavy deps (`pandas`,
`numpy`, `scikit-learn`, `sqlalchemy`, `scrapy`, `nltk`, `requests`, …) are
already installed there. A few project-specific deps had to be added with:

```powershell
& "C:\Users\MarianCraciun\anaconda3\python.exe" -m pip install `
    fastapi uvicorn gunicorn httpx `
    resend ensembledata pyodbc azure-identity python-multipart vaderSentiment
```

After that, the full test suite runs with:

```powershell
& "C:\Users\MarianCraciun\anaconda3\python.exe" -m pytest tests/ -v
```

### Known pre-existing test failures (NOT caused by your edits)

A baseline run on `main` produces **2 failures + 23 errors**, all in:

* `tests/test_ads_insight.py`
* `tests/test_trend_collector.py`
* `tests/test_all_sources.py`

The root cause is `unittest.mock.patch` targeting attributes (e.g.
`get_session`) that don't exist on the patched scraper modules. If your change
leaves those counts unchanged, you have not introduced a regression. To verify,
stash your changes and re-run those three files:

```powershell
git stash
& "C:\Users\MarianCraciun\anaconda3\python.exe" -m pytest `
    tests/test_ads_insight.py tests/test_trend_collector.py tests/test_all_sources.py
git stash pop
```

## PowerShell shell tips

* The default shell is `powershell.exe` (Windows PowerShell 5.1) — **not**
  PowerShell Core. Some POSIX-ish syntax does not work.
* Use `;` (not `&&`) to chain commands.
* `2>&1` works, but always combine with `Select-Object -Last N` or
  `Format-Table` to keep output manageable.
* Invoke executables with paths that contain spaces using the call operator:
  `& "C:\path with spaces\tool.exe" args`.
* `git` output can paginate — prefix with `git --no-pager …`.

## Repo layout reminders

* Backend entrypoint: `src/api/main.py` (FastAPI). It uses
  `@app.on_event("startup")` handlers (no lifespan context manager).
* Test config lives in `pyproject.toml` (pytest `configfile`).
* `.env.example` documents required env vars; copy to `.env` for local runs.
* The `ENV` env var gates production-only guards (e.g. the OTP-bypass guard in
  `src/api/main.py` — see `_check_test_account_env_guard`). Valid values:
  `development`, `dev`, `staging`, `production`, `prod`.

