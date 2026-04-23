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

## Working from spec / plan markdown files (Task workflow)

When the user issues an instruction of the form **"start with task N"**, **"work
on task N"**, **"do task N"**, **"continue with task N"**, **"start task N"**,
or any close paraphrase (with or without a phase number, e.g. "start Phase 5b
Task 22"):

1. **Locate the task in the markdown file the user currently has open in the
   editor** (not in chat history, not by guessing — read the actual file). If
   no spec/plan file is open, ask the user which file to read.
2. **Read the task thoroughly and end-to-end** before doing anything else:
   - The task heading (`### Task N: <title>`).
   - Every `**Files:**` / `**API surface:**` / `**Step …**` block under it.
   - The **enclosing Phase heading** (`## Phase X — …`) and any phase intro
     prose (it often contains constraints that apply to every task in the
     phase).
   - The **Definition of Done** row for that task in the per-task acceptance
     criteria table near the top of the Implementation Plan section.
   - The **Universal DoD checklist (U1–U14)** and the **Non-Regression
     Guardrails (G1–G10)** — these apply to *every* task.
   - Any **"Prompt for subagent"** block at the bottom of the task — it is the
     authoritative summary of intent.
   - Any task the current task depends on (check the Master Execution Order
     table; a later step may not start until earlier ones are merged).
3. **Restate, in 2–4 lines, what the task requires** so the user can confirm
   you read the right thing. Include: files to create/modify, the acceptance
   criteria specific to this task, and any phase-level gate that must already
   be satisfied. Do **not** ask permission to start — restating *is* the
   confirmation; proceed in the same response.
4. **Run the baseline test snapshot** (per the Start Prompt in the spec) and
   record failure/error counts before writing any code.
5. **Implement the task one Step at a time**, in the order written, using
   tools (not chat). Tick off each `- [ ]` checkbox in the spec file as you
   complete it (edit the file in place).
6. **Honor every Guardrail (G1–G10) and the Universal DoD (U1–U14).** If a
   guardrail would be violated, stop and surface the conflict before
   proceeding.
7. **Commit once at the end** of the task, using the exact commit message
   shown in the task body (`feat(trends): …` etc.).
8. **Post the status update** in the format the Start Prompt specifies:
   `Step N/M complete: <title>. Tests: baseline=X/Y, current=X/Y. Commit: <hash>.`

If the user says **"start with the next task"** or **"continue"**, infer the
next task from the most recently completed checkbox or commit, and apply the
same workflow.

If the user says **"finish"**, **"complete the implementation"**, or **"are
we done?"**, run the **Completion Prompt** verification protocol from the spec
and report the results checkbox-by-checkbox.

The spec file is the source of truth — never invent acceptance criteria,
filenames, or steps that aren't written there. If the spec is ambiguous, ask;
do not paper over the ambiguity with a guess.
